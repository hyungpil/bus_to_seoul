"""실시간 모니터링 데이터 조합 (웹/CLI 공용)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from . import db
from .config import (DEST_STOP_ID, DEST_STOP_NAME, KST, ORIGIN_STOP_ID,
                     ORIGIN_STOP_NAME, ROUTES)
from .naver import NaverBusClient


def historical_travel(conn: sqlite3.Connection, route_name: str, at: datetime) -> dict | None:
    """같은 요일·시간대 -> 같은 시간대(전 요일) -> 노선 전체 순으로 평균 소요시간을 찾는다."""
    q = ("SELECT COUNT(*) n, AVG(travel_sec) avg FROM trips "
         "WHERE stage='done' AND accurate=1 AND route_name=? ")
    tries = [
        (q + "AND weekday=? AND hour=?", (route_name, at.weekday(), at.hour), f"{db.WEEKDAY_KO[at.weekday()]}요일 {at.hour}시대"),
        (q + "AND hour=?", (route_name, at.hour), f"전체 요일 {at.hour}시대"),
        (q, (route_name,), "전체 기록"),
    ]
    for sql, args, basis in tries:
        r = conn.execute(sql, args).fetchone()
        if r["n"]:
            return {"avg_sec": int(r["avg"]), "samples": r["n"], "basis": basis}
    return None


def live_status(client: NaverBusClient, conn: sqlite3.Connection) -> dict:
    now = datetime.now(KST)
    result = {"now": db.fmt(now), "origin": ORIGIN_STOP_NAME, "dest": DEST_STOP_NAME,
              "routes": [], "errors": []}
    try:
        a = client.arrivals(ORIGIN_STOP_ID, ROUTES.keys())
    except Exception as e:
        a = {}
        result["errors"].append(f"{ORIGIN_STOP_NAME} 조회 실패: {e}")
    try:
        b = client.arrivals(DEST_STOP_ID, ROUTES.keys())
    except Exception as e:
        b = {}
        result["errors"].append(f"{DEST_STOP_NAME} 조회 실패: {e}")

    en_route = {}
    for r in conn.execute("SELECT * FROM trips WHERE stage='passed_a' ORDER BY a_arrival").fetchall():
        en_route.setdefault(r["route_id"], []).append(r)

    for rid, rname in ROUTES.items():
        ra, rb = a.get(rid), b.get(rid)
        b_by_plate = {x.plate_no: x for x in rb.buses} if rb else {}
        approaching = []
        for bus in (ra.buses if ra else []):
            eta_a = ra.reference_time + timedelta(seconds=bus.remaining_sec or 0)
            hist = historical_travel(conn, rname, eta_a)
            approaching.append({
                "plate_no": bus.plate_no,
                "stage": "approaching_a",
                "eta_origin": eta_a.strftime("%H:%M"),
                "min_to_origin": round((bus.remaining_sec or 0) / 60),
                "stops_to_origin": bus.remaining_stop,
                "seats": bus.remaining_seat,
                "congestion": bus.congestion,
                "eta_dest": (eta_a + timedelta(seconds=hist["avg_sec"])).strftime("%H:%M") if hist else None,
                "eta_dest_basis": f"{hist['basis']} 평균 {hist['avg_sec']/60:.0f}분 (n={hist['samples']})" if hist else None,
            })
        tracking = []
        for t in en_route.get(rid, []):
            live = b_by_plate.get(t["plate_no"])
            item = {"plate_no": t["plate_no"], "stage": "passed_a", "passed_origin": t["a_arrival"][11:16]}
            if live:
                eta_b = rb.reference_time + timedelta(seconds=live.remaining_sec or 0)
                item.update(eta_dest=eta_b.strftime("%H:%M"), stops_to_dest=live.remaining_stop,
                            elapsed_min=round((now - db.parse(t["a_arrival"])).total_seconds() / 60),
                            source="실시간")
            else:
                hist = historical_travel(conn, rname, db.parse(t["a_arrival"]))
                if hist:
                    item.update(eta_dest=(db.parse(t["a_arrival"]) + timedelta(seconds=hist["avg_sec"])).strftime("%H:%M"),
                                source="과거평균")
            tracking.append(item)
        result["routes"].append({
            "route_id": rid, "route_name": rname,
            "status": ra.status if ra else "NO_DATA",
            "approaching": approaching, "tracking": tracking,
        })
    return result


def stats(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT * FROM v_travel_stats ORDER BY route_name, weekday, hour").fetchall()
    recent = conn.execute(
        "SELECT * FROM v_origin_arrivals ORDER BY a_arrival DESC LIMIT 50").fetchall()
    summary = conn.execute(
        "SELECT stage, COUNT(*) n FROM trips GROUP BY stage").fetchall()
    return {"travel": [dict(r) for r in rows], "recent": [dict(r) for r in recent],
            "summary": {r["stage"]: r["n"] for r in summary}}
