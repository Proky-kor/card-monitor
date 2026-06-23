"""롯데카드 파서 (파일럿, 검증된 JSON 경로).

목록(신용): POST /app/LPCDADA_A100.lc (type=credit)
목록(체크): POST /app/LPCDADA_A101.lc (type=cco)
응답: {"Content": "<li>...</li> HTML조각", "Param": {"totalRowCnt": 페이지수}}
조각: <li><a onclick="GoDet('<코드>')"> ... <img src=".../cdInfo/<파일>"> ...
        <b class="tit"><상품명></b><span class="txt"><설명></span></a></li>
"""

import logging
import re
import time
from dataclasses import replace

from bs4 import BeautifulSoup

import config
from data.http import make_client
from data.models import CardProduct, DiscontinueNotice

_log = logging.getLogger(__name__)

# 상세페이지의 "카드출시일 : 2021년 06월 22일" → (연,월,일)
_LAUNCH_RE = re.compile(r"카드출시일\s*[:：]\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")

COMPANY = "lotte"
COMPANY_NAME = "롯데카드"
BASE = "https://www.lottecard.co.kr"
LANDING = BASE + "/app/LPCDADA_V100.lc"
HOME_URL = LANDING  # 카드 목록 홈
NOTICE_URL = BASE + "/app/LPEVNCA_V100.lc"  # 공지사항(단종/발급중단 검색 기준)
NOTICE_LIST_URL = BASE + "/app/LPEVNCA_V101.lc"  # 공지 목록 AJAX
NOTICE_DETAIL_TMPL = BASE + "/app/LPEVNCA_V200.lc?newsSeq={seq}"
# 사람이 보는 상품 상세페이지 (GoDet 이동 대상)
DETAIL_TMPL = BASE + "/app/LPCDADB_V100.lc?vtCdKndC={code}"

# 단종/발급중단 공지 검색어 (검색은 토큰 OR라 노이즈가 섞임 → 제목 엄격필터로 거른다)
_NOTICE_KEYWORDS = ["발급 중단", "발급중단", "단종"]
# 진짜 카드 단종/발급중단 공지만 통과시키는 제목 필터
_DISCONTINUE_TITLE = re.compile(r"(발급\s*중단|발급\s*종료|단종|판매\s*중단)")
_DODETAIL = re.compile(r"DoDetail\(\s*'([^']+)'")
# 제목에서 떼어낼 접미 (상품명 후보만 남기기 위함)
_TITLE_SUFFIX = re.compile(r"\s*(카드)?\s*(발급\s*중단|단종|판매\s*중단|발급\s*종료)\s*안내?\s*$")

# (엔드포인트, type 파라미터) — 신용/체크 구분은 부정확(cco가 체크가 아님)하여 제외.
# 두 목록을 합쳐 전체 상품을 수집하되 card_type 라벨은 부여하지 않는다.
_LISTS = [
    ("/app/LPCDADA_A100.lc", "credit"),
    ("/app/LPCDADA_A101.lc", "cco"),
]
_MAX_PAGES = 30  # 안전 상한
_GODET = re.compile(r"GoDet\(\s*'([^']+)'")


def _parse_fragment(html: str, card_type: str) -> list[CardProduct]:
    soup = BeautifulSoup(html, "lxml")
    out: list[CardProduct] = []
    for a in soup.select("a[onclick*=GoDet]"):
        m = _GODET.search(a.get("onclick", ""))
        if not m:
            continue
        code = m.group(1).strip()
        tit = a.select_one("b.tit")
        name = tit.get_text(strip=True) if tit else ""
        if not name:
            continue
        txt = a.select_one("span.txt")
        desc = txt.get_text(strip=True) if txt else None
        img_el = a.select_one("img")
        image_url = None
        if img_el and img_el.get("src"):
            src = img_el["src"].strip()
            if src.startswith("//"):
                src = "https:" + src
            # noimg 플레이스홀더는 무시
            if "card_noimg" not in src:
                image_url = src
        out.append(
            CardProduct(
                company=COMPANY,
                company_name=COMPANY_NAME,
                code=code,
                name=name,
                card_type=card_type,
                image_url=image_url,
                detail_url=DETAIL_TMPL.format(code=code),
                launch_date=None,
                description=desc,
            )
        )
    return out


def _fetch_list(client, endpoint: str, type_param: str, card_type: str) -> list[CardProduct]:
    products: dict[str, CardProduct] = {}
    total_pages = 1
    page = 1
    while page <= total_pages and page <= _MAX_PAGES:
        form = {
            "pageNo": str(page),
            "totalRowCnt": "0",
            "type": type_param,
            "cate": "",
            "cond": "",
            "isDet": "N",
            "allSearch": "",
        }
        resp = client.post(BASE + endpoint, data=form)
        resp.raise_for_status()
        data = resp.json()
        param = data.get("Param", {}) if isinstance(data, dict) else {}
        total_pages = int(param.get("totalRowCnt", 1) or 1)
        content = data.get("Content", "") if isinstance(data, dict) else ""
        for p in _parse_fragment(content, card_type):
            products[p.code] = p  # 코드 기준 중복 제거
        page += 1
        time.sleep(config.REQUEST_DELAY)
    return list(products.values())


def _parse_launch_date(html: str) -> str | None:
    """상세페이지 HTML에서 '카드출시일' → 'YYYY-MM-DD' 또는 None (순수 함수)."""
    m = _LAUNCH_RE.search(html)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def _fetch_launch_date(client, code: str) -> str | None:
    """상세페이지를 받아 카드출시일 파싱."""
    try:
        resp = client.get(DETAIL_TMPL.format(code=code))
        resp.raise_for_status()
    except Exception as e:  # 한 건 실패는 치명적이지 않음
        _log.warning("출시일 조회 실패 code=%s: %s", code, e)
        return None
    return _parse_launch_date(resp.text)


def scrape(known_launch: dict[str, str] | None = None) -> list[CardProduct]:
    """롯데카드 신용+체크 전체 상품 목록.

    known_launch: {code: 출시일} 이미 아는 출시일 (출시일은 불변이므로 재요청 생략).
    """
    known = known_launch or {}
    results: dict[str, CardProduct] = {}
    with make_client(ajax=True, referer=LANDING) as client:
        client.get(LANDING)  # 세션 쿠키 확보
        for endpoint, type_param in _LISTS:
            items = _fetch_list(client, endpoint, type_param, "")  # 구분 라벨 없음
            _log.info("롯데카드 %s 목록: %d건", type_param, len(items))
            for p in items:
                results.setdefault(p.code, p)  # 먼저 본 목록 유지

    # 이미 아는 출시일 먼저 채움
    for code, ld in known.items():
        if code in results and ld and not results[code].launch_date:
            results[code] = replace(results[code], launch_date=ld)

    # 출시일 모르는 상품만 상세페이지에서 보강 (저속)
    missing = [c for c in results if not results[c].launch_date]
    if missing:
        _log.info("롯데카드 출시일 보강 대상 %d건", len(missing))
        with make_client(referer=LANDING) as dclient:
            for code in missing:
                ld = _fetch_launch_date(dclient, code)
                if ld:
                    results[code] = replace(results[code], launch_date=ld)
                time.sleep(config.REQUEST_DELAY)
    return list(results.values())


# ---------------------------------------------------------------------------
# 단종/발급중단 공지
# ---------------------------------------------------------------------------

def _extract_card_names(title: str) -> tuple[str, ...]:
    """공지 제목에서 대상 상품명 후보 추출.

    예) '디지로카 Travel, 디지로카 Travel 프리미엄 카드 발급 중단 안내'
        -> ('디지로카 Travel', '디지로카 Travel 프리미엄')
    """
    core = _TITLE_SUFFIX.sub("", title).strip()
    parts = [p.strip() for p in core.split(",") if p.strip()]
    # 각 후보 끝의 '카드' 토큰은 매칭 정규화에서 처리하므로 그대로 둠
    return tuple(dict.fromkeys(parts))


def _parse_notice_fragment(html: str) -> list[DiscontinueNotice]:
    """공지 목록 HTML 조각 파싱 (순수 함수). 발급중단/단종류만 추려 반환."""
    soup = BeautifulSoup(html, "lxml")
    out: list[DiscontinueNotice] = []
    for a in soup.select("a[onclick*=DoDetail]"):
        m = _DODETAIL.search(a.get("onclick", ""))
        if not m:
            continue
        seq = m.group(1).strip()
        tit_el = a.select_one("strong.tit, .tit")
        title = tit_el.get_text(strip=True) if tit_el else a.get_text(strip=True)
        if not title or not _DISCONTINUE_TITLE.search(title):
            continue  # 진짜 발급중단/단종 공지만 (검색 노이즈 제거)
        # 단종 날짜는 파싱하지 않음(기능 제외). notice_id 역순 = 최신순.
        out.append(
            DiscontinueNotice(
                company=COMPANY,
                company_name=COMPANY_NAME,
                notice_id=seq,
                title=title,
                notice_date=None,
                url=NOTICE_DETAIL_TMPL.format(seq=seq),
                card_names=_extract_card_names(title),
            )
        )
    return out


def scrape_notices() -> list[DiscontinueNotice]:
    """롯데카드 단종/발급중단 공지 수집 (검색어 여러 개 합집합, newsSeq 기준 중복 제거)."""
    found: dict[str, DiscontinueNotice] = {}
    with make_client(ajax=True, referer=NOTICE_URL) as client:
        client.get(NOTICE_URL)  # 세션 쿠키
        for kw in _NOTICE_KEYWORDS:
            form = {
                "pageNo": "1",
                "pageRows": "50",
                "newsSeq": "",
                "procType": "",
                "searchText": kw,
                "curRowCnt": "0",
            }
            try:
                resp = client.post(NOTICE_LIST_URL, data=form)
                resp.raise_for_status()
                content = resp.json().get("Content", "")
            except Exception as e:  # 검색어 1개 실패는 치명적이지 않음
                _log.warning("롯데 공지 검색 실패 kw=%s: %s", kw, e)
                continue
            for n in _parse_notice_fragment(content):
                found[n.notice_id] = n
            time.sleep(config.REQUEST_DELAY)
    _log.info("롯데카드 단종/발급중단 공지 %d건", len(found))
    return list(found.values())
