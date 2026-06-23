"""Teams 알림 페이로드 빌드 단위테스트 (네트워크 없음)."""

from data.models import CardProduct
from services.notifier import _build_payload, notify_new_products


def _p(name, company="shinhan", cname="신한카드", launch="2026-06-01"):
    return CardProduct(company=company, company_name=cname, code=name, name=name,
                       launch_date=launch, detail_url="http://x/" + name)


def test_payload_lists_new_cards():
    payload = _build_payload([_p("A카드"), _p("B카드", launch=None)])
    assert payload["newCount"] == 2
    assert "신규 카드 상품 2건" in payload["title"]
    assert "A카드" in payload["text"]
    assert "출시 2026-06-01" in payload["text"]
    assert len(payload["cards"]) == 2
    assert payload["cards"][0]["name"] == "A카드"


def test_payload_truncates_over_max():
    payload = _build_payload([_p(f"카드{i}") for i in range(50)])
    assert payload["newCount"] == 50
    assert "외 10건" in payload["text"]  # 40 표시 + 나머지 10


def test_notify_skips_when_no_webhook(monkeypatch):
    import config
    monkeypatch.setattr(config, "TEAMS_WEBHOOK_URL", "")
    assert notify_new_products([_p("A카드")]) is False


def test_notify_skips_when_empty():
    assert notify_new_products([]) is False
