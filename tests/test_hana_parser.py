"""하나 출시일 파싱 + 개별 상세 URL 단위테스트 (네트워크 없음)."""

from data.scrapers.hana import BASE, _detail_url, _parse_launch_date


def test_parse_launch_date_dot():
    assert _parse_launch_date("출시 시기 : 2025.02.17 준법심의 A-25-0312") == "2025-02-17"


def test_parse_launch_date_zero_pad():
    assert _parse_launch_date("출시 시기 2024.2.1") == "2024-02-01"


def test_parse_launch_date_colon_fullwidth_and_dash():
    assert _parse_launch_date("출시 시기： 2026-6-9") == "2026-06-09"


def test_parse_launch_date_absent():
    assert _parse_launch_date("연회비 및 부가서비스 안내") is None


def test_detail_url_uses_cd_no_zero_padded():
    # goCardInfo2(CD_NO) 재현: mID=PI41+CD_NO(6자리 0채움)+P, CD_PD_SEQ=CD_NO
    url = _detail_url("18394")
    assert url == f"{BASE}/OPI41000000D.web?schID=pcd&mID=PI41018394P&CD_PD_SEQ=18394"


def test_detail_url_short_code_zero_pad():
    assert "mID=PI41000093P" in _detail_url("93")
    assert "CD_PD_SEQ=93" in _detail_url("93")


def test_detail_url_non_numeric_falls_back_to_list():
    assert _detail_url("ABC") == f"{BASE}/OPI31000000D.web?schID=pcd&mID=OPI31000005P&CT_ID=241704030444153"
