# card-monitor — 카드사 신규 상품 모니터링

카드사 공식 홈페이지에서 **신규 출시·단종 카드 상품**을 자동 수집해 사내 대시보드로 보여주는 별도 독립 앱.
기존 단가/검수 도구(`../ax-design-inspector`)와 **완전히 분리**된 프로젝트다.

## 목적 / 표시 정보
상품명 · 체크/신용 구분 · 출시일 · 단종 여부 · 디자인 이미지. 모든 데이터는 **각 카드사 공식 홈페이지에서 직접 수집**한다.
(pleple.net 등 외부 집계 사이트는 데이터 소스로 쓰지 않고, 단종 확인·검증용 **참고**로만 사용.)

## 배포 구조 (중요)
카드 상품 정보는 **전사 공통(시장 정보)** 이라, 사용자별 데이터인 기존 도구와 정반대다.
→ **중앙 서버 1곳에서만 수집·호스팅**하고 직원은 브라우저로 **조회만** 한다.
PC마다 수집하면 같은 사이트를 N번 긁어 봇/IP 차단 위험이 커지므로 금지.

- `python main.py --mode collect` : 수집(작업 스케줄러 1일 1회) — 서버에서만.
- `python main.py --mode serve`   : 대시보드 서버(0.0.0.0 바인드, 상시 구동).

## 아키텍처
```
main.py                  # CLI: --mode serve | collect
config.py                # .env 기반 설정 (_env 패턴)
data/
  models.py              # CardProduct (frozen dataclass)
  http.py                # truststore SSLContext + httpx 클라이언트 (timeout 필수)
  scrapers/
    __init__.py          # 레지스트리 {회사키: scraper 함수}
    lotte.py             # 롯데카드 (파일럿, 검증됨)
services/
  collector.py           # 전 회사 수집 → 이미지 저장 → DB upsert (graceful)
storage/
  db.py                  # sqlite: card_products 테이블·upsert·list
  cards.db               # (생성됨, git 제외)
  card_images/           # 로컬 이미지 캐시 <회사>/<해시>.ext (git 제외)
web/
  app.py                 # FastAPI, 이미지 안전 서빙
  routers/dashboard.py   # GET / (목록·필터)
  templates/             # base.html, list.html
데이터입력/카드사_URL.md   # 회사별 URL·엔드포인트 메모 (운영자/개발 참고)
_probe/                  # 실측 프로브 스크립트·샘플 (참고용, 배포 제외)
```

## 코딩 규칙 (필수)
- **Python**: PEP8, 타입힌트, `@dataclass(frozen=True)` 불변. black/ruff.
- **HTTP**: `verify=False` 절대 금지. `truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)` + **timeout 필수**. User-Agent 명시, 요청 간 지연(저속 수집).
- **예외**: 광범위 `except Exception: pass` 금지. 구체 예외 + 로깅. 단, 수집은 **회사 1곳 실패해도 나머지 진행**(graceful) — 실패는 잡아서 로그 남기고 계속.
- **보안**: 시크릿은 `.env`(채팅/메일 공유 금지). 외부 파일명(이미지)은 sanitize + 경로 트래버설 방지. HTML 출력은 `html.escape` 또는 Jinja2 자동 이스케이프.
- **dict.get() 0 falsy 버그 주의**: 정수/카운트 조회 시 `or` 대신 `is not None`/`in`.
- **Windows**: 경로/문자열·콘솔 출력에 이모지 금지(cp949 깨짐). `.bat`은 CRLF.
- **파일 크기**: 함수 <50줄, 파일 <800줄. 회사별 파서는 작게 분리.

## 파서 작성 패턴 (카드사 추가 시)
각 카드사 파서는 `data/scrapers/<회사>.py`에 `scrape() -> list[CardProduct]` 형태로 작성하고 `scrapers/__init__.py` 레지스트리에 등록한다.
1. **랜딩/목록 페이지의 실제 데이터 경로를 먼저 실측**(`_probe/` 방식). 대부분 JS/AJAX(JSON 또는 HTML 조각)다 — 정적 HTML에 전체 목록이 없을 수 있다.
2. AJAX/JSON 엔드포인트를 찾으면 그걸 직접 호출(가장 안정적). 못 찾으면 Playwright(서버 1대만 설치) 고려.
3. 페이지네이션 처리. 회사별 단종/노출 플래그 의미를 검증 후 매핑.
4. **샘플 응답으로 단위테스트**(네트워크 모킹). 사이트 실연결 의존 금지.

### 롯데카드 (검증된 경로, 파일럿)
- 목록: `POST https://www.lottecard.co.kr/app/LPCDADA_A100.lc`(type=credit) + `LPCDADA_A101.lc`(type=cco) → JSON `{Content: HTML조각, Param:{totalRowCnt=페이지수}}`. 두 목록을 합쳐 전체(115건) 수집.
- **신용/체크 구분 제외**: A100=credit, A101=cco로 나뉘지만 cco 목록에 신용카드가 섞여 있어(B롯데카드·GS&POINT 등) 분류가 부정확 → card_type 라벨 부여 안 함(빈 값). UI에 신용/체크 필터 없음.
- 조각 구조: `<li><a onclick="GoDet('<코드>')">...<img src=".../cdInfo/<파일>">...<b class="tit"><상품명></b><span class="txt"><설명></span></a></li>`
- 이미지: `https://image.lottecard.co.kr/UploadFiles/ecenterPath/cdInfo/<파일명>`
- 상세(사람용): `LPCDADB_V100.lc?vtCdKndC=<코드>` — **HTML에 `카드출시일 : YYYY년 MM월 DD일` 서버렌더**. 출시일은 여기서 파싱(`_parse_launch_date`). 출시일은 불변이라 DB에 있으면 재요청 생략(`known_launch`).
- 단종 감지 2경로:
  - (자동) 사이트는 판매중 상품만 노출 → **목록에서 사라지면 단종**(last_seen diff, `mark_discontinued`).
  - (공지) 공지 목록 AJAX `POST /app/LPEVNCA_V101.lc` (form: searchText='발급 중단' 등, pageRows). 응답 `{Content:HTML조각}`. 조각 `<a onclick="DoDetail('<newsSeq>')"><strong class=tit>제목</strong></a>`. 상세 `LPEVNCA_V200.lc?newsSeq=N`. **검색은 토큰 OR라 노이즈 → 제목 `_DISCONTINUE_TITLE` 엄격필터** 필수. 공지 카드명↔상품명 매칭(`match_notice_to_products`, 공백제거·끝'카드'제거 정규화)되면 해당 상품 discontinued=1 + notice_url.
- **단종 날짜 기능 제외**: 단종/공지 날짜는 파싱·표기하지 않음(요청). 단종 공지 수집·패널·필터는 비활성(단종 안내 불필요).

### 신한카드 (검증된 경로)
- 신한 홈페이지는 완전 SPA(script-hub, 서버요청 시 404 셸) → **Playwright로 API를 발견**했으나 런타임은 **httpx만으로 충분**.
- 목록 API(GET): `https://shapi.shinhancard.com/card-apply/search/v1.0/searchPagingFixedCardProductList?pageSize=8&index=<P>&listID=<카테고리>` (Referer/Origin=`https://www.shinhancard.com` 헤더 필요).
  - 신용 listID=`202001020012`, 체크 listID=`202001020001`. pageSize는 서버가 8로 고정 → index 페이지네이션.
- 응답 `payload.{totalPage, cardInformationList[]}`. item: cardProductEntryId(코드)·cardProductEntryName(상품명)·cardProductUrl(상세경로, BASE+)·thumbnailImgUrl(이미지, BASE+)·**cardPdStartDate(출시일, 목록에 포함 → 상세조회 불필요)**·cardProductSummary(요약).
- 신한은 listID로 신용/체크가 **정확히 분리**되어 card_type 부여(롯데는 부정확해서 미부여).

### 디자인/UI 규칙 (현재)
- **신규등록(파란 배지)** = first_seen 최근 `CARD_NEW_REGISTERED_DAYS`(기본14)일 + **baseline(MIN first_seen) 이후**(첫 수집 전량 노이즈 방지). 모니터링이 새로 발견한 상품. 필터 `status=registered`.
- **당월출시(초록 배지)** = launch_date 연-월이 당월(`_is_new`). 필터 `status=new`.
- 정렬 = 출시일 기준(기본 최근 `launch_desc`/오래된 `launch_asc`). 단종 상품 목록서 제외. 좌측 사이드바=카드사 구분.

### 모니터링·알림·자동화
- 주기 수집: `자동수집_등록.bat`(Windows 작업 스케줄러 schtasks DAILY → `카드수집_실행.bat auto`). 해제 `자동수집_해제.bat`.
- 신규 감지: `collect_company`가 수집 전 `db.existing_codes`와 비교 → 새 코드만 `_new_products`(최초 수집 prior 비면 신규 0). `collect_all`이 신규 있으면 Teams 1회 알림.
- Teams 알림: `services/notifier.py`(`CARD_TEAMS_WEBHOOK_URL` .env, MessageCard+구조화 cards, Incoming Webhook/Power Automate 호환, 실패해도 수집 계속). 시크릿은 .env만(채팅/메일 금지).
- 비개발자 자동화 가이드: `자동화_안내.md`(PC 작업스케줄러) + `깃허브_자동화_안내.md`(GitHub Actions).
- **GitHub Actions(PC 불필요)**: `.github/workflows/monitor.yml` — cron 매일 00:00 UTC(09:00 KST)+수동. pip install + playwright --with-deps chromium → `collect`(Teams는 `secrets.CARD_TEAMS_WEBHOOK_URL`) → `export` → cards.db 강제커밋(상태유지=신규감지) → Pages 배포. **리스크: 한국 카드사가 GitHub 해외 IP 차단 가능 → 첫 수동 실행으로 검증 필요.**
- **정적 대시보드**: `main.py --mode export` → `dist/index.html`(web/static_export.py). 이미지=원본 image_url(서버 불필요), 회사·신규등록/당월·검색은 클라이언트 JS 필터. GitHub Pages용.
- **신규등록 baseline은 회사별**(`db.baseline_by_company`): 각 회사 첫 수집일분은 제외(점진 추가 대응). 전역 baseline은 회사마다 수집일 다르면 오탐 → 회사별 필수.

### 카드사별 정찰 현황 (2026-06-22, 8개 국내사)
신한처럼 "깨끗한 JSON API + 출시일 포함"인 곳만 저비용. 나머지는 회사별 난이도 천차만별.
- **롯데** ✅ 완료 — AJAX HTML조각(LPCDADA_A100/A101) + 상세에서 출시일. 115건.
- **신한** ✅ 완료 — 공개 JSON API(searchPagingFixedCardProductList) 목록에 출시일·이미지 포함. 212건.
- **현대** ✅ 완료(Playwright) — 전체목록 `/cpc/ma/CPCMA0101_01.hc`("전체 카드 신청") 렌더 후 `goCardDetail('<코드>')` 73건 추출. 이름=박스 타이틀, 이미지=`https://img.hyundaicard.com/img/com/card/card_<코드>_h.png`(코드도출), 상세=`/cpc/cr/CPCCR0201_01.hc?cardWcd=<코드>`. **출시일은 상세 본문 "(신규 )출시(YYYY년 MM월 DD일)"** — JS렌더라 Playwright로 상세 렌더 필요(known_launch 캐싱으로 신규분만). 73/73 출시일 확보.
- **KB** ✅ 완료(Playwright목록+httpx상세, 40건·출시일33) — 목록: 모바일 `m.kbcard.com/CRD/DVIEW/MCAM0101` 렌더, `fnVwCardDetail('<코드>')`+h3 이름+img `product/<코드>_img.png`(스크롤-안정화 ~40건). **출시일: 상세 `card.kbcard.com/CRD/DVIEW/HCAMCXPRICAC0076?mainCC=a&cooperationcode=<코드>`가 SSR이라 httpx로 받아 부가서비스 안내의 "(YYYY.MM.DD 출시)" 파싱**(`_parse_launch_date`, known_launch 캐싱). 신용/체크 목록 0047/0056은 JS페이지네이션이라 httpx GET은 첫 ~10건만 → 모바일이 더 많음. 오픈API포털은 제휴·OAuth 전용이라 카탈로그 불가.
- **하나** ✅ 완료(httpx EUC-KR, 118건·출시일無) — 랜딩 `OPI41000000D.web`는 보안프로그램 안티봇이지만, 목록 AJAX `POST /OPI31000000D.ajax`(폼인코딩, **응답 EUC-KR** → `resp.content.decode('euc-kr')`)는 차단 안 됨. body `schID=pcd&mID=OPM05000000C&...&CT_ID=<카테고리>&ST_ID=`. 응답 `dataMap.CARD_LIST.data[]`: CD_NM(이름)·CD_NO(코드)·LIST_IMG_TYPE_IMG(이미지 `hanacard.co.kr`+경로)·CD_DESC_TXT. 카테고리 CT_ID: 신용 241704030444153·체크 241704050328506·제휴 241704030444279. 신용 58+제휴 26→신용, 체크 34. **출시일은 목록에 없음**(상세 경로 미발굴).
- **우리** ✅ 완료(Playwright 인-브라우저 fetch, 134건·출시일100%) — 목록 API `POST /dcpc/yh1/crd/crd02/searchCrd02List.pwkjson`(body `{"crd02Vo":{recordCnt:3000,nowPage:1,ctgrCd:"",hiPrdCtgrCd:"M110018",sortDiv:"B"}}`)는 세션 필요해 httpx 막힘 → **카테고리 페이지 연 뒤 page.evaluate(fetch)**. **ctgrCd 빈값=전체 반환**(ctgrCd는 혜택 하위카테고리 필터라 채우면 일부만; 혜택태그 중복은 cdPrdCd로 dedupe=134). card_type은 **cdPrdCfcd('1'=신용·'2'=체크)**. item에 cdPrdCd·cdPrdNm·**cdPdselStaDh(YYYYMMDD...=출시일)**·fileCoursWeb(이미지 `pc.wooricard.com`+경로) 다 있음(상세 불필요).
- **비씨(BC)** ✅ 완료(순수 httpx, 239건·출시일無) — 목록 API 폼인코딩 POST `/app/card/CreditSearch.do`·`/app/card/CheckSearch.do`(body `retKey=json&pageNo=N`) → `{TOTAL,PAGE_COUNT,CARDGDS[10/page]}` httpx 직호출 OK. item: cardGdsNo(코드)·cardGdsNm(이름)·CARD_GDS_IMG(이미지 `bccard.com`+경로)·affiFirmNo·mbNo. 신용 161+체크 78. **출시일 미노출**(BC는 회원은행 카드 집계 네트워크 — 상세 `CreditCardMain.do?gdsno=<affiFirmNo>&mbkNo=<mbNo>`에도 출시일 없음). 주의: BC 페이지가 Playwright 셀렉터 엔진을 깨뜨림(eval_on_selector_all 실패) → page.evaluate 사용. 단 목록은 httpx라 무관.
- **삼성** ✅ 완료(Playwright목록+httpx상세, 107건·출시일100%) — Nuxt SPA. 목록: 신용 `PGHPPDCCardCardinfoRecommendPC001?tabIndex=9`(91건)+체크 `PGHPPCCCardCardinfoCheckcard001`(16건) 렌더 후 **카드 플레이트 이미지 `scard/image/personal/b_<코드>.png`(신용 AAP·체크 ABP)에서 코드 추출**(DOM에 code 링크 없고 이미지로만 식별). 이름도 목록 img alt/타이틀에서(107중 105). **출시일: 상세 `PGHPPCCCardCardinfoDetails001?code=<코드>` HTML의 __NUXT__ 블롭 `sellStrtdt:"YYYY-MM-DD"` httpx 파싱**(span#sellStrtdt는 JS로 채워져 비어있지만 __NUXT__엔 있음). 이미지 `b_<코드>.png`. 신용/체크 URL 분리로 card_type 부여.
- **농협** ❓ — 추정 URL 404. 정확한 카드목록 URL 재확보 필요.

권장: 신한식 API가 있는 곳 위주. DOM스크랩(출시일無)·안티봇은 비용 대비 효과 낮음.

### Playwright (발견 전용)
- SPA 카드사(신한·KB·우리 등)의 내부 API를 **찾을 때만** 사용: `uv pip install --native-tls playwright` + `NODE_TLS_REJECT_UNAUTHORIZED=0 python -m playwright install chromium`(회사망 프록시).
- 발견 후엔 가급적 httpx 직접호출로 런타임 구현(신한처럼). 정말 렌더가 필요한 경우에만 런타임 Playwright(중앙 서버 1대).

## 검증
- 단위테스트: `pytest -q` (샘플 픽스처 파싱).
- 수집: `python main.py --mode collect` → `storage/cards.db` 행·`storage/card_images/` 파일 확인.
- 서버: `python main.py --mode serve` → 브라우저 `http://localhost:8001/`.

## 현황
- 2026-06-22: 파싱 실현 가능성 실측 완료(롯데 JSON 경로 확정). 프레임워크 + 롯데 파일럿 구축 중. 호스팅은 추후.
