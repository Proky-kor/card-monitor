"""대시보드 라우터 — 목록·필터·정렬."""

from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import config
from data.scrapers import COMPANY_META
from storage import db

router = APIRouter()
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

_SORTS = {"launch_desc", "launch_asc"}


def _is_new(launch_date: str | None) -> bool:
    """신규 = 출시일의 연-월이 조회 당월과 일치."""
    if not launch_date:
        return False
    return launch_date[:7] == datetime.now().strftime("%Y-%m")


def _is_newly_registered(first_seen: str | None, baseline: str | None) -> bool:
    """신규등록 = 최초 수집(baseline) 이후 새로 잡혔고 N일 이내(first_seen 기준).

    최초 수집분(first_seen == baseline 날짜)은 전부 baseline이라 신규로 보지 않는다.
    """
    if not first_seen:
        return False
    day = first_seen[:10]
    if baseline and day <= baseline:  # 최초 수집분 제외
        return False
    try:
        dt = datetime.strptime(day, "%Y-%m-%d")
    except (ValueError, TypeError):
        return False
    return dt >= datetime.now() - timedelta(days=config.NEW_REGISTERED_DAYS)


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    company: str | None = None,
    status: str | None = None,  # 'new' | None
    sort: str = "launch_desc",  # 'launch_desc'(기본, 최근 출시일) | 'launch_asc'
) -> HTMLResponse:
    if sort not in _SORTS:
        sort = "launch_desc"
    with db.get_conn() as conn:
        # 단종 상품은 제외(안내 불필요)
        rows = db.list_products(conn, company=company, discontinued=0, sort=sort)
        companies = db.list_companies(conn)
        baseline = db.baseline_by_company(conn)

    products = []
    for r in rows:
        d = dict(r)
        d["is_new"] = _is_new(r["launch_date"])
        d["is_new_registered"] = _is_newly_registered(
            r["first_seen"], baseline.get(r["company"]))
        products.append(d)
    if status == "new":
        products = [p for p in products if p["is_new"]]
    elif status == "registered":
        products = [p for p in products if p["is_new_registered"]]

    # 카드사 홈페이지 바로가기 링크 (현재 필터 회사 또는 전체)
    if company and company in COMPANY_META:
        home_links = [COMPANY_META[company]]
    else:
        home_links = [
            COMPANY_META[c["company"]] for c in companies if c["company"] in COMPANY_META
        ]

    ctx = {
        "request": request,
        "products": products,
        "companies": companies,
        "home_links": home_links,
        "filters": {"company": company, "status": status, "sort": sort},
        "this_month": datetime.now().strftime("%Y년 %m월"),
        "registered_days": config.NEW_REGISTERED_DAYS,
        "total": len(products),
        "grand_total": sum(c["cnt"] for c in companies),
    }
    return _TEMPLATES.TemplateResponse(request, "list.html", ctx)
