"""우리카드 파서 (Playwright 인-브라우저 fetch).

우리카드 목록 API(`searchCrd02List.pwkjson`, POST)는 세션/토큰이 필요해 httpx 직호출이
막히지만, 카테고리 페이지를 연 뒤 브라우저 컨텍스트에서 fetch하면 전체를 받을 수 있다.
응답 item에 코드·이름·이미지가 있다.
  cdPrdCd(코드)·cdPrdNm(이름)·cdPdselStaDh(판매시작일시 YYYYMMDDHHMMSS)
  ·fileCoursWeb(이미지 경로, pc.wooricard.com + 경로)

출시일 주의: 목록의 cdPdselStaDh는 **판매시작일**이라 실제 **출시일**과 다르다.
실제 출시일은 상세 API(`searchCrdDtl.pwkjson`)의 rvwNoTxt(상품설명서 HTML)에
"상품출시일 : YYYY년 MM월 DD일" 형태로 들어 있어, 이를 우선 사용한다.
(신한·롯데와 동일한 '목록 판매일 ≠ 상세 출시일' 패턴.)
"""

import logging
import re

from playwright.sync_api import sync_playwright

from data.models import CardProduct

_log = logging.getLogger(__name__)

COMPANY = "woori"
COMPANY_NAME = "우리카드"
BASE = "https://pc.wooricard.com"
LIST_PAGE = BASE + "/dcpc/yh1/crd/crd02/H1CRD202S00.do?ctgrCd={ctgr}&hiPrdCtgrCd={hi}"
API_PATH = "/dcpc/yh1/crd/crd02/searchCrd02List.pwkjson"
DETAIL_PATH = "/dcpc/yh1/crd/crd01/searchCrdDtl.pwkjson"
HOME_URL = BASE + "/dcpc/yh1/crd/crd02/H1CRD202S00.do?ctgrCd=S000017&hiPrdCtgrCd=M110018"
# 카드별 상세페이지(자세히보기 랜딩). cdPrdCd로 해당 상품 상세로 직접 이동.
DETAIL_PAGE = BASE + "/dcpc/yh1/crd/crd01/H1CRD101S02.do?cdPrdCd={code}"
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

# 상세 API를 코드별로 순회 fetch → rvwNoTxt 원문만 반환(파싱은 파이썬에서).
# 과도한 연속 요청을 피하기 위해 각 요청 사이 120ms 지연.
_DETAIL_JS = """
async (codes) => {
  const out = {};
  for (const code of codes) {
    try {
      const body = JSON.stringify({ crd01DtlVo: { cdPrdCd: code } });
      const r = await fetch('%s', { method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' }, body });
      const j = await r.json();
      out[code] = (((j.resultVo || {}).crd01DtlVo || {}).rvwNoTxt) || '';
    } catch (e) { out[code] = ''; }
    await new Promise(res => setTimeout(res, 120));
  }
  return out;
}
""" % DETAIL_PATH

# rvwNoTxt(상품설명서 HTML)에서 "상품출시일 : 2026년 4월 16일" 추출.
_REAL_LAUNCH_RE = re.compile(
    r"상품출시일\s*[:：]?\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")


def _sell_date(raw: str | None) -> str | None:
    """cdPdselStaDh 'YYYYMMDDHHMMSS' → 'YYYY-MM-DD' 또는 None (판매시작일 폴백용)."""
    if not raw or len(raw) < 8 or not raw[:8].isdigit():
        return None
    y, mo, d = raw[:4], raw[4:6], raw[6:8]
    if not ("01" <= mo <= "12" and "01" <= d <= "31"):
        return None
    return f"{y}-{mo}-{d}"


def _parse_real_launch(rvw_html: str | None) -> str | None:
    """rvwNoTxt에서 '상품출시일 : YYYY년 MM월 DD일' → 'YYYY-MM-DD' 또는 None."""
    if not rvw_html:
        return None
    m = _REAL_LAUNCH_RE.search(rvw_html)
    if not m:
        return None
    y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y}-{mo:02d}-{d:02d}"


def scrape(known_launch: dict[str, str] | None = None) -> list[CardProduct]:
    known = known_launch or {}
    raw: dict[str, dict] = {}  # code -> {name, image_url, card_type, desc, sell}
    detail_launch: dict[str, str | None] = {}
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

        for it in items:
            code = (it.get("cdPrdCd") or "").strip()
            name = (it.get("cdPrdNm") or "").strip()
            if not code or not name or code in raw:  # 혜택태그 중복 제거
                continue
            img = it.get("fileCoursWeb") or ""
            image_url = (BASE + img) if img.startswith("/") else (img or None)
            raw[code] = {
                "name": name,
                "image_url": image_url,
                "card_type": _CFCD_TYPE.get(it.get("cdPrdCfcd"), ""),
                "desc": (it.get("cdPrdSlgTxt") or "").strip() or None,
                "sell": _sell_date(it.get("cdPdselStaDh")),
            }

        # 출시일 미확보 코드만 상세 조회(known_launch 캐싱 → 최초만 전체)
        missing = [c for c in raw if c not in known]
        if missing:
            try:
                rvw_map = page.evaluate(_DETAIL_JS, missing)
            except Exception as e:
                _log.warning("우리 상세 fetch 실패(판매시작일 폴백): %s", e)
                rvw_map = {}
            for code, rvw in rvw_map.items():
                detail_launch[code] = _parse_real_launch(rvw)
        browser.close()

    out: list[CardProduct] = []
    enriched = 0
    for code, d in raw.items():
        # 우선순위: 기수집 출시일(known) → 상세 상품출시일 → 판매시작일 폴백
        launch = known.get(code) or detail_launch.get(code) or d["sell"]
        if detail_launch.get(code):
            enriched += 1
        out.append(CardProduct(
            company=COMPANY, company_name=COMPANY_NAME, code=code, name=d["name"],
            card_type=d["card_type"], image_url=d["image_url"],
            detail_url=DETAIL_PAGE.format(code=code),
            launch_date=launch, description=d["desc"],
        ))
    _log.info("우리카드 합계 %d건 (상세 출시일 보정 %d건)", len(out), enriched)
    return out
