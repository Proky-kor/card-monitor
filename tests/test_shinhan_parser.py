"""신한 목록 API 아이템 → CardProduct 매핑 단위테스트 (네트워크 없음)."""

from data.scrapers.shinhan import BASE, _parse_launch, _to_product

ITEM = {
    "cardProductEntryId": "202512230004",
    "cardProductEntryName": "신한카드 Simple Plan",
    "cardProductSummary": "실적 없이 한도 없이 Simple하게",
    "cardProductUrl": "/pconts/html/card/apply/credit/1237253_2207.html",
    "thumbnailImgUrl": "/pconts/static/images/card/plate/POGDXC_G3_v_f_s.webp",
    "cardPdStartDate": "2025-12-17T00:00:00",
}


def test_maps_all_fields():
    p = _to_product(ITEM, "신용")
    assert p is not None
    assert p.code == "202512230004"
    assert p.name == "신한카드 Simple Plan"
    assert p.card_type == "신용"
    assert p.launch_date == "2025-12-17"
    assert p.image_url == BASE + "/pconts/static/images/card/plate/POGDXC_G3_v_f_s.webp"
    assert p.detail_url == BASE + "/pconts/html/card/apply/credit/1237253_2207.html"
    assert p.description == "실적 없이 한도 없이 Simple하게"


def test_missing_code_or_name_returns_none():
    assert _to_product({"cardProductEntryName": "x"}, "신용") is None
    assert _to_product({"cardProductEntryId": "1"}, "신용") is None


def test_parse_launch_from_detail():
    html = '<li>카드 이용 시... 부가서비스는 카드 신규출시(2026.02.04) 이후 3년...</li>'
    assert _parse_launch(html) == "2026-02-04"


def test_parse_launch_absent():
    assert _parse_launch("<li>출시 정보 없음</li>") is None


def test_no_start_date_yields_none_launch():
    item = dict(ITEM)
    item.pop("cardPdStartDate")
    p = _to_product(item, "체크")
    assert p.launch_date is None
    assert p.card_type == "체크"
