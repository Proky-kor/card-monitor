"""KB국민카드 파서 (Playwright DOM 스크래핑).

KB는 깨끗한 카드목록 API가 없고(오픈API는 제휴·인증 전용), 출시일도 미공개.
모바일 "카드 한눈에보기"가 카드들을 DOM 렌더한다.
  목록: https://m.kbcard.com/CRD/DVIEW/MCAM0101
  카드: a/li onclick="fnVwCardDetail('<코드>')" + h3(이름) + img product/<코드>_img.png
  이미지: https://img1.kbcard.com/ST/img/cxc/kbcard/upload/img/product/<코드>_img.png
  상세: https://card.kbcard.com/CRD/DVIEW/HCAMCXPRICAC0076?cooperationcode=<코드>&mainCC=a
출시일은 KB가 노출하지 않으므로 launch_date=None (신규/출시정렬 미지원).
"""

import logging
import re
import time

from playwright.sync_api import sync_playwright

import config
from data.http import make_client
from data.models import CardProduct

_log = logging.getLogger(__name__)
# 상세 부가서비스 안내의 출시일 — 세 형식 모두 지원:
#  ① "...카드(2025.03.31 출시)"          (날짜 먼저, 점 구분)
#  ② "(2009년 11월12일 출시)"            (날짜 먼저, 한글, 월/일 공백 무관)
#  ③ "신규출시(2007년 3월 8일) 이후..."   (출시 먼저, 한글)
_LAUNCH_RE_DOT = re.compile(r"\(\s*(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*출시\s*\)")
_LAUNCH_RE_KORPRE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*출시")
_LAUNCH_RE_KOR = re.compile(r"출시\s*\(?\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")

COMPANY = "kb"
COMPANY_NAME = "KB국민카드"
HOME_URL = "https://card.kbcard.com/CRD/DVIEW/HCAM0101"
IMG_TMPL = "https://img1.kbcard.com/ST/img/cxc/kbcard/upload/img/product/{code}_img.png"
DETAIL_TMPL = "https://card.kbcard.com/CRD/DVIEW/HCAMCXPRICAC0076?cooperationcode={code}&mainCC=a"
# (카드구분, 목록 베이스 URL) — KB는 URL로 신용/체크가 정확히 분리됨.
# 목록은 혜택 카테고리(cateIdx)별로 나뉘므로 cateIdx를 순회해 합집합으로 전체를 모은다.
_LISTS = [
    ("신용", "https://card.kbcard.com/CRD/DVIEW/HCAMCXPRICAC0047"),
    ("체크", "https://card.kbcard.com/CRD/DVIEW/HCAMCXPRICAC0056"),
]
_MAX_CATE = 16        # cateIdx 안전 상한
_CATE_EMPTY_STOP = 3  # 연속 N개 카테고리가 신규 0이면 중단
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 목록 페이지에서 goDetail('코드') + 카드명(h3.tit-dep4) 추출
_EXTRACT_JS = r"""
() => {
  const out = []; const seen = {};
  document.querySelectorAll('a[onclick*=goDetail]').forEach(a => {
    const m = (a.getAttribute('onclick') || '').match(/goDetail\(\s*['"]([0-9]+)/);
    if (!m) return;
    const code = m[1]; if (seen[code]) return; seen[code] = 1;
    const box = a.closest('.card-box__item') || a.closest('li') || a;
    const h = box.querySelector('h3,[class*=tit],strong');
    const img = box.querySelector('img');
    let name = (h ? h.innerText : '') || (img ? img.getAttribute('alt') : '') || '';
    out.push({ code, name: name.trim().replace(/\s+/g, ' ').slice(0, 60) });
  });
  return out;
}
"""


def _parse_launch_date(html: str) -> str | None:
    """상세페이지에서 출시일 → 'YYYY-MM-DD' 또는 None (두 형식 지원, 순수 함수)."""
    for rx in (_LAUNCH_RE_DOT, _LAUNCH_RE_KORPRE, _LAUNCH_RE_KOR):
        for m in rx.finditer(html):
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mo <= 12 and 1 <= d <= 31:  # 00.00 등 오류 데이터 배제
                return f"{y}-{mo:02d}-{d:02d}"
    return None


def _fetch_launch_date(client, code: str) -> str | None:
    try:
        r = client.get(DETAIL_TMPL.format(code=code))
        r.raise_for_status()
    except Exception as e:
        _log.warning("KB 출시일 조회 실패 code=%s: %s", code, e)
        return None
    return _parse_launch_date(r.text)


def _collect_list(page, base_url: str) -> dict[str, str]:
    """한 목록(신용/체크)의 카테고리(cateIdx)를 순회해 {code: name} 합집합 수집."""
    found: dict[str, str] = {}
    empty = 0
    for ci in range(1, _MAX_CATE + 1):
        try:
            page.goto(f"{base_url}?pageNo=1&cateIdx={ci}",
                      wait_until="networkidle", timeout=40000)
            page.wait_for_timeout(1500)
            for _ in range(4):
                page.mouse.wheel(0, 5000)
                page.wait_for_timeout(400)
            items = page.evaluate(_EXTRACT_JS)
        except Exception as e:
            _log.warning("KB 목록 실패 %s cateIdx=%d: %s", base_url[-4:], ci, e)
            items = []
        new = 0
        for it in items:
            c, n = it.get("code"), it.get("name")
            if c and n and c not in found:
                found[c] = n
                new += 1
        if new == 0:
            empty += 1
            if empty >= _CATE_EMPTY_STOP:
                break
        else:
            empty = 0
    return found


def scrape(known_launch: dict[str, str] | None = None) -> list[CardProduct]:
    known = known_launch or {}
    collected: list[tuple[str, str, str]] = []  # (card_type, code, name)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(user_agent=_UA, locale="ko-KR").new_page()
        for card_type, base in _LISTS:
            found = _collect_list(page, base)
            _log.info("KB국민카드 %s: %d건", card_type, len(found))
            for code, name in found.items():
                collected.append((card_type, code, name))
        browser.close()

    # 코드 기준 중복 제거(신용 우선)
    by_code: dict[str, tuple[str, str]] = {}
    for card_type, code, name in collected:
        by_code.setdefault(code, (card_type, name))

    _log.info("KB국민카드 합계 %d건", len(by_code))
    out: list[CardProduct] = []
    # 출시일은 상세(SSR) httpx 조회, 모르는 코드만(불변, known 캐싱)
    with make_client(referer="https://card.kbcard.com/") as client:
        for code, (card_type, name) in by_code.items():
            launch = known.get(code)
            if not launch:
                launch = _fetch_launch_date(client, code)
                time.sleep(config.REQUEST_DELAY)
            out.append(CardProduct(
                company=COMPANY, company_name=COMPANY_NAME, code=code, name=name,
                card_type=card_type, image_url=IMG_TMPL.format(code=code),
                detail_url=DETAIL_TMPL.format(code=code), launch_date=launch, description=None,
            ))
    return out
