"""신규 등록 감지 + Teams 알림 호출 통합 테스트 (임시 DB, 네트워크 없음)."""

import config
from data.models import CardProduct
from services import collector


def _prod(code, name):
    return CardProduct(company="fake", company_name="테스트카드", code=code, name=name,
                       launch_date="2026-06-01")


def _setup(monkeypatch, tmp_path, products):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(collector, "REGISTRY",
                        {"fake": ("테스트카드", lambda known_launch=None: products)})
    # 이미지 다운로드 네트워크 차단
    monkeypatch.setattr(collector, "_download_image", lambda *a, **k: None)


def test_first_run_no_new(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, [_prod("A", "A카드"), _prod("B", "B카드")])
    s = collector.collect_company("fake")
    assert s["collected"] == 2
    assert s["new_count"] == 0  # 최초 수집은 신규로 보지 않음
    assert s["_new_products"] == []


def test_second_run_detects_new(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, [_prod("A", "A카드"), _prod("B", "B카드")])
    collector.collect_company("fake")  # 최초
    # C 추가
    monkeypatch.setattr(collector, "REGISTRY",
                        {"fake": ("테스트카드",
                                  lambda known_launch=None: [_prod("A", "A카드"),
                                                             _prod("B", "B카드"),
                                                             _prod("C", "C카드")])})
    s = collector.collect_company("fake")
    assert s["new_count"] == 1
    assert [p.code for p in s["_new_products"]] == ["C"]


def test_zero_result_does_not_discontinue(monkeypatch, tmp_path):
    """수집 0건(클라우드 일시 실패)이면 기존 상품을 단종 처리하지 않고 보존한다."""
    import storage.db as db
    _setup(monkeypatch, tmp_path, [_prod("A", "A카드"), _prod("B", "B카드")])
    collector.collect_company("fake")  # 최초 2건 저장
    # 다음 수집이 0건 반환(파서 일시 실패 시뮬레이션)
    monkeypatch.setattr(collector, "REGISTRY",
                        {"fake": ("테스트카드", lambda known_launch=None: [])})
    s = collector.collect_company("fake")
    assert s["collected"] == 0
    assert s["discontinued"] == 0
    # 기존 A·B는 여전히 활성(discontinued=0) 이어야 한다
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT code, discontinued FROM card_products WHERE company='fake'"
        ).fetchall()
    assert {r["code"]: r["discontinued"] for r in rows} == {"A": 0, "B": 0}


def test_collect_all_calls_notifier(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, [_prod("A", "A카드")])
    collector.collect_company("fake")  # 최초(신규 0)
    monkeypatch.setattr(collector, "REGISTRY",
                        {"fake": ("테스트카드",
                                  lambda known_launch=None: [_prod("A", "A카드"),
                                                             _prod("N", "신상카드")])})
    monkeypatch.setattr(config, "ENABLED_COMPANIES", ["fake"])
    captured = {}
    import services.notifier as notifier
    monkeypatch.setattr(notifier, "notify_new_products",
                        lambda prods: captured.update(n=[p.code for p in prods]))
    collector.collect_all()
    assert captured.get("n") == ["N"]
