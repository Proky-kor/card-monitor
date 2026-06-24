"""수집 오케스트레이션: 전 회사 파서 실행 → 이미지 저장 → DB upsert.

graceful: 회사 1곳이 실패해도 나머지는 계속한다(구체 예외 로깅).
"""

import hashlib
import io
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from PIL import Image

import config
from data.http import make_client
from data.models import CardProduct
from data.scrapers import NOTICE_REGISTRY, REGISTRY
from storage import db

_log = logging.getLogger(__name__)
_EXT_OK = {"jpg": "jpg", "jpeg": "jpg", "png": "png", "gif": "gif", "webp": "webp"}
_MIN_MATCH_LEN = 4  # 매칭 오탐 방지 최소 정규화 길이


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _norm_name(s: str) -> str:
    """매칭용 정규화: 소문자·공백제거·끝 '카드' 제거."""
    t = re.sub(r"\s+", "", s).lower()
    while t.endswith("카드"):
        t = t[:-2]
    return t


def match_notice_to_products(
    card_names: tuple[str, ...], products: list
) -> list[str]:
    """공지 제목의 상품명 후보 ↔ 상품 목록(code,name) 매칭 → code 리스트 (순수 함수)."""
    matched: list[str] = []
    norm_prods = [(p["code"], _norm_name(p["name"])) for p in products]
    for cand in card_names:
        nc = _norm_name(cand)
        if len(nc) < _MIN_MATCH_LEN:
            continue
        for code, npn in norm_prods:
            if not npn or len(npn) < _MIN_MATCH_LEN:
                continue
            if nc == npn or nc in npn or npn in nc:
                if code not in matched:
                    matched.append(code)
    return matched


def _safe_stem(company: str, code: str) -> str:
    """회사+코드를 안전한 파일 stem으로. 경로 트래버설 방지(해시 병용)."""
    base = re.sub(r"[^A-Za-z0-9_-]", "_", f"{company}_{code}")
    digest = hashlib.sha1(f"{company}:{code}".encode("utf-8")).hexdigest()[:8]
    return f"{base}_{digest}"


def _download_image(client: httpx.Client, company: str, product: CardProduct) -> str | None:
    """이미지 다운로드·검증·저장. 저장 경로(상대, '회사/파일')를 반환하거나 None."""
    if not product.image_url:
        return None
    try:
        resp = client.get(product.image_url)
        resp.raise_for_status()
        data = resp.content
        with Image.open(io.BytesIO(data)) as img:
            fmt = (img.format or "").lower()
        ext = _EXT_OK.get(fmt)
        if ext is None:
            _log.warning("지원않는 이미지 포맷 company=%s code=%s fmt=%s", company, product.code, fmt)
            return None
        company_dir = Path(config.IMAGE_DIR) / company
        company_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{_safe_stem(company, product.code)}.{ext}"
        target = (company_dir / fname).resolve()
        # 경로 트래버설 방지: IMAGE_DIR 하위인지 검증
        if not str(target).startswith(str(Path(config.IMAGE_DIR).resolve())):
            raise ValueError(f"경로 트래버설 시도: {fname!r}")
        target.write_bytes(data)
        return f"{company}/{fname}"
    except (httpx.HTTPError, OSError, ValueError) as e:
        _log.warning("이미지 저장 실패 company=%s code=%s: %s", company, product.code, e)
        return None


def collect_company(company: str) -> dict:
    """단일 회사 수집. 결과 요약 dict 반환(신규 등록 상품 포함)."""
    name, scrape = REGISTRY[company]
    with db.get_conn() as conn:
        known = db.known_launch_dates(conn, company)
        prior = db.existing_codes(conn, company)  # 수집 전 기존 코드(신규 감지용)
    products = scrape(known_launch=known)
    now = _now()
    # 처음 본 코드 = 신규 등록 상품 (최초 수집 시 prior가 비면 전부를 신규로 보지 않음)
    new_products: list[CardProduct] = []
    if prior:
        seen_new: set[str] = set()
        for p in products:
            if p.code not in prior and p.code not in seen_new:
                seen_new.add(p.code)
                new_products.append(p)
    # 수집 0건은 (사이트 개편이 아니라) 클라우드 일시 실패일 가능성이 크다.
    # 이 상태로 mark_discontinued를 부르면 seen=∅ → 해당 회사 전체가 단종 처리되는
    # 데이터 오염이 발생하므로, 0건이면 단종 마킹을 건너뛰고 실패로 본다.
    if not products:
        _log.warning("[%s] 수집 0건 → 단종 마킹 건너뜀(일시 실패로 간주, 기존 데이터 보존)", name)
        return {"company": company, "name": name, "collected": 0,
                "discontinued": 0, "new_count": 0, "_new_products": []}
    seen: set[str] = set()
    with db.get_conn() as conn, make_client(referer=None) as img_client:
        for p in products:
            seen.add(p.code)
            image_path = _download_image(img_client, company, p)
            db.upsert_product(conn, p, now=now, image_path=image_path)
        discontinued = db.mark_discontinued(conn, company, seen, now)

    _log.info("[%s] 수집 %d건, 신규등록 %d건, 미노출 단종 %d건",
              name, len(products), len(new_products), discontinued)
    return {"company": company, "name": name, "collected": len(products),
            "discontinued": discontinued, "new_count": len(new_products),
            "_new_products": new_products}


def _collect_notices(company: str, now: str) -> tuple[int, int]:
    """단종/발급중단 공지 수집·저장 + 상품 매칭 반영. (공지수, 매칭상품수) 반환."""
    scrape_notices = NOTICE_REGISTRY.get(company)
    if scrape_notices is None:
        return (0, 0)
    notices = scrape_notices()
    matched_total = 0
    with db.get_conn() as conn:
        db.clear_notices(conn, company)  # 현재 공지로 전량 갱신
        prods = db.products_for_matching(conn, company)
        for n in notices:
            codes = match_notice_to_products(n.card_names, prods)
            db.upsert_notice(conn, n, now=now, matched_codes=codes)
            if codes:
                db.apply_discontinue_from_notice(
                    conn, company, codes, notice_url=n.url, now=now,
                )
                matched_total += len(codes)
    return (len(notices), matched_total)


def collect_all() -> list[dict]:
    """등록된(또는 .env로 지정된) 회사 전체 수집. 회사 실패는 건너뛴다.

    수집 후 신규 등록 상품이 있으면 Teams로 1회 알림한다.
    """
    targets = config.ENABLED_COMPANIES or list(REGISTRY.keys())
    summaries = []
    new_all: list[CardProduct] = []
    for company in targets:
        if company not in REGISTRY:
            _log.warning("미등록 회사 건너뜀: %s", company)
            continue
        try:
            s = collect_company(company)
            new_all.extend(s.pop("_new_products", []))
            summaries.append(s)
        except Exception as e:  # graceful: 회사 1곳 실패해도 계속
            _log.exception("[%s] 수집 실패: %s", company, e)
            summaries.append({"company": company, "error": str(e)})

    if new_all:
        from services.notifier import notify_new_products
        notify_new_products(new_all)
    return summaries
