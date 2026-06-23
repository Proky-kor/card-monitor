"""신한카드 파서.

신한 홈페이지는 완전 SPA지만, 카드 목록 데이터는 공개 JSON API로 제공된다.
(발견은 Playwright로 했으나 런타임은 httpx만으로 충분.)

목록 API(GET): https://shapi.shinhancard.com/card-apply/search/v1.0/searchPagingFixedCardProductList
  params: pageSize(서버가 8로 고정), index(1-base 페이지), listID(카테고리)
  - 신용카드 listID=202001020012, 체크카드 listID=202001020001
응답: payload.{totalSize,totalPage,cardInformationList[]}
  item: cardProductEntryId(코드)·cardProductEntryName(상품명)·cardProductUrl(상세경로)
        ·thumbnailImgUrl/mainImgUrl(이미지)·cardPdStartDate(출시일)·cardProductSummary(요약)
"""

import logging
import time

import config
from data.http import make_client, request_with_retry
from data.models import CardProduct

_log = logging.getLogger(__name__)

COMPANY = "shinhan"
COMPANY_NAME = "신한카드"
BASE = "https://www.shinhancard.com"
HOME_URL = BASE + "/pconts/html/card/credit/CONFM70002/CONFM70002R01.html"  # 신용카드 목록
API = "https://shapi.shinhancard.com/card-apply/search/v1.0/searchPagingFixedCardProductList"

# (카드구분, listID) — 신한은 listID로 신용/체크가 정확히 분리됨
_LISTS = [
    ("신용", "202001020012"),
    ("체크", "202001020001"),
]
_PAGE_SIZE = 8  # 서버 고정값
_MAX_PAGES = 60  # 안전 상한


def _to_product(item: dict, card_type: str) -> CardProduct | None:
    code = (item.get("cardProductEntryId") or "").strip()
    name = (item.get("cardProductEntryName") or "").strip()
    if not code or not name:
        return None
    img = item.get("thumbnailImgUrl") or item.get("mainImgUrl") or ""
    image_url = BASE + img if img.startswith("/") else (img or None)
    detail = item.get("cardProductUrl") or ""
    detail_url = BASE + detail if detail.startswith("/") else (detail or None)
    start = item.get("cardPdStartDate") or ""
    launch_date = start[:10] if len(start) >= 10 else None
    return CardProduct(
        company=COMPANY,
        company_name=COMPANY_NAME,
        code=code,
        name=name,
        card_type=card_type,
        image_url=image_url,
        detail_url=detail_url,
        launch_date=launch_date,
        description=(item.get("cardProductSummary") or "").strip() or None,
    )


def _fetch_list(client, card_type: str, list_id: str) -> list[CardProduct]:
    products: dict[str, CardProduct] = {}
    total_pages = 1
    page = 1
    while page <= total_pages and page <= _MAX_PAGES:
        resp = request_with_retry(
            client, "GET", API,
            params={"pageSize": _PAGE_SIZE, "index": page, "listID": list_id},
            headers={"Origin": BASE},
        )
        resp.raise_for_status()
        payload = resp.json().get("payload", {})
        total_pages = int(payload.get("totalPage", 1) or 1)
        for item in payload.get("cardInformationList", []):
            p = _to_product(item, card_type)
            if p:
                products[p.code] = p
        page += 1
        time.sleep(config.REQUEST_DELAY)
    return list(products.values())


def scrape(known_launch: dict[str, str] | None = None) -> list[CardProduct]:
    """신한카드 신용+체크 전체 상품 (출시일이 목록 API에 포함되어 상세조회 불필요)."""
    results: dict[str, CardProduct] = {}
    with make_client(referer=BASE + "/") as client:
        for card_type, list_id in _LISTS:
            items = _fetch_list(client, card_type, list_id)
            _log.info("신한카드 %s: %d건", card_type, len(items))
            for p in items:
                results.setdefault(p.code, p)
    return list(results.values())
