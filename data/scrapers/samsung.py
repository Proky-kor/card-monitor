"""삼성카드 파서 (Playwright 목록 + httpx 상세).

삼성 카드안내는 Nuxt SPA. 목록 페이지에서 렌더된 카드 플레이트 이미지(`b_<코드>.png`,
신용=AAP·체크=ABP)로 카드 코드를 모으고, 상세 페이지의 __NUXT__ 블롭에 있는
`sellStrtdt:"YYYY-MM-DD"`(카드 출시일자)를 httpx로 파싱한다.
  신용 목록: PGHPPDCCardCardinfoRecommendPC001?tabIndex=9
  체크 목록: PGHPPCCCardCardinfoCheckcard001
  상세:      PGHPPCCCardCardinfoDetails001?code=<코드>
  이미지:    https://static11.samsungcard.com/wcms/home/scard/image/personal/b_<코드>.png
"""

import logging
import re
import time

from playwright.sync_api import sync_playwright

import config
from data.http import make_client
from data.models import CardProduct

_log = logging.getLogger(__name__)

COMPANY = "samsung"
COMPANY_NAME = "삼성카드"
BASE = "https://www.samsungcard.com"
CARDINFO = BASE + "/home/card/cardinfo/"
HOME_URL = CARDINFO + "PGHPPDCCardCardinfoRecommendPC001?tabIndex=9"
DETAIL_TMPL = CARDINFO + "PGHPPCCCardCardinfoDetails001?code={code}"
IMG_TMPL = "https://static11.samsungcard.com/wcms/home/scard/image/personal/b_{code}.png"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# (카드구분, 목록 URL)
_LISTS = [
    ("신용", CARDINFO + "PGHPPDCCardCardinfoRecommendPC001?tabIndex=9"),
    ("체크", CARDINFO + "PGHPPCCCardCardinfoCheckcard001"),
]

# 목록 페이지 렌더 후 카드 플레이트 이미지에서 코드+이름 추출
_EXTRACT_JS = r"""
() => {
  const out = []; const seen = {};
  document.querySelectorAll('img').forEach(img => {
    const s = img.currentSrc || img.getAttribute('src') || img.getAttribute('data-src') || '';
    const m = s.match(/scard\/image\/personal\/[a-z]_([A-Z]{2,3}[0-9]{3,})(?:_\d)?\.png/);
    if (!m) return;
    const code = m[1]; if (seen[code]) return; seen[code] = 1;
    let box = img.closest('li') || img.closest('[class*=card]') || img.parentElement;
    let name = img.getAttribute('alt') || '';
    for (let i = 0; i < 6 && box && !name; i++) {
      const t = box.querySelector('strong,[class*=name],[class*=tit],h3,h4,dt');
      if (t && t.innerText.trim()) name = t.innerText.trim();
      box = box.parentElement;
    }
    out.push({ code, name: name.replace(/\s+/g, ' ').slice(0, 60) });
  });
  return out;
}
"""
_SELL_RE = re.compile(r'sellStrtdt:"(\d{4}-\d{2}-\d{2})"')
# 상세 og:title (목록 이름이 비었을 때 폴백)
_OGTITLE_RE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"')


def _parse_detail(html: str) -> tuple[str | None, str | None]:
    """상세 HTML에서 (출시일, og:title 이름) 추출."""
    sm = _SELL_RE.search(html)
    launch = sm.group(1) if sm else None
    om = _OGTITLE_RE.search(html)
    name = om.group(1).strip() if om else None
    return launch, name


def scrape(known_launch: dict[str, str] | None = None) -> list[CardProduct]:
    known = known_launch or {}
    collected: list[tuple[str, str, str]] = []  # (card_type, code, list_name)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(user_agent=_UA, locale="ko-KR").new_page()
        for card_type, url in _LISTS:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(4000)
                for _ in range(12):
                    page.mouse.wheel(0, 6000)
                    page.wait_for_timeout(500)
                items = page.evaluate(_EXTRACT_JS)
            except Exception as e:
                _log.warning("삼성 목록 실패 %s: %s", card_type, e)
                items = []
            _log.info("삼성카드 %s: %d건", card_type, len(items))
            for it in items:
                if it.get("code"):
                    collected.append((card_type, it["code"], it.get("name") or ""))
        browser.close()

    # 코드 중복 제거(먼저 본 구분 유지)
    by_code: dict[str, tuple[str, str]] = {}
    for card_type, code, name in collected:
        by_code.setdefault(code, (card_type, name))

    _log.info("삼성카드 합계 %d건", len(by_code))
    out: list[CardProduct] = []
    with make_client(referer=BASE + "/") as client:
        for code, (card_type, list_name) in by_code.items():
            launch = known.get(code)
            name = list_name
            if not launch or not name:
                try:
                    r = client.get(DETAIL_TMPL.format(code=code))
                    r.raise_for_status()
                    d_launch, d_name = _parse_detail(r.text)
                    launch = launch or d_launch
                    name = name or d_name or code
                except Exception as e:
                    _log.warning("삼성 상세 실패 code=%s: %s", code, e)
                    name = name or code
                time.sleep(config.REQUEST_DELAY)
            out.append(CardProduct(
                company=COMPANY, company_name=COMPANY_NAME, code=code, name=name,
                card_type=card_type, image_url=IMG_TMPL.format(code=code),
                detail_url=DETAIL_TMPL.format(code=code), launch_date=launch, description=None,
            ))
    return out
