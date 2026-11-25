"""GitHub Actions용 버스 데이터 수집 및 정적 내보내기 CLI."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta

from . import db
from .config import DB_PATH, KST, LOG_DIR


def setup_logging(name: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(LOG_DIR / f"{name}.log", encoding="utf-8")]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def cmd_stats():
    from .service import stats

    s = stats(db.connect())
    print("운행 상태:", s["summary"] or "기록 없음")
    print(f"\n{'노선':<6}{'요일':<4}{'시':>4}{'건수':>6}{'평균':>8}{'최소':>8}{'최대':>8}")
    for r in s["travel"]:
        print(f"{r['route_name']:<6}{r['weekday_name']:<4}{r['hour']:>4}{r['trips']:>6}"
              f"{r['avg_min']:>8}{r['min_min']:>8}{r['max_min']:>8}")


def cmd_check(args):
    """GitHub Actions가 만든 데이터와 최근 수집 기록을 점검한다."""
    print("=== GitHub Actions 수집 데이터 ===")
    if not DB_PATH.exists():
        print("  DB 파일 없음 - 아직 수집되지 않았습니다.")
        return

    conn = db.connect()
    last = conn.execute("SELECT MAX(polled_at) t FROM polls").fetchone()["t"]
    print(f"  마지막 조회: {last or '없음'}")
    print(f"\n  {'날짜':<12}{'요일':<4}{'조회':>6}{'실패':>6}{'광명역통과':>8}{'완료':>6}{'정확':>6}{'유실':>6}")
    since = (datetime.now(KST) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT d, (SELECT COUNT(*) FROM polls WHERE substr(polled_at,1,10)=d) polls,
               (SELECT COUNT(*) FROM polls WHERE substr(polled_at,1,10)=d AND ok=0) fails,
               (SELECT COUNT(*) FROM trips WHERE service_date=d AND a_arrival IS NOT NULL) passed,
               (SELECT COUNT(*) FROM trips WHERE service_date=d AND stage='done') done,
               (SELECT COUNT(*) FROM trips WHERE service_date=d AND stage='done' AND accurate=1) acc,
               (SELECT COUNT(*) FROM trips WHERE service_date=d AND stage='lost') lost
        FROM (SELECT DISTINCT substr(polled_at,1,10) d FROM polls WHERE polled_at >= ?) ORDER BY d""",
        (since,)).fetchall()
    if not rows:
        print(f"  최근 {args.days}일 조회 기록 없음")
    for x in rows:
        wd = db.WEEKDAY_KO[datetime.strptime(x["d"], "%Y-%m-%d").weekday()]
        print(f"  {x['d']:<12}{wd:<4}{x['polls']:>6}{x['fails']:>6}{x['passed']:>8}"
              f"{x['done']:>6}{x['acc']:>6}{x['lost']:>6}")

    print("\n=== 수집 로그 마지막 10줄 ===")
    logf = LOG_DIR / "collector.log"
    if logf.exists():
        for line in logf.read_text(encoding="utf-8", errors="replace").splitlines()[-10:]:
            print("  " + line)
    else:
        print("  로그 없음")


def main():
    p = argparse.ArgumentParser(prog="bus_to_seoul")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("export-static")
    c = sub.add_parser("collect")
    c.add_argument("--force", action="store_true", help="수집 시간대(16~19시) 무시")
    sub.add_parser("stats")
    k = sub.add_parser("check")
    k.add_argument("--days", type=int, default=7)
    args = p.parse_args()

    if args.cmd == "export-static":
        from .export_static import export
        export()
    elif args.cmd == "collect":
        setup_logging("collector")
        from .collector import run
        run(force=args.force)
    elif args.cmd == "stats":
        cmd_stats()
    elif args.cmd == "check":
        cmd_check(args)


if __name__ == "__main__":
    main()
