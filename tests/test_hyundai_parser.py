"""현대 출시일 파싱 단위테스트 (네트워크 없음)."""

from data.scrapers.hyundai import IMG_TMPL, _parse_launch_date


def test_parse_launch_date_with_prefix():
    assert _parse_launch_date("신규 출시(2025년 12월 24일) 이후 발급분") == "2025-12-24"


def test_parse_launch_date_plain():
    assert _parse_launch_date("출시 2026년 6월 16일") == "2026-06-16"


def test_parse_launch_date_absent():
    assert _parse_launch_date("출시일 정보가 없습니다") is None


def test_image_url_derivable_from_code():
    assert IMG_TMPL.format(code="TBE4").endswith("card_TBE4_h.png")
