"""BC카드(비씨) 파서 (순수 httpx).

비씨 목록 API는 폼인코딩 POST로 httpx 직호출이 된다(세션 불필요).
  신용: POST /app/card/CreditSearch.do  (body: retKey=json&pageNo=N)
  체크: POST /app/card/CheckSearch.do
응답: {TOTAL, PAGE_COUNT, CARDGDS:[...]}, item당
  cardGdsNo(코드)·cardGdsNm(이름)·CARD_GDS_IMG(이미지 경로)·affiFirmNo·mbNo
BC는 회원은행 카드를 모으는 네트워크라 카드 출시일을 노출하지 않음 → launch_date=None.
상세: /app/card/{Credit|Check}CardMain.do?gdsno=<affiFirmNo>&mbkNo=<mbNo>
"""

import logging

from data.http import make_client, request_with_retry
from data.models import CardProduct

_log = logging.getLogger(__name__)

COMPANY = "bc"
COMPANY_NAME = "BC카드"
BASE = "https://www.bccard.com"
HOME_URL = BASE + "/app/card/CreditCardMain.do"
_MAX_PAGES = 40  # 안전 상한

# (카드구분, 검색 엔드포인트, 상세 메인 페이지)
_LISTS = [
    ("신용", "/app/card/CreditSearch.do", "CreditCardMain.do"),
    ("체크", "/app/card/CheckSearch.do", "CheckCardMain.do"),
]


def _fetch_list(client, endpoint: str, card_type: str, detail_page: str) -> list[CardProduct]:
    products: dict[str, CardProduct] = {}
    page = 1
    total_pages = 1
    while page <= total_pages and page <= _MAX_PAGES:
        resp = request_with_retry(client, "POST", BASE + endpoint,
                                  content=f"retKey=json&pageNo={page}")
        resp.raise_for_status()
        data = resp.json()
        total_pages = int(data.get("PAGE_COUNT", 1) or 1)
        for it in data.get("CARDGDS", []):
            code = (it.get("cardGdsNo") or "").strip()
            name = (it.get("cardGdsNm") or "").strip()
            if not code or not name or code in products:
                continue
            img = it.get("CARD_GDS_IMG") or ""
            image_url = (BASE + img) if img.startswith("/") else (img or None)
            affi = (it.get("affiFirmNo") or "").strip()
            mb = (it.get("mbNo") or "").strip()
            detail_url = (
                f"{BASE}/app/card/{detail_page}?gdsno={affi}&mbkNo={mb}"
                if affi else HOME_URL
            )
            products[code] = CardProduct(
                company=COMPANY, company_name=COMPANY_NAME, code=code, name=name,
                card_type=card_type, image_url=image_url, detail_url=detail_url,
                launch_date=None,  # BC 미노출
                description=(it.get("mainBnftCtnt") or "").strip() or None,
            )
        page += 1
    return list(products.values())


def scrape(known_launch: dict[str, str] | None = None) -> list[CardProduct]:
    results: dict[str, CardProduct] = {}
    # 폼인코딩 POST. ajax 헤더 + content-type 지정.
    with make_client(ajax=True, referer=HOME_URL) as client:
        client.headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        client.get(HOME_URL)  # 세션 쿠키(있으면)
        for card_type, endpoint, detail_page in _LISTS:
            items = _fetch_list(client, endpoint, card_type, detail_page)
            _log.info("BC카드 %s: %d건", card_type, len(items))
            for p in items:
                results.setdefault(p.code, p)
    _log.info("BC카드 합계 %d건", len(results))
    return list(results.values())
