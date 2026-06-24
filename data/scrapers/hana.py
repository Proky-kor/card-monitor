"""하나카드 파서 (httpx, EUC-KR).

하나 홈페이지 일부(OPI41000000D.web)는 보안프로그램 안티봇이 뜨지만, 카드 목록 AJAX
`POST /OPI31000000D.ajax`(폼인코딩, **응답이 EUC-KR**)는 httpx로 직접 호출된다.
응답 dataMap.CARD_LIST.data[] 에 카드들:
  CD_NM(이름)·CD_NO(코드)·LIST_IMG_TYPE_IMG(이미지 경로)·CD_DESC_TXT(설명)
카테고리(CT_ID): 신용/체크/제휴. (출시일은 목록에 없음 → launch_date=None.)
"""

import json
import logging
import re

from data.http import make_client, request_with_retry
from data.models import CardProduct

_log = logging.getLogger(__name__)

COMPANY = "hana"
COMPANY_NAME = "하나카드"
BASE = "https://www.hanacard.co.kr"
API = BASE + "/OPI31000000D.ajax"
LIST_PAGE = BASE + "/OPI31000000D.web?schID=pcd&mID=OPI31000005P&CT_ID={ct}"
HOME_URL = LIST_PAGE.format(ct="241704030444153")
# 카드별 상세페이지(자세히보기 랜딩). 응답 item의 CD_ID(상품 고유 ID)로 직접 이동.
DETAIL_PAGE = BASE + "/OPI41000000D.web?CD_ID={cd_id}&schID=pcd&mID=OPI41000000C"

# (카드구분, CT_ID)
_CATEGORIES = [
    ("신용", "241704030444153"),
    ("체크", "241704050328506"),
    ("신용", "241704030444279"),  # 제휴(신용계열)
]
_TAG_RE = re.compile(r"<[^>]+>")


def _body(ct: str) -> str:
    return (f"schID=pcd&mID=OPM05000000C&PAGE=&SORT_KEY=&SORT_TYPE="
            f"&PAGE_TYPE=&CT_ID={ct}&ST_ID=")


def scrape(known_launch: dict[str, str] | None = None) -> list[CardProduct]:
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
                cd_id = (it.get("CD_ID") or "").strip()
                detail = DETAIL_PAGE.format(cd_id=cd_id) if cd_id else LIST_PAGE.format(ct=ct)
                by_code[code] = CardProduct(
                    company=COMPANY, company_name=COMPANY_NAME, code=code, name=name,
                    card_type=card_type, image_url=image_url,
                    detail_url=detail,
                    launch_date=None, description=desc,
                )
    _log.info("하나카드 합계 %d건", len(by_code))
    return list(by_code.values())
