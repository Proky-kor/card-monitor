"""롯데 파서 단위테스트 — 네트워크 없이 HTML 조각만으로 검증."""

from data.scrapers.lotte import _parse_fragment, _parse_launch_date

FRAGMENT = """
<ul>
  <li><a onclick="GoDet('P14312-A14312');return false;" href="#" role="button">
    <span class="img typeH">
      <img src="//image.lottecard.co.kr/UploadFiles/ecenterPath/cdInfo/ecenterCdInfoP14312-A14312_nm1_v.png" alt="" onerror="this.src='//image.lottecard.co.kr/webapp/pc/images/card/card_noimg.png'">
    </span>
    <b class="tit">롯데마트&amp;MAXX 카드</b>
    <span class="txt">롯데마트&amp;MAXX 최대 10% 할인</span>
  </a></li>
  <li><a onclick="GoDet('P15608-A15608');return false;" href="#" role="button">
    <span class="img">
      <img src="//image.lottecard.co.kr/webapp/pc/images/card/card_noimg.png" alt="">
    </span>
    <b class="tit">디지로카 Golf</b>
    <span class="txt">골프 최대 7% 캐시백</span>
  </a></li>
</ul>
"""


def test_parses_code_name_image_desc():
    products = _parse_fragment(FRAGMENT, "신용")
    assert len(products) == 2
    p = products[0]
    assert p.code == "P14312-A14312"
    assert p.name == "롯데마트&MAXX 카드"
    assert p.card_type == "신용"
    assert p.description == "롯데마트&MAXX 최대 10% 할인"
    assert p.image_url == (
        "https://image.lottecard.co.kr/UploadFiles/ecenterPath/cdInfo/"
        "ecenterCdInfoP14312-A14312_nm1_v.png"
    )
    assert p.detail_url and "P14312-A14312" in p.detail_url


def test_noimg_placeholder_becomes_none():
    products = _parse_fragment(FRAGMENT, "신용")
    assert products[1].name == "디지로카 Golf"
    assert products[1].image_url is None  # card_noimg 플레이스홀더는 무시


def test_empty_fragment_yields_nothing():
    assert _parse_fragment("<ul></ul>", "체크") == []


def test_parse_launch_date():
    html = '<ul><li>카드출시일 : 2011년 09월 26일</li></ul>'
    assert _parse_launch_date(html) == "2011-09-26"


def test_parse_launch_date_single_digit_padded():
    assert _parse_launch_date("카드출시일 : 2021년 6월 2일") == "2021-06-02"


def test_parse_launch_date_absent():
    assert _parse_launch_date("<div>출시일 정보 없음</div>") is None
