"""card-monitor 진입점.

  python main.py --mode collect   # 수집 (작업 스케줄러 1일 1회, 서버에서만)
  python main.py --mode serve     # 대시보드 서버
"""

import argparse
import logging
import sys


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def run_collect() -> int:
    from services.collector import collect_all

    summaries = collect_all()
    failed = 0
    for s in summaries:
        if "error" in s:
            failed += 1
            print(f"[실패] {s['company']}: {s['error']}")
        else:
            print(f"[완료] {s['name']}: 수집 {s['collected']}건, "
                  f"신규등록 {s.get('new_count', 0)}건, 미노출단종 {s['discontinued']}건")
    succeeded = len(summaries) - failed
    # 일부 실패는 경고만 (해당 회사 기존 데이터는 유지). 전부 실패해야 오류 종료.
    if failed:
        print(f"[경고] {failed}개사 수집 실패(기존 데이터 유지). 성공 {succeeded}개사.")
    return 0 if succeeded else 1


def run_serve() -> int:
    import uvicorn

    import config

    uvicorn.run("web.app:app", host=config.SERVE_HOST, port=config.SERVE_PORT, log_level="info")
    return 0


def run_export() -> int:
    from web.static_export import export_static

    path = export_static("dist")
    print(f"[완료] 정적 대시보드 생성: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(description="카드사 신규 상품 모니터링")
    parser.add_argument("--mode", choices=["collect", "serve", "export"], required=True)
    args = parser.parse_args(argv)
    if args.mode == "collect":
        return run_collect()
    if args.mode == "export":
        return run_export()
    return run_serve()


if __name__ == "__main__":
    sys.exit(main())
