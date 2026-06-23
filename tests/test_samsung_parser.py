"""삼성 상세 파싱 단위테스트 (네트워크 없음)."""

from data.scrapers.samsung import IMG_TMPL, _parse_detail


def test_parse_detail_launch_from_nuxt():
    html = '...,info:L,etc:a},sellStrtdt:"2025-07-02",sellBgdAmt:0,...'
    launch, _ = _parse_detail(html)
    assert launch == "2025-07-02"


def test_parse_detail_no_launch():
    launch, name = _parse_detail("<html>no data</html>")
    assert launch is None and name is None


def test_image_url_from_code():
    assert IMG_TMPL.format(code="AAP1877").endswith("personal/b_AAP1877.png")
