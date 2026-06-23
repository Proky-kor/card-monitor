"""정적 대시보드 생성 — 서버 없이 GitHub Pages 등에 올릴 수 있는 단일 HTML.

수집된 DB를 읽어 dist/index.html 을 만든다. 이미지는 카드사 원본 URL을 직접 사용하고,
회사·신규/당월·검색 필터는 클라이언트 JS로 동작(서버 불필요).
"""

import html
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import config
from storage import db

_log = logging.getLogger(__name__)


def _is_new(launch_date):
    return bool(launch_date) and launch_date[:7] == datetime.now().strftime("%Y-%m")


def _is_reg(first_seen, baseline):
    if not first_seen:
        return False
    day = first_seen[:10]
    if baseline and day <= baseline:
        return False
    try:
        dt = datetime.strptime(day, "%Y-%m-%d")
    except (ValueError, TypeError):
        return False
    return dt >= datetime.now() - timedelta(days=config.NEW_REGISTERED_DAYS)


def _card_html(p: dict) -> str:
    img = p.get("image_url") or ""
    name = html.escape(p.get("name") or "")
    company = html.escape(p.get("company_name") or "")
    launch = p.get("launch_date") or ""
    badges = ""
    if p["_reg"]:
        badges += '<span class="badge reg">신규등록</span>'
    if p["_new"]:
        badges += '<span class="badge new">당월출시</span>'
    launch_tag = f'<span class="tag">출시 {html.escape(launch)}</span>' if launch else ""
    img_html = (f'<img src="{html.escape(img)}" alt="{name}" loading="lazy">'
                if img else '<span class="noimg">이미지 없음</span>')
    href = html.escape(p.get("detail_url") or "#")
    return (
        f'<a class="card" data-c="{html.escape(p.get("company") or "")}" '
        f'data-reg="{1 if p["_reg"] else 0}" data-new="{1 if p["_new"] else 0}" '
        f'data-launch="{html.escape(launch)}" '
        f'data-name="{name.lower()}" href="{href}" target="_blank" rel="noopener">'
        f'<div class="thumb">{img_html}</div>'
        f'<div class="body"><div class="name">{name}</div>'
        f'<div class="meta"><span class="tag">{company}</span>{badges}{launch_tag}</div>'
        f'</div></a>'
    )


def build_html() -> str:
    with db.get_conn() as conn:
        rows = [dict(r) for r in db.list_products(conn, discontinued=0, sort="launch_desc")]
        companies = [dict(r) for r in db.list_companies(conn)]
        baseline = db.baseline_by_company(conn)
    for p in rows:
        p["_new"] = _is_new(p.get("launch_date"))
        p["_reg"] = _is_reg(p.get("first_seen"), baseline.get(p.get("company")))

    updated = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(rows)
    reg_n = sum(1 for p in rows if p["_reg"])
    comp_btns = '<button class="cbtn on" data-c="">전체 ' + str(total) + "</button>"
    for c in companies:
        comp_btns += (f'<button class="cbtn" data-c="{html.escape(c["company"])}">'
                      f'{html.escape(c["company_name"])} {c["cnt"]}</button>')
    cards = "\n".join(_card_html(p) for p in rows)

    return _TEMPLATE.format(
        updated=updated, total=total, reg_n=reg_n,
        reg_days=config.NEW_REGISTERED_DAYS, this_month=datetime.now().strftime("%Y년 %m월"),
        comp_btns=comp_btns, cards=cards,
    )


def export_static(out_dir: str = "dist") -> str:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "index.html"
    target.write_text(build_html(), encoding="utf-8")
    _log.info("정적 대시보드 생성: %s", target)
    return str(target)


_TEMPLATE = """<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>카드사 신규 상품 모니터링</title>
<style>
:root{{--bg:#0f1115;--surface:#181b22;--surface2:#20242e;--line:#2b3140;--text:#e7eaf0;--muted:#9aa3b2;--accent:#4c8dff;--new:#2ecc71;}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:"Malgun Gothic",system-ui,sans-serif}}
header{{padding:18px 24px;border-bottom:1px solid var(--line)}}h1{{font-size:19px;margin:0 0 4px}}.sub{{color:var(--muted);font-size:13px}}
main{{padding:18px 24px 60px;max-width:1400px;margin:0 auto}}
.bar{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:14px}}
.bar .lbl{{font-size:12px;color:var(--muted);margin-right:2px}}
button{{cursor:pointer;font-size:13px;padding:7px 13px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--muted)}}
button.on{{background:var(--accent);border-color:var(--accent);color:#fff}}
#q{{padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--text);min-width:200px}}
.grid{{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(210px,1fr))}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column;text-decoration:none;color:inherit;transition:transform .15s,border-color .15s}}
.card:hover{{transform:translateY(-3px);border-color:var(--accent)}}
.thumb{{aspect-ratio:16/10;background:var(--surface2);display:flex;align-items:center;justify-content:center;overflow:hidden}}
.thumb img{{width:100%;height:100%;object-fit:contain;padding:10px}}.noimg{{color:var(--muted);font-size:12px}}
.body{{padding:11px 13px 13px}}.name{{font-size:14px;font-weight:600}}
.meta{{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:6px}}
.tag{{font-size:11px;padding:2px 8px;border-radius:6px;background:var(--surface2);color:var(--muted)}}
.badge{{font-size:11px;font-weight:700;padding:2px 8px;border-radius:6px}}
.badge.new{{background:rgba(46,204,113,.15);color:var(--new)}}.badge.reg{{background:var(--accent);color:#fff}}
#empty{{color:var(--muted);padding:50px 0;text-align:center;display:none}}
</style></head><body>
<header><h1>카드사 신규 상품 모니터링</h1>
<div class="sub">총 <b id="cnt">{total}</b>건 · 신규등록 {reg_n}건(최근 {reg_days}일) · 당월출시 기준 {this_month} · 갱신 {updated}</div></header>
<main>
<div class="bar" id="comp">{comp_btns}</div>
<div class="bar"><span class="lbl">상태</span>
<button class="sbtn on" data-s="">전체</button>
<button class="sbtn" data-s="reg">신규등록</button>
<button class="sbtn" data-s="new">당월출시</button>
<span class="lbl" style="margin-left:12px">정렬</span>
<button class="obtn on" data-o="desc">최근 출시순</button>
<button class="obtn" data-o="asc">오래된 출시순</button>
<input id="q" type="search" placeholder="카드명 검색"></div>
<div class="grid" id="grid">{cards}</div>
<div id="empty">조건에 맞는 카드가 없습니다.</div>
</main>
<script>
var fc="",fs="",fq="";
function apply(){{
  var cards=document.querySelectorAll('#grid .card'),shown=0;
  cards.forEach(function(el){{
    var ok=(!fc||el.dataset.c===fc)&&(!fs||el.dataset[fs]==='1')&&(!fq||el.dataset.name.indexOf(fq)>=0);
    el.style.display=ok?'':'none';if(ok)shown++;
  }});
  document.getElementById('cnt').textContent=shown;
  document.getElementById('empty').style.display=shown?'none':'block';
}}
document.getElementById('comp').addEventListener('click',function(e){{if(e.target.dataset.c===undefined)return;
  document.querySelectorAll('#comp .cbtn').forEach(b=>b.classList.remove('on'));e.target.classList.add('on');fc=e.target.dataset.c;apply();}});
document.querySelectorAll('.sbtn').forEach(function(b){{b.addEventListener('click',function(){{
  document.querySelectorAll('.sbtn').forEach(x=>x.classList.remove('on'));b.classList.add('on');fs=b.dataset.s;apply();}});}});
document.getElementById('q').addEventListener('input',function(e){{fq=e.target.value.trim().toLowerCase();apply();}});
var fo='desc';
function sortGrid(){{
  var grid=document.getElementById('grid');
  var cards=Array.prototype.slice.call(grid.children);
  cards.sort(function(a,b){{
    var la=a.dataset.launch||'',lb=b.dataset.launch||'';
    if(!la&&!lb)return 0;if(!la)return 1;if(!lb)return -1;   // 출시일 없으면 뒤로
    return fo==='desc'?lb.localeCompare(la):la.localeCompare(lb);
  }});
  cards.forEach(function(c){{grid.appendChild(c);}});
}}
document.querySelectorAll('.obtn').forEach(function(b){{b.addEventListener('click',function(){{
  document.querySelectorAll('.obtn').forEach(x=>x.classList.remove('on'));b.classList.add('on');fo=b.dataset.o;sortGrid();apply();}});}});
</script></body></html>"""
