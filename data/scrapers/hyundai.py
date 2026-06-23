"""현대카드 파서 (Playwright DOM 스크래핑).

현대 홈페이지는 JS 렌더(Handlebars/Vue) SPA라 httpx로는 목록·출시일이 안 나온다.
전체 카드 목록: https://www.hyundaicard.com/cpc/ma/CPCMA0101_01.hc ("전체 카드 신청")
  - 각 카드: <a onclick="goCardDetail('<코드>')"> + 카드명 + 이미지
  - 이미지: https://img.hyundaicard.com/img/com/card/card_<코드>_h.png (코드에서 도출)
  - 상세: /cpc/cr/CPCCR0201_01.hc?cardWcd=<코드> 본문 "신규 출시(YYYY년 MM월 DD일)"
출시일은 상세 렌더가 필요해 known_launch에 없는 카드만 조회(불변이라 1회성).
"""

import logging
import re
import time

from playwright.sync_api import sync_playwright

import config
from data.models import CardProduct

_log = logging.getLogger(__name__)

COMPANY = "hyundai"
COMPANY_NAME = "현대카드"
BASE = "https://www.hyundaicard.com"
LIST_URL = BASE + "/cpc/ma/CPCMA0101_01.hc"
HOME_URL = LIST_URL
DETAIL_TMPL = BASE + "/cpc/cr/CPCCR0201_01.hc?cardWcd={code}"
IMG_TMPL = "https://img.hyundaicard.com/img/com/card/card_{code}_h.png"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_LAUNCH_RE = re.compile(r"출시\s*\(?\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")

# 목록 페이지에서 카드 코드/이름을 뽑는 JS (goCardDetail 기준)
_EXTRACT_JS = r"""
() => {
  const out = []; const seen = {};
  document.querySelectorAll('a').forEach(a => {
    const m = (a.getAttribute('onclick') || '').match(/goCardDetail\(\s*['"]([A-Za-z0-9]+)/);
    if (!m) return;
    const code = m[1]; if (seen[code]) return; seen[code] = 1;
    const box = a.closest('li') || a.parentElement;
    let name = '';
    if (box) {
      const el = box.querySelector('[class*=name],[class*=tit],strong');
      name = (el ? el.innerText : '').trim();
      if (!name) name = (box.innerText || '').trim().split('\n')[0];
    }
    out.push({ code, name: name.replace(/\s+/g, ' ').slice(0, 60) });
  });
  return out;
}
"""


def _parse_launch_date(body_text: str) -> str | None:
    m = _LAUNCH_RE.search(body_text)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def scrape(known_launch: dict[str, str] | None = None) -> list[CardProduct]:
    known = known_launch or {}
    results: list[CardProduct] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=_UA, locale="ko-KR")
        page = ctx.new_page()
        # 현대 페이지는 추적 스크립트로 networkidle이 안 끝남 → domcontentloaded + 카드 등장 대기
        page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_selector("a[onclick*=goCardDetail]", timeout=30000)
        except Exception as e:
            _log.warning("현대 카드 셀렉터 대기 실패: %s", e)
        page.wait_for_timeout(2000)
        for _ in range(6):
            page.mouse.wheel(0, 6000)
            page.wait_for_timeout(700)
        raw = page.evaluate(_EXTRACT_JS)
        _log.info("현대카드 목록 %d건", len(raw))

        # 출시일 모르는 카드만 상세 렌더로 보강
        detail = ctx.new_page()
        for item in raw:
            code = item["code"]
            name = item["name"]
            if not code or not name:
                continue
            launch = known.get(code)
            if not launch:
                try:
                    detail.goto(DETAIL_TMPL.format(code=code),
                                wait_until="domcontentloaded", timeout=40000)
                    detail.wait_for_timeout(1500)
                    launch = _parse_launch_date(detail.inner_text("body"))
                except Exception as e:  # 한 건 실패는 무시
                    _log.warning("현대 출시일 조회 실패 code=%s: %s", code, e)
                    launch = None
                time.sleep(config.REQUEST_DELAY)
            results.append(CardProduct(
                company=COMPANY,
                company_name=COMPANY_NAME,
                code=code,
                name=name,
                card_type="",
                image_url=IMG_TMPL.format(code=code),
                detail_url=DETAIL_TMPL.format(code=code),
                launch_date=launch,
                description=None,
            ))
        browser.close()
    return results
