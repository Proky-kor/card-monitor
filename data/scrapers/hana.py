"""하나카드 파서 (목록=httpx·EUC-KR, 개별상세·출시일=Playwright).

목록은 AJAX `POST /OPI31000000D.ajax`(폼인코딩, 응답 EUC-KR)로 직접 수집한다.
응답 dataMap.CARD_LIST.data[]: CD_NM(이름)·CD_NO(코드)·CD_ID·LIST_IMG_TYPE_IMG(이미지)·CD_DESC_TXT(설명)

개별 상세페이지는 사이트의 goCardInfo2(CD_NO)가 만드는 URL을 그대로 재현한다:
  /OPI41000000D.web?schID=pcd&mID=PI41{CD_NO 6자리 0채움}P&CD_PD_SEQ={CD_NO}
이 페이지 본문에 "출시 시기 : YYYY.MM.DD"가 노출되므로 Playwright 렌더로 파싱한다.
(목록 AJAX·"카드 한눈에 보기"(mID=OPI41000000C)에는 출시일이 없다.)
출시일은 불변이라 known_launch에 있으면 상세 재조회를 생략한다(최초 1회만 전체 조회).
"""

import json
import logging
import re
import time
from dataclasses import replace

import config
from data.http import make_client, request_with_retry
from data.models import CardProduct

_log = logging.getLogger(__name__)

COMPANY = "hana"
COMPANY_NAME = "하나카드"
BASE = "https://www.hanacard.co.kr"
API = BASE + "/OPI31000000D.ajax"
LIST_PAGE = BASE + "/OPI31000000D.web?schID=pcd&mID=OPI31000005P&CT_ID={ct}"
HOME_URL = LIST_PAGE.format(ct="241704030444153")

# (카드구분, CT_ID)
_CATEGORIES = [
    ("신용", "241704030444153"),
    ("체크", "241704050328506"),
    ("신용", "241704030444279"),  # 제휴(신용계열)
]
_TAG_RE = re.compile(r"<[^>]+>")
# 상세페이지 본문 "출시 시기 : 2025.02.17" (구분자 . - / 허용)
_LAUNCH_RE = re.compile(r"출시\s*시기\s*[:：]?\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _body(ct: str) -> str:
    return (f"schID=pcd&mID=OPM05000000C&PAGE=&SORT_KEY=&SORT_TYPE="
            f"&PAGE_TYPE=&CT_ID={ct}&ST_ID=")


def _detail_url(code: str) -> str:
    """개별 상품 상세페이지 URL (goCardInfo2(CD_NO) 재현). 숫자코드만 지원."""
    if code.isdigit():
        return f"{BASE}/OPI41000000D.web?schID=pcd&mID=PI41{int(code):06d}P&CD_PD_SEQ={code}"
    return HOME_URL  # 비정상 코드는 목록으로 폴백


def _parse_launch_date(body_text: str) -> str | None:
    """상세페이지 본문에서 '출시 시기 : YYYY.MM.DD' → 'YYYY-MM-DD' 또는 None (순수 함수)."""
    m = _LAUNCH_RE.search(body_text)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def _fetch_list() -> dict[str, CardProduct]:
    """카드 목록(출시일 없이) 수집. {code: CardProduct}."""
    by_code: dict[str, CardProduct] = {}
    with make_client(ajax=True, referer=HOME_URL) as client:
        client.headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        for card_type, ct in _CATEGORIES:
            try:
                resp = request_with_retry(client, "POST", API, content=_body(ct))
                resp.raise_for_status()
                data = json.loads(resp.content.decode("euc-kr", "replace"))
                cards = data.get("dataMap", {}).get("CARD_LIST", {}).get("data", [])
            except Exception as e:
                _log.warning("하나 목록 실패 ct=%s: %s", ct, e)
                cards = []
            _log.info("하나카드 %s(%s): %d건", card_type, ct, len(cards))
            for it in cards:
                code = (it.get("CD_NO") or "").strip()
                name = (it.get("CD_NM") or "").strip()
                if not code or not name or code in by_code:
                    continue
                img = it.get("LIST_IMG_TYPE_IMG") or ""
                image_url = (BASE + img) if img.startswith("/") else (img or None)
                desc = _TAG_RE.sub(" ", it.get("CD_DESC_TXT") or "").strip() or None
                by_code[code] = CardProduct(
                    company=COMPANY, company_name=COMPANY_NAME, code=code, name=name,
                    card_type=card_type, image_url=image_url,
                    detail_url=_detail_url(code),
                    launch_date=None, description=desc,
                )
    return by_code


def _fetch_launch_dates(codes: list[str]) -> dict[str, str]:
    """상세페이지 렌더로 출시일 보강. {code: 'YYYY-MM-DD'} (실패 건은 생략)."""
    out: dict[str, str] = {}
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # playwright 미설치 시 출시일만 비우고 계속
        _log.warning("playwright 미설치 — 하나 출시일 보강 skip: %s", e)
        return out
    _log.info("하나카드 출시일 보강 대상 %d건", len(codes))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ko-KR", user_agent=_UA)
        page = ctx.new_page()
        for code in codes:
            if not code.isdigit():
                continue
            try:
                page.goto(_detail_url(code), wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2000)
                ld = _parse_launch_date(page.inner_text("body"))
                if ld:
                    out[code] = ld
            except Exception as e:  # 한 건 실패는 치명적이지 않음
                _log.warning("하나 출시일 조회 실패 code=%s: %s", code, e)
            time.sleep(config.REQUEST_DELAY)
        browser.close()
    return out


def scrape(known_launch: dict[str, str] | None = None) -> list[CardProduct]:
    """하나카드 신용+체크+제휴 전체 상품.

    known_launch: {code: 출시일} 이미 아는 출시일 (불변이므로 상세 재조회 생략).
    """
    known = known_launch or {}
    by_code = _fetch_list()

    # 이미 아는 출시일 먼저 채움
    for code, ld in known.items():
        if code in by_code and ld and not by_code[code].launch_date:
            by_code[code] = replace(by_code[code], launch_date=ld)

    # 출시일 모르는 상품만 상세 렌더로 보강 (저속)
    missing = [c for c in by_code if not by_code[c].launch_date]
    if missing:
        for code, ld in _fetch_launch_dates(missing).items():
            if ld:
                by_code[code] = replace(by_code[code], launch_date=ld)

    _log.info("하나카드 합계 %d건", len(by_code))
    return list(by_code.values())
