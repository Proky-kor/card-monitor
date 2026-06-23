"""Teams 알림 — 신규 카드 상품 감지 시 웹훅으로 전송.

CARD_TEAMS_WEBHOOK_URL(.env)이 설정돼 있을 때만 동작(없으면 조용히 skip).
Teams Incoming Webhook(MessageCard) 및 Power Automate('HTTP 요청 수신') 양쪽에서
읽을 수 있도록, MessageCard 포맷 + 평문 text + 구조화 cards 를 함께 보낸다.
"""

import logging

import config
from data.http import make_client
from data.models import CardProduct

_log = logging.getLogger(__name__)
_MAX_LIST = 40  # 메시지에 나열할 최대 건수


def _build_payload(products: list[CardProduct]) -> dict:
    n = len(products)
    shown = products[:_MAX_LIST]
    lines = []
    for p in shown:
        date = f" · 출시 {p.launch_date}" if p.launch_date else ""
        lines.append(f"- [{p.company_name}] {p.name}{date}")
    if n > _MAX_LIST:
        lines.append(f"… 외 {n - _MAX_LIST}건")
    text = "\n".join(lines)
    title = f"신규 카드 상품 {n}건 감지"
    return {
        # MessageCard (Teams Incoming Webhook 호환)
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": title,
        "themeColor": "4C8DFF",
        "title": title,
        "text": text.replace("\n", "  \n"),
        # 구조화 데이터 (Power Automate에서 파싱용)
        "newCount": n,
        "cards": [
            {
                "company": p.company_name,
                "name": p.name,
                "launchDate": p.launch_date,
                "url": p.detail_url,
                "image": p.image_url,
            }
            for p in shown
        ],
    }


def notify_new_products(products: list[CardProduct]) -> bool:
    """신규 상품을 Teams로 알림. 전송 성공 시 True, 미설정/실패 시 False."""
    if not products:
        return False
    if not config.TEAMS_WEBHOOK_URL:
        _log.info("Teams 웹훅 미설정 — 알림 skip (신규 %d건)", len(products))
        return False
    payload = _build_payload(products)
    try:
        with make_client() as client:
            r = client.post(config.TEAMS_WEBHOOK_URL, json=payload)
            r.raise_for_status()
        _log.info("Teams 알림 전송 완료 (신규 %d건)", len(products))
        return True
    except Exception as e:  # 알림 실패가 수집을 막지 않도록
        _log.warning("Teams 알림 전송 실패: %s", e)
        return False
