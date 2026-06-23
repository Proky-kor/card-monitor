"""SQLite 저장 — card_products 테이블, upsert/list.

수집은 스냅샷이다: 매 수집마다 last_seen 갱신, 처음 본 상품은 first_seen 기록.
이번 수집에서 안 보인 (회사의) 상품은 discontinued=1 로 표시(단종 신호).
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import config
from data.models import CardProduct, DiscontinueNotice

_SCHEMA = """
CREATE TABLE IF NOT EXISTS card_products (
    company        TEXT NOT NULL,
    code           TEXT NOT NULL,
    company_name   TEXT NOT NULL,
    name           TEXT NOT NULL,
    card_type      TEXT NOT NULL DEFAULT '기타',
    image_url      TEXT,
    image_path     TEXT,
    detail_url     TEXT,
    launch_date    TEXT,
    description    TEXT,
    discontinued   INTEGER NOT NULL DEFAULT 0,
    notice_url     TEXT,
    first_seen     TEXT NOT NULL,
    last_seen      TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (company, code)
);
CREATE TABLE IF NOT EXISTS card_notices (
    company       TEXT NOT NULL,
    notice_id     TEXT NOT NULL,
    company_name  TEXT NOT NULL,
    title         TEXT NOT NULL,
    notice_date   TEXT,
    url           TEXT NOT NULL,
    matched_codes TEXT,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (company, notice_id)
);
"""

# 기존 DB에 없을 수 있는 컬럼 (스키마 진화 대응)
_ENSURE_COLUMNS = {
    "card_products": {
        "notice_url": "TEXT",
    },
}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    for table, cols in _ENSURE_COLUMNS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, decl in cols.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def _connect() -> sqlite3.Connection:
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        _ensure_columns(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_product(
    conn: sqlite3.Connection,
    product: CardProduct,
    *,
    now: str,
    image_path: str | None,
) -> None:
    """상품 upsert. 신규면 first_seen=now, 기존이면 last_seen/필드 갱신 + 재등장 시 단종 해제."""
    row = conn.execute(
        "SELECT first_seen, image_path FROM card_products WHERE company=? AND code=?",
        (product.company, product.code),
    ).fetchone()
    if row is None:
        conn.execute(
            """INSERT INTO card_products
               (company, code, company_name, name, card_type, image_url, image_path,
                detail_url, launch_date, description, discontinued,
                first_seen, last_seen, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?)""",
            (
                product.company, product.code, product.company_name, product.name,
                product.card_type, product.image_url, image_path, product.detail_url,
                product.launch_date, product.description, now, now, now,
            ),
        )
    else:
        # 기존 image_path 보존(이번에 새로 못 받았으면)
        keep_image = image_path if image_path is not None else row["image_path"]
        conn.execute(
            """UPDATE card_products SET
               company_name=?, name=?, card_type=?, image_url=?, image_path=?,
               detail_url=?, launch_date=COALESCE(?, launch_date), description=?,
               discontinued=0, last_seen=?, updated_at=?
               WHERE company=? AND code=?""",
            (
                product.company_name, product.name, product.card_type, product.image_url,
                keep_image, product.detail_url, product.launch_date, product.description,
                now, now, product.company, product.code,
            ),
        )


def mark_discontinued(
    conn: sqlite3.Connection, company: str, seen_codes: set[str], now: str
) -> int:
    """이번 수집에서 안 보인 (해당 회사의) 상품을 단종 처리. 처리 건수 반환."""
    rows = conn.execute(
        "SELECT code FROM card_products WHERE company=? AND discontinued=0",
        (company,),
    ).fetchall()
    stale = [r["code"] for r in rows if r["code"] not in seen_codes]
    for code in stale:
        conn.execute(
            "UPDATE card_products SET discontinued=1, updated_at=? WHERE company=? AND code=?",
            (now, company, code),
        )
    return len(stale)


def list_products(
    conn: sqlite3.Connection,
    *,
    company: str | None = None,
    card_type: str | None = None,
    discontinued: int | None = None,
    sort: str = "launch_desc",
) -> list[sqlite3.Row]:
    """대시보드용 목록 조회.

    sort: 'launch_desc'(기본, 최근 출시일 우선) | 'launch_asc'(오래된 출시일 우선).
    출시일 없는 상품은 항상 뒤로.
    """
    sql = "SELECT * FROM card_products WHERE 1=1"
    params: list[object] = []
    if company:
        sql += " AND company=?"
        params.append(company)
    if card_type:
        sql += " AND card_type=?"
        params.append(card_type)
    if discontinued is not None:
        sql += " AND discontinued=?"
        params.append(discontinued)
    direction = "ASC" if sort == "launch_asc" else "DESC"
    # 출시일 NULL은 뒤로, 그 다음 이름순 보조 정렬
    sql += f" ORDER BY (launch_date IS NULL) ASC, launch_date {direction}, name ASC"
    return conn.execute(sql, params).fetchall()


def baseline_by_company(conn: sqlite3.Connection) -> dict[str, str]:
    """회사별 최초 수집일 {company: 'YYYY-MM-DD'}. 신규등록 기준선.

    회사마다 처음 수집한 날이 다를 수 있으므로(점진 추가) 회사별로 본다.
    각 회사의 첫 수집분은 baseline이라 신규로 보지 않는다.
    """
    rows = conn.execute(
        "SELECT company, MIN(first_seen) AS m FROM card_products GROUP BY company"
    ).fetchall()
    return {r["company"]: (r["m"][:10] if r["m"] else "") for r in rows}


def existing_codes(conn: sqlite3.Connection, company: str) -> set[str]:
    """수집 전 해당 회사의 기존 카드 코드 집합 (신규 등록 감지용)."""
    rows = conn.execute(
        "SELECT code FROM card_products WHERE company=?", (company,)
    ).fetchall()
    return {r["code"] for r in rows}


def known_launch_dates(conn: sqlite3.Connection, company: str) -> dict[str, str]:
    """이미 저장된 {code: launch_date} (출시일은 불변 → 재수집 시 재요청 생략용)."""
    rows = conn.execute(
        "SELECT code, launch_date FROM card_products "
        "WHERE company=? AND launch_date IS NOT NULL AND launch_date != ''",
        (company,),
    ).fetchall()
    return {r["code"]: r["launch_date"] for r in rows}


def list_companies(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT company, company_name, COUNT(*) AS cnt FROM card_products "
        "GROUP BY company, company_name ORDER BY company_name"
    ).fetchall()


# ---------------------------------------------------------------------------
# 단종/발급중단 공지
# ---------------------------------------------------------------------------

def upsert_notice(
    conn: sqlite3.Connection,
    notice: DiscontinueNotice,
    *,
    now: str,
    matched_codes: list[str],
) -> None:
    """공지 upsert. matched_codes는 콤마 문자열로 저장."""
    codes_csv = ",".join(matched_codes)
    conn.execute(
        """INSERT INTO card_notices
           (company, notice_id, company_name, title, notice_date, url, matched_codes, updated_at)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(company, notice_id) DO UPDATE SET
             company_name=excluded.company_name, title=excluded.title,
             notice_date=excluded.notice_date, url=excluded.url,
             matched_codes=excluded.matched_codes, updated_at=excluded.updated_at""",
        (notice.company, notice.notice_id, notice.company_name, notice.title,
         notice.notice_date, notice.url, codes_csv, now),
    )


def apply_discontinue_from_notice(
    conn: sqlite3.Connection,
    company: str,
    codes: list[str],
    *,
    notice_url: str,
    now: str,
) -> None:
    """공지로 확인된 상품을 단종 처리 + 공지URL 기록 (단종 날짜는 기록하지 않음)."""
    for code in codes:
        conn.execute(
            """UPDATE card_products SET
               discontinued=1, notice_url=?, updated_at=?
               WHERE company=? AND code=?""",
            (notice_url, now, company, code),
        )


def clear_notices(conn: sqlite3.Connection, company: str) -> None:
    """해당 회사 공지 전체 삭제 (매 수집마다 현재 공지로 전량 갱신)."""
    conn.execute("DELETE FROM card_notices WHERE company=?", (company,))


def list_notices(
    conn: sqlite3.Connection, *, company: str | None = None
) -> list[sqlite3.Row]:
    """단종/발급중단 공지 목록 (최신순)."""
    sql = "SELECT * FROM card_notices WHERE 1=1"
    params: list[object] = []
    if company:
        sql += " AND company=?"
        params.append(company)
    sql += " ORDER BY notice_date DESC, notice_id DESC"
    return conn.execute(sql, params).fetchall()


def products_for_matching(conn: sqlite3.Connection, company: str) -> list[sqlite3.Row]:
    """공지-상품 매칭용: 해당 회사의 (code, name)."""
    return conn.execute(
        "SELECT code, name FROM card_products WHERE company=?", (company,)
    ).fetchall()
