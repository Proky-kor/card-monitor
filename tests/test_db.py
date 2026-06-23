"""DB upsert / 단종 감지 단위테스트 (임시 DB)."""

import config
from data.models import CardProduct
from storage import db


def _product(code: str, name: str) -> CardProduct:
    return CardProduct(company="lotte", company_name="롯데카드", code=code,
                       name=name, card_type="신용")


def test_upsert_and_discontinued_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")

    # 1차 수집: 2건
    with db.get_conn() as conn:
        db.upsert_product(conn, _product("C1", "카드1"), now="2026-06-01 09:00:00", image_path="lotte/a.png")
        db.upsert_product(conn, _product("C2", "카드2"), now="2026-06-01 09:00:00", image_path=None)
        db.mark_discontinued(conn, "lotte", {"C1", "C2"}, "2026-06-01 09:00:00")
    with db.get_conn() as conn:
        rows = db.list_products(conn)
    assert len(rows) == 2
    assert all(r["discontinued"] == 0 for r in rows)

    # 2차 수집: C2 사라짐 -> 단종 처리
    with db.get_conn() as conn:
        db.upsert_product(conn, _product("C1", "카드1"), now="2026-06-02 09:00:00", image_path="lotte/a.png")
        n = db.mark_discontinued(conn, "lotte", {"C1"}, "2026-06-02 09:00:00")
    assert n == 1
    with db.get_conn() as conn:
        disc = db.list_products(conn, discontinued=1)
    assert len(disc) == 1 and disc[0]["code"] == "C2"


def test_image_path_preserved_when_missing_on_update(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t2.db")
    with db.get_conn() as conn:
        db.upsert_product(conn, _product("C1", "카드1"), now="2026-06-01 09:00:00", image_path="lotte/a.png")
        # 재수집 시 이미지 못 받음(None) -> 기존 경로 보존
        db.upsert_product(conn, _product("C1", "카드1 개정"), now="2026-06-02 09:00:00", image_path=None)
        rows = db.list_products(conn)
    assert rows[0]["image_path"] == "lotte/a.png"
    assert rows[0]["name"] == "카드1 개정"


def test_reappearance_clears_discontinued(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t3.db")
    with db.get_conn() as conn:
        db.upsert_product(conn, _product("C1", "카드1"), now="2026-06-01 09:00:00", image_path=None)
        db.mark_discontinued(conn, "lotte", set(), "2026-06-02 09:00:00")  # 사라짐 -> 단종
        assert db.list_products(conn, discontinued=1)
        db.upsert_product(conn, _product("C1", "카드1"), now="2026-06-03 09:00:00", image_path=None)  # 재등장
        assert db.list_products(conn, discontinued=1) == []
