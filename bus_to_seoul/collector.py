"""GitHub Actions에서 실행되는 단회 수집기."""
from __future__ import annotations

import logging
from datetime import datetime

from . import db
from .config import (COLLECT_END, COLLECT_START, DEST_STOP_ID, KST, ORIGIN_STOP_ID,
                     ROUTES, TRACK_GRACE)
from .naver import NaverBusClient
from .tracker import Tracker

log = logging.getLogger(__name__)


def in_window(now: datetime) -> bool:
    return COLLECT_START <= now.time() < COLLECT_END


def in_grace(now: datetime) -> bool:
    end = now.replace(hour=COLLECT_END.hour, minute=COLLECT_END.minute, second=0, microsecond=0)
    return end <= now < end + TRACK_GRACE


def poll_stop(client: NaverBusClient, tracker: Tracker, stop_id: int, now: datetime):
    try:
        arr = client.arrivals(stop_id, ROUTES.keys())
        err = None
    except Exception as e:  # 네트워크/일시 오류는 다음 분에 재시도
        arr, err = None, f"{type(e).__name__}: {e}"
        log.warning("정류장 %s 조회 실패: %s", stop_id, err)
    tracker.record(stop_id, now, arr, err)
    return arr


def cycle(client: NaverBusClient, tracker: Tracker, now: datetime, force: bool = False):
    window = force or in_window(now)
    counts = tracker.open_counts()
    grace = force or in_grace(now)
    poll_a = window or (grace and counts.get("approaching_a", 0) > 0)
    if poll_a:
        tracker.update_origin(now, poll_stop(client, tracker, ORIGIN_STOP_ID, now), allow_new=window)
    # 광명역 갱신 직후 passed_a가 새로 생겼을 수 있으므로 다시 센다
    poll_b = window or (grace and tracker.open_counts().get("passed_a", 0) > 0)
    if poll_b:
        tracker.update_dest(now, poll_stop(client, tracker, DEST_STOP_ID, now))
    tracker.expire(now)
    return poll_a or poll_b


def run(force: bool = False):
    conn = db.connect()
    tracker = Tracker(conn)
    client = NaverBusClient()
    now = datetime.now(KST)
    log.info("단회 수집 시작 (수집 %s~%s%s)", COLLECT_START, COLLECT_END,
             ", 시간대 무시" if force else "")
    try:
        cycle(client, tracker, now, force=force)
    except Exception:
        log.exception("수집 사이클 오류")
        raise
    finally:
        conn.close()
