"""SQLite 저장소. 시각은 모두 KST 'YYYY-MM-DD HH:MM:SS' 문자열."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .config import DB_PATH, KST, ACCURATE_LAST_REMAINING_SEC

WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

SCHEMA = f"""
-- GitHub Actions 1분 주기 원본 관측 (두 정류장 x 두 노선 x 차량)
CREATE TABLE IF NOT EXISTS observations (
    id              INTEGER PRIMARY KEY,
    polled_at       TEXT NOT NULL,
    reference_time  TEXT NOT NULL,
    stop_id         INTEGER NOT NULL,
    route_id        INTEGER NOT NULL,
    route_name      TEXT NOT NULL,
    plate_no        TEXT NOT NULL,
    remaining_sec   INTEGER,
    remaining_stop  INTEGER,
    remaining_seat  INTEGER,
    congestion      TEXT,
    status          TEXT,
    predicted_at    TEXT          -- reference_time + remaining_sec
);
CREATE INDEX IF NOT EXISTS ix_obs_stop_time ON observations(stop_id, polled_at);
CREATE INDEX IF NOT EXISTS ix_obs_plate ON observations(plate_no, polled_at);

-- 폴링 사이클 로그 (응답 실패/NO_RESULT 추적용)
CREATE TABLE IF NOT EXISTS polls (
    id          INTEGER PRIMARY KEY,
    polled_at   TEXT NOT NULL,
    stop_id     INTEGER NOT NULL,
    ok          INTEGER NOT NULL,
    error       TEXT,
    route_status TEXT            -- JSON: {{route_id: status}}
);

-- 차량 1회 운행(광명역 -> 서울대입구역) 추적
--   stage: approaching_a -> passed_a -> done | lost
CREATE TABLE IF NOT EXISTS trips (
    id                  INTEGER PRIMARY KEY,
    route_id            INTEGER NOT NULL,
    route_name          TEXT NOT NULL,
    plate_no            TEXT NOT NULL,
    stage               TEXT NOT NULL,
    service_date        TEXT NOT NULL,     -- 광명역 도착 기준 날짜
    weekday             INTEGER,           -- 0=월 .. 6=일
    weekday_name        TEXT,
    hour                INTEGER,           -- 광명역 도착 시각의 시
    slot10              TEXT,              -- 광명역 도착 시각 10분 단위 (예: '16:30')

    a_first_seen        TEXT,
    a_last_seen         TEXT,
    a_last_remaining_sec INTEGER,
    a_last_remaining_stop INTEGER,
    a_first_predicted   TEXT,              -- 처음 봤을 때 예측한 광명역 도착시각
    a_miss              INTEGER DEFAULT 0,
    a_first_missing     TEXT,
    a_arrival           TEXT,              -- 추정 광명역 도착(통과) 시각
    a_seat              INTEGER,           -- 광명역 직전 잔여좌석

    b_first_seen        TEXT,
    b_last_seen         TEXT,
    b_last_remaining_sec INTEGER,
    b_last_remaining_stop INTEGER,
    b_first_predicted   TEXT,
    b_miss              INTEGER DEFAULT 0,
    b_first_missing     TEXT,
    b_arrival           TEXT,              -- 추정 서울대입구역2번출구 도착 시각

    travel_sec          INTEGER,           -- b_arrival - a_arrival
    accurate            INTEGER DEFAULT 0, -- 양쪽 모두 직전 남은시간 <= {ACCURATE_LAST_REMAINING_SEC}s
    note                TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_trips_open ON trips(stage, route_id, plate_no);
CREATE INDEX IF NOT EXISTS ix_trips_slot ON trips(weekday, hour);

-- 요일 x 시간대별 소요시간 통계 (정확도 기준 통과한 완료 운행만)
CREATE VIEW IF NOT EXISTS v_travel_stats AS
SELECT route_name, weekday, weekday_name, hour,
       COUNT(*)                         AS trips,
       ROUND(AVG(travel_sec)/60.0, 1)   AS avg_min,
       ROUND(MIN(travel_sec)/60.0, 1)   AS min_min,
       ROUND(MAX(travel_sec)/60.0, 1)   AS max_min
FROM trips
WHERE stage = 'done' AND accurate = 1
GROUP BY route_name, weekday, hour;

-- 10분 슬롯 단위 통계
CREATE VIEW IF NOT EXISTS v_travel_stats_slot10 AS
SELECT route_name, weekday, weekday_name, slot10,
       COUNT(*)                         AS trips,
       ROUND(AVG(travel_sec)/60.0, 1)   AS avg_min,
       ROUND(MIN(travel_sec)/60.0, 1)   AS min_min,
       ROUND(MAX(travel_sec)/60.0, 1)   AS max_min
FROM trips
WHERE stage = 'done' AND accurate = 1
GROUP BY route_name, weekday, slot10;

-- 광명역 도착 기록 (요일/시간대별 몇 대가 언제 왔는지)
CREATE VIEW IF NOT EXISTS v_origin_arrivals AS
SELECT service_date, weekday_name, hour, slot10, route_name, plate_no,
       a_first_predicted, a_arrival, a_seat, b_arrival,
       ROUND(travel_sec/60.0, 1) AS travel_min, stage, accurate
FROM trips
WHERE a_arrival IS NOT NULL
ORDER BY a_arrival;
"""


def fmt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")


def parse(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn
