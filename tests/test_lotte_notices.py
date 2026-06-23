"""롯데 단종/발급중단 공지 파싱 + 상품 매칭 단위테스트 (네트워크 없음)."""

from data.scrapers.lotte import _extract_card_names, _parse_notice_fragment
from services.collector import match_notice_to_products

NOTICE_FRAGMENT = """
<ul>
  <li><a href="#" onclick="javascript:DoDetail('3587')">
    <strong class="tit">디지로카 Travel, 디지로카 Travel 프리미엄 카드 발급 중단 안내</strong>
    <span class="date">2026.06.04</span>
  </a></li>
  <li><a href="#" onclick="javascript:DoDetail('3567')">
    <strong class="tit">춘식이모바일로카 발급 중단 안내</strong>
    <span class="date">2026.03.20</span>
  </a></li>
</ul>
"""


class _Row(dict):
    def __getitem__(self, k):
        return super().__getitem__(k)


def _prod(code, name):
    return {"code": code, "name": name}


def test_parse_notice_fragment():
    notices = _parse_notice_fragment(NOTICE_FRAGMENT)
    assert len(notices) == 2
    n0 = notices[0]
    assert n0.notice_id == "3587"
    assert n0.notice_date is None  # 단종 날짜는 파싱하지 않음 (기능 제외)
    assert "디지로카 Travel" in n0.title
    assert n0.url.endswith("newsSeq=3587")


def test_extract_card_names_splits_and_strips_suffix():
    names = _extract_card_names("디지로카 Travel, 디지로카 Travel 프리미엄 카드 발급 중단 안내")
    assert "디지로카 Travel" in names
    assert any("프리미엄" in n for n in names)


def test_match_handles_spacing_difference():
    # 공지 '춘식이모바일로카' ↔ 상품 '춘식이 모바일로카' (공백 차이) 매칭
    notices = _parse_notice_fragment(NOTICE_FRAGMENT)
    chunsik = [n for n in notices if "춘식이" in n.title][0]
    products = [_prod("P1", "춘식이 모바일로카"), _prod("P2", "전혀 다른 카드")]
    codes = match_notice_to_products(chunsik.card_names, products)
    assert codes == ["P1"]


def test_match_no_false_positive_on_short_token():
    products = [_prod("P9", "LOCA")]
    # 너무 짧은 후보는 매칭하지 않음
    assert match_notice_to_products(("AB",), products) == []
