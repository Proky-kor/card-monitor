"""우리카드 파서 (Playwright 인-브라우저 fetch).

우리카드 목록 API(`searchCrd02List.pwkjson`, POST)는 세션/토큰이 필요해 httpx 직호출이
막히지만, 카테고리 페이지를 연 뒤 브라우저 컨텍스트에서 fetch하면 전체를 받을 수 있다.
응답 item에 코드·이름·출시일·이미지가 모두 있어 상세 조회가 불필요하다.
  cdPrdCd(코드)·cdPrdNm(이름)·cdPdselStaDh(판매시작일시 YYYYMMDDHHMMSS=출시일)
  ·fileCoursWeb(이미지 경로, pc.wooricard.com + 경로)
카테고리(ctgrCd, hiPrdCtgrCd): 프리미엄·신용·체크·제휴.
"""

import logging

from playwright.sync_api import sync_playwright

from data.models import CardProduct

_log = logging.getLogger(__name__)

COMPANY = "woori"
COMPANY_NAME = "우리카드"
BASE = "https://pc.wooricard.com"
LIST_PAGE = BASE + "/dcpc/yh1/crd/crd02/H1CRD202S00.do?ctgrCd={ctgr}&hiPrdCtgrCd={hi}"
API_PATH = "/dcpc/yh1/crd/crd02/searchCrd02List.pwkjson"
HOME_URL = BASE + "/dcpc/yh1/crd/crd02/H1CRD202S00.do?ctgrCd=S000017&hiPrdCtgrCd=M110018"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# ctgrCd(혜택 하위 카테고리)를 비우면 전체 카드가 반환된다(혜택태그 중복 포함 → 코드로 dedupe).
# 카드구분은 cdPrdCfcd로 판별: '2'=체크, '1'=신용, 그 외=기타.
_CFCD_TYPE = {"1": "신용", "2": "체크"}

# 브라우저 컨텍스트에서 전체 목록 fetch (ctgrCd 빈값 + recordCnt 크게)
_FETCH_JS = """
async () => {
  const body = JSON.stringify({ crd02Vo: {
    recordCnt: 3000, nowPage: 1, ctgrCd: '', hiPrdCtgrCd: 'M110018', sortDiv: 'B' } });
  const r = await fetch('%s', { method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' }, body });
  const j = await r.json();
  return (j.crd02ResultVo || {}).crd02VoList || [];
}
""" % API_PATH


def _launch_date(raw: str | None) -> str | None:
    """cdPdselStaDh 'YYYYMMDDHHMMSS' → 'YYYY-MM-DD' 또는 None."""
    if not raw or len(raw) < 8 or not raw[:8].isdigit():
        return None
    y, mo, d = raw[:4], raw[4:6], raw[6:8]
    if not ("01" <= mo <= "12" and "01" <= d <= "31"):
        return None
    return f"{y}-{mo}-{d}"


def scrape(known_launch: dict[str, str] | None = None) -> list[CardProduct]:
    by_code: dict[str, CardProduct] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(user_agent=_UA, locale="ko-KR").new_page()
        # networkidle은 추적 스크립트로 안 끝남 → domcontentloaded + 대기로 세션 확보
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        try:
            items = page.evaluate(_FETCH_JS)
        except Exception as e:
            _log.warning("우리 목록 fetch 실패: %s", e)
            items = []
        browser.close()

    for it in items:
        code = (it.get("cdPrdCd") or "").strip()
        name = (it.get("cdPrdNm") or "").strip()
        if not code or not name or code in by_code:  # 혜택태그 중복 제거
            continue
        img = it.get("fileCoursWeb") or ""
        image_url = (BASE + img) if img.startswith("/") else (img or None)
        by_code[code] = CardProduct(
            company=COMPANY, company_name=COMPANY_NAME, code=code, name=name,
            card_type=_CFCD_TYPE.get(it.get("cdPrdCfcd"), ""),
            image_url=image_url, detail_url=HOME_URL,
            launch_date=_launch_date(it.get("cdPdselStaDh")),
            description=(it.get("cdPrdSlgTxt") or "").strip() or None,
        )
    _log.info("우리카드 합계 %d건", len(by_code))
    return list(by_code.values())
