"""KB 출시일 파싱 단위테스트 (네트워크 없음)."""

from data.scrapers.kb import IMG_TMPL, _parse_launch_date


def test_parse_launch_date():
    html = 'KB WE:SH All⁺카드(2025.03.31 출시)를 이용하는 경우'
    assert _parse_launch_date(html) == "2025-03-31"


def test_parse_launch_date_single_digit():
    assert _parse_launch_date("카드(2026.6.2 출시)") == "2026-06-02"


def test_parse_launch_date_korean_format():
    # "신규출시(2007년 3월 8일) 이후..." 형식도 지원
    html = "부가 서비스는 카드 신규출시(2007년 3월 8일) 이후 1년 이상 유지됩니다."
    assert _parse_launch_date(html) == "2007-03-08"


def test_parse_launch_date_korean_date_before_chulsi():
    # "카드(2009년 11월12일 출시)" — 날짜 먼저, 월/일 공백 없음
    assert _parse_launch_date("스타트럭카드(2009년 11월12일 출시)를 이용") == "2009-11-12"


def test_parse_launch_date_absent():
    assert _parse_launch_date("출시일 정보 없음") is None


def test_image_url_from_code():
    assert IMG_TMPL.format(code="09297").endswith("product/09297_img.png")
