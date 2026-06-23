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
    ok = True
    for s in summaries:
        if "error" in s:
            ok = False
            print(f"[실패] {s['company']}: {s['error']}")
        else:
            print(f"[완료] {s['name']}: 수집 {s['collected']}건, "
                  f"신규등록 {s.get('new_count', 0)}건, 미노출단종 {s['discontinued']}건")
    return 0 if ok else 1


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
