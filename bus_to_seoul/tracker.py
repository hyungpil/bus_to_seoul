"""차량번호(plateNo) 기반 운행 추적.

정류장 실시간 도착 목록은 노선마다 '가장 가까운 버스 1~2대'만 보여준다.
그래서 도착(통과)은 "목록에 보이던 차량이 목록에서 빠진 시점"으로 판정하고,
도착 시각은 마지막 관측의 (기준시각 + 남은시간)을
[마지막 관측 시각, 처음 빠진 것을 확인한 시각] 범위로 잘라서 추정한다.

    approaching_a  광명역5번출구 목록에 보임 (아직 도착 전)
    passed_a       광명역5번출구 통과. 서울대입구역2번출구 목록에 나타나기를 기다림/추적 중
    done           서울대입구역2번출구 통과 -> travel_sec 확정
    lost           타임아웃 또는 같은 차량이 다시 광명역에 나타남
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta

from . import db
from .config import (ACCURATE_LAST_REMAINING_SEC, MISS_THRESHOLD_EMPTY,
                     MISS_THRESHOLD_LISTED, ROUTES, TRIP_TIMEOUT)
from .naver import RouteArrival

log = logging.getLogger(__name__)


def estimate_arrival(last_seen: datetime, last_rem: int | None, first_missing: datetime) -> datetime:
    pred = last_seen + timedelta(seconds=last_rem or 0)
    return max(last_seen, min(pred, first_missing))


def slot_fields(t: datetime) -> dict:
    return {
        "service_date": t.strftime("%Y-%m-%d"),
        "weekday": t.weekday(),
        "weekday_name": db.WEEKDAY_KO[t.weekday()],
        "hour": t.hour,
        "slot10": f"{t.hour:02d}:{t.minute // 10 * 10:02d}",
    }


class Tracker:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ---------- helpers ----------
    def _update(self, trip_id: int, now: datetime, **fields):
        fields["updated_at"] = db.fmt(now)
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE trips SET {cols} WHERE id = ?", (*fields.values(), trip_id))

    def _open(self, stage: str) -> dict[tuple[int, str], sqlite3.Row]:
        rows = self.conn.execute("SELECT * FROM trips WHERE stage = ?", (stage,)).fetchall()
        return {(r["route_id"], r["plate_no"]): r for r in rows}

    def open_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT stage, COUNT(*) c FROM trips WHERE stage IN ('approaching_a','passed_a') GROUP BY stage"
        ).fetchall()
        return {r["stage"]: r["c"] for r in rows}

    # ---------- raw logging ----------
    def record(self, stop_id: int, now: datetime, arrivals: dict[int, RouteArrival] | None, error: str | None):
        self.conn.execute(
            "INSERT INTO polls(polled_at, stop_id, ok, error, route_status) VALUES (?,?,?,?,?)",
            (db.fmt(now), stop_id, int(arrivals is not None), error,
             json.dumps({rid: ra.status for rid, ra in (arrivals or {}).items()})),
        )
        for ra in (arrivals or {}).values():
            for b in ra.buses:
                pred = ra.reference_time + timedelta(seconds=b.remaining_sec or 0)
                self.conn.execute(
                    """INSERT INTO observations(polled_at, reference_time, stop_id, route_id, route_name,
                       plate_no, remaining_sec, remaining_stop, remaining_seat, congestion, status, predicted_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (db.fmt(now), db.fmt(ra.reference_time), stop_id, ra.route_id, ra.route_name,
                     b.plate_no, b.remaining_sec, b.remaining_stop, b.remaining_seat,
                     b.congestion, b.status, db.fmt(pred)),
                )

    # ---------- 광명역5번출구 ----------
    def update_origin(self, now: datetime, arrivals: dict[int, RouteArrival] | None, allow_new: bool):
        open_a = self._open("approaching_a")
        for rid, rname in ROUTES.items():
            ra = (arrivals or {}).get(rid)
            listed = {b.plate_no: b for b in ra.buses} if ra else {}

            for plate, b in listed.items():
                ref = ra.reference_time
                pred = ref + timedelta(seconds=b.remaining_sec or 0)
                row = open_a.get((rid, plate))
                if row:
                    self._update(row["id"], now, a_last_seen=db.fmt(ref),
                                 a_last_remaining_sec=b.remaining_sec, a_last_remaining_stop=b.remaining_stop,
                                 a_seat=b.remaining_seat, a_miss=0, a_first_missing=None)
                    continue
                if not allow_new:
                    continue
                # 같은 차량이 아직 열린 운행(passed_a)을 갖고 있다면 한 바퀴 돌아온 것 -> lost
                for stale in self.conn.execute(
                        "SELECT id FROM trips WHERE stage='passed_a' AND route_id=? AND plate_no=?",
                        (rid, plate)).fetchall():
                    self._update(stale["id"], now, stage="lost", note="reappeared at origin")
                sf = slot_fields(pred)
                self.conn.execute(
                    """INSERT INTO trips(route_id, route_name, plate_no, stage, service_date, weekday, weekday_name,
                         hour, slot10, a_first_seen, a_last_seen, a_last_remaining_sec, a_last_remaining_stop,
                         a_first_predicted, a_seat, created_at, updated_at)
                       VALUES (?,?,?,'approaching_a',?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (rid, rname, plate, sf["service_date"], sf["weekday"], sf["weekday_name"], sf["hour"],
                     sf["slot10"], db.fmt(ref), db.fmt(ref), b.remaining_sec, b.remaining_stop,
                     db.fmt(pred), b.remaining_seat, db.fmt(now), db.fmt(now)),
                )
                log.info("[%s] %s 광명역 접근 감지 (도착예정 %s, %s정거장 전)",
                         rname, plate, pred.strftime("%H:%M:%S"), b.remaining_stop)

            for (r, plate), row in open_a.items():
                if r != rid or plate in listed:
                    continue
                threshold = MISS_THRESHOLD_LISTED if listed else MISS_THRESHOLD_EMPTY
                miss = row["a_miss"] + 1
                first_missing = db.parse(row["a_first_missing"]) or now
                if miss < threshold:
                    self._update(row["id"], now, a_miss=miss, a_first_missing=db.fmt(first_missing))
                    continue
                arr = estimate_arrival(db.parse(row["a_last_seen"]), row["a_last_remaining_sec"], first_missing)
                self._update(row["id"], now, stage="passed_a", a_miss=miss,
                             a_first_missing=db.fmt(first_missing), a_arrival=db.fmt(arr), **slot_fields(arr))
                log.info("[%s] %s 광명역5번출구 통과 %s", rname, plate, arr.strftime("%H:%M:%S"))
        self.conn.commit()

    # ---------- 서울대입구역2번출구 ----------
    def update_dest(self, now: datetime, arrivals: dict[int, RouteArrival] | None):
        open_b = self._open("passed_a")
        for rid, rname in ROUTES.items():
            ra = (arrivals or {}).get(rid)
            listed = {b.plate_no: b for b in ra.buses} if ra else {}

            for (r, plate), row in open_b.items():
                if r != rid:
                    continue
                b = listed.get(plate)
                if b:
                    ref = ra.reference_time
                    pred = ref + timedelta(seconds=b.remaining_sec or 0)
                    f = dict(b_last_seen=db.fmt(ref), b_last_remaining_sec=b.remaining_sec,
                             b_last_remaining_stop=b.remaining_stop, b_miss=0, b_first_missing=None)
                    if not row["b_first_seen"]:
                        f.update(b_first_seen=db.fmt(ref), b_first_predicted=db.fmt(pred))
                    self._update(row["id"], now, **f)
                    continue
                if not row["b_first_seen"]:
                    continue  # 아직 서울대입구역 목록(가까운 1~2대)에 안 들어옴
                threshold = MISS_THRESHOLD_LISTED if listed else MISS_THRESHOLD_EMPTY
                miss = row["b_miss"] + 1
                first_missing = db.parse(row["b_first_missing"]) or now
                if miss < threshold:
                    self._update(row["id"], now, b_miss=miss, b_first_missing=db.fmt(first_missing))
                    continue
                arr = estimate_arrival(db.parse(row["b_last_seen"]), row["b_last_remaining_sec"], first_missing)
                a_arr = db.parse(row["a_arrival"])
                travel = int((arr - a_arr).total_seconds())
                accurate = int((row["a_last_remaining_sec"] or 0) <= ACCURATE_LAST_REMAINING_SEC
                               and (row["b_last_remaining_sec"] or 0) <= ACCURATE_LAST_REMAINING_SEC
                               and travel > 0)
                self._update(row["id"], now, stage="done", b_miss=miss, b_first_missing=db.fmt(first_missing),
                             b_arrival=db.fmt(arr), travel_sec=travel, accurate=accurate)
                log.info("[%s] %s 서울대입구역2번출구 도착 %s, 소요 %.1f분%s", rname, plate,
                         arr.strftime("%H:%M:%S"), travel / 60, "" if accurate else " (정확도 낮음)")
        self.conn.commit()

    def expire(self, now: datetime):
        cutoff = db.fmt(now - TRIP_TIMEOUT)
        n = self.conn.execute(
            "UPDATE trips SET stage='lost', note='timeout', updated_at=? "
            "WHERE stage='passed_a' AND a_arrival < ?", (db.fmt(now), cutoff)).rowcount
        n += self.conn.execute(
            "UPDATE trips SET stage='lost', note='stale at origin', updated_at=? "
            "WHERE stage='approaching_a' AND a_last_seen < ?", (db.fmt(now), cutoff)).rowcount
        if n:
            log.info("타임아웃 처리 %d건", n)
        self.conn.commit()
