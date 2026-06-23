"""우리 출시일 파싱 단위테스트 (네트워크 없음)."""

from data.scrapers.woori import _launch_date


def test_launch_date_from_datetime():
    assert _launch_date("20260507000000") == "2026-05-07"


def test_launch_date_date_only():
    assert _launch_date("20211101") == "2021-11-01"


def test_launch_date_invalid():
    assert _launch_date(None) is None
    assert _launch_date("") is None
    assert _launch_date("2026") is None
    assert _launch_date("20269900000000") is None  # 잘못된 월
