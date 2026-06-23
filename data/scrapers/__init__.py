"""카드사 파서 레지스트리.

각 파서는 scrape() -> list[CardProduct] 를 제공하는 모듈.
새 카드사 추가: 모듈 작성 후 REGISTRY에 등록.
"""

from collections.abc import Callable

from data.models import CardProduct, DiscontinueNotice
from data.scrapers import bccard, hana, hyundai, kb, lotte, samsung, shinhan, woori

# 회사키 -> (표시명, scrape 함수)
REGISTRY: dict[str, tuple[str, Callable[..., list[CardProduct]]]] = {
    shinhan.COMPANY: (shinhan.COMPANY_NAME, shinhan.scrape),
    lotte.COMPANY: (lotte.COMPANY_NAME, lotte.scrape),
    hyundai.COMPANY: (hyundai.COMPANY_NAME, hyundai.scrape),
    kb.COMPANY: (kb.COMPANY_NAME, kb.scrape),
    samsung.COMPANY: (samsung.COMPANY_NAME, samsung.scrape),
    woori.COMPANY: (woori.COMPANY_NAME, woori.scrape),
    bccard.COMPANY: (bccard.COMPANY_NAME, bccard.scrape),
    hana.COMPANY: (hana.COMPANY_NAME, hana.scrape),
}

# 회사키 -> 단종/발급중단 공지 scrape 함수 (지원하는 회사만)
NOTICE_REGISTRY: dict[str, Callable[[], list[DiscontinueNotice]]] = {
    lotte.COMPANY: lotte.scrape_notices,
}

# 회사키 -> 카드사 홈페이지 바로가기 링크 (home: 카드 목록)
COMPANY_META: dict[str, dict[str, str]] = {
    shinhan.COMPANY: {"name": shinhan.COMPANY_NAME, "home": shinhan.HOME_URL},
    lotte.COMPANY: {"name": lotte.COMPANY_NAME, "home": lotte.HOME_URL},
    hyundai.COMPANY: {"name": hyundai.COMPANY_NAME, "home": hyundai.HOME_URL},
    kb.COMPANY: {"name": kb.COMPANY_NAME, "home": kb.HOME_URL},
    samsung.COMPANY: {"name": samsung.COMPANY_NAME, "home": samsung.HOME_URL},
    woori.COMPANY: {"name": woori.COMPANY_NAME, "home": woori.HOME_URL},
    bccard.COMPANY: {"name": bccard.COMPANY_NAME, "home": bccard.HOME_URL},
    hana.COMPANY: {"name": hana.COMPANY_NAME, "home": hana.HOME_URL},
}


def available() -> list[str]:
    return list(REGISTRY.keys())
