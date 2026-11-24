"""사용법:
    python -m bus_to_seoul collect            # 16:00~19:00 1분 단위 수집 (상시 실행)
    python -m bus_to_seoul collect --force --minutes 60   # 시간대 무시하고 60분 수집 (테스트)
    python -m bus_to_seoul monitor            # 터미널 실시간 모니터
    python -m bus_to_seoul web                # 웹 대시보드 http://127.0.0.1:8507
    python -m bus_to_seoul stats              # 요일·시간대별 통계 출력
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from . import db
from .config import LOG_DIR, WEB_HOST, WEB_PORT


def setup_logging(name: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(LOG_DIR / f"{name}.log", encoding="utf-8")]
    if sys.stdout is not None:  # pythonw.exe(콘솔 없음)로 실행되면 stdout이 None
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def cmd_monitor(args):
    from .naver import NaverBusClient
    from .service import live_status
    client, conn = NaverBusClient(), db.connect()
    while True:
        d = live_status(client, conn)
        if not args.once:
            os.system("cls" if os.name == "nt" else "clear")
        print(f"[{d['now']}] {d['origin']} → {d['dest']}")
        for e in d["errors"]:
            print("  ! " + e)
        for r in d["routes"]:
            print(f"\n■ {r['route_name']}")
            if not r["approaching"]:
                print("   도착 정보 없음")
            for b in r["approaching"]:
                dest = f" → 서울대입구역 {b['eta_dest']} ({b['eta_dest_basis']})" if b["eta_dest"] else ""
                print(f"   {b['eta_origin']} ({b['min_to_origin']}분 후, {b['stops_to_origin']}정거장 전) "
                      f"{b['plate_no']} 좌석 {b['seats']}{dest}")
            for t in r["tracking"]:
                print(f"   ↳ 추적중 {t['plate_no']} 광명역 {t['passed_origin']} 통과 → 서울대입구역 "
                      f"{t.get('eta_dest', '?')} ({t.get('source', '-')})")
        if args.once:
            return
        time.sleep(args.interval)


def cmd_stats(args):
    from .service import stats
    s = stats(db.connect())
    print("운행 상태:", s["summary"] or "기록 없음")
    print(f"\n{'노선':<6}{'요일':<4}{'시':>4}{'건수':>6}{'평균':>8}{'최소':>8}{'최대':>8}")
    for r in s["travel"]:
        print(f"{r['route_name']:<6}{r['weekday_name']:<4}{r['hour']:>4}{r['trips']:>6}"
              f"{r['avg_min']:>8}{r['min_min']:>8}{r['max_min']:>8}")


def cmd_check(args):
    """수집 상태 점검: 스케줄러 작업, 최근 조회, 일자별 축적 현황, 로그 마지막 줄."""
    import subprocess
    from datetime import datetime, timedelta
    from .config import DB_PATH, KST

    print("=== 1. 작업 스케줄러 ===")
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "$t=Get-ScheduledTask -TaskName BusToSeoul-Collector -ErrorAction SilentlyContinue;"
         "if($t){$i=$t|Get-ScheduledTaskInfo; $f='yyyy-MM-dd HH:mm';"
         "\"$($t.State)|$($i.LastRunTime.ToString($f))|$($i.LastTaskResult)|$($i.NextRunTime.ToString($f))\"}"
         "else{'NONE'}"],
        capture_output=True, text=True, errors="replace")
    out = (r.stdout or "").strip()
    if out == "NONE" or "|" not in out:
        print("  등록 안 됨 - register_task.ps1 을 실행하세요.", r.stderr.strip())
    else:
        state, last, code, nxt = out.split("|")
        code = int(code)
        result = {0: "성공", 267009: "실행 중", 267011: "아직 실행된 적 없음"}.get(code, f"오류 코드 {code}")
        if last.startswith("1999"):
            last = "-"
        print(f"  상태: {state} / 마지막 실행: {last} ({result}) / 다음 실행: {nxt}")

    print(f"\n=== 2. DB ({DB_PATH}) ===")
    if not DB_PATH.exists():
        print("  DB 파일 없음 - 아직 한 번도 수집되지 않았습니다.")
    else:
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
        print("  * 정상 하루치: 조회 약 360회(16~19시, 정류장 2곳 x 180분) + 19시 이후 추적분")

    print("\n=== 3. 수집 로그 마지막 10줄 ===")
    logf = LOG_DIR / "collector.log"
    if logf.exists():
        for line in logf.read_text(encoding="utf-8", errors="replace").splitlines()[-10:]:
            print("  " + line)
    else:
        print("  로그 없음")


def main():
    p = argparse.ArgumentParser(prog="bus_to_seoul")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--force", action="store_true", help="수집 시간대(16~19시) 무시")
    c.add_argument("--once", action="store_true", help="1회만 조회")
    c.add_argument("--minutes", type=int, help="N분 후 종료")
    m = sub.add_parser("monitor")
    m.add_argument("--once", action="store_true")
    m.add_argument("--interval", type=int, default=30)
    w = sub.add_parser("web")
    w.add_argument("--host", default=WEB_HOST)
    w.add_argument("--port", type=int, default=WEB_PORT)
    sub.add_parser("stats")
    k = sub.add_parser("check")
    k.add_argument("--days", type=int, default=7)
    args = p.parse_args()

    if args.cmd == "collect":
        setup_logging("collector")
        from .collector import run
        run(force=args.force, once=args.once, duration_min=args.minutes)
    elif args.cmd == "monitor":
        cmd_monitor(args)
    elif args.cmd == "web":
        setup_logging("web")
        from .web import serve
        serve(args.host, args.port)
    elif args.cmd == "stats":
        cmd_stats(args)
    elif args.cmd == "check":
        cmd_check(args)


if __name__ == "__main__":
    main()
