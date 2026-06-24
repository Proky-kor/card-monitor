"""우리 출시일 파싱 단위테스트 (네트워크 없음)."""

from data.scrapers.woori import _parse_real_launch, _sell_date


def test_sell_date_from_datetime():
    assert _sell_date("20260507000000") == "2026-05-07"


def test_sell_date_date_only():
    assert _sell_date("20211101") == "2021-11-01"


def test_sell_date_invalid():
    assert _sell_date(None) is None
    assert _sell_date("") is None
    assert _sell_date("2026") is None
    assert _sell_date("20269900000000") is None  # 잘못된 월


def test_parse_real_launch_basic():
    # rvwNoTxt 상품설명서 HTML에 박힌 실제 출시일
    html = '<strong>상품출시일 : 2026년 4월 16일</strong></p>'
    assert _parse_real_launch(html) == "2026-04-16"


def test_parse_real_launch_no_space_and_colon_variants():
    assert _parse_real_launch("상품출시일: 2025년 12월 1일") == "2025-12-01"
    assert _parse_real_launch("상품출시일：2025년 1월 9일") == "2025-01-09"


def test_parse_real_launch_missing():
    assert _parse_real_launch(None) is None
    assert _parse_real_launch("") is None
    assert _parse_real_launch("출시일 정보 없음") is None
    assert _parse_real_launch("상품출시일 : 2026년 13월 40일") is None  # 잘못된 월/일
