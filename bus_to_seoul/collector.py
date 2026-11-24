"""16:00~19:00 1분 단위 수집기."""
from __future__ import annotations

import logging
import sys
import time as _time
from datetime import datetime, timedelta

from . import db
from .config import (COLLECT_END, COLLECT_START, DEST_STOP_ID, KST, ORIGIN_STOP_ID,
                     POLL_INTERVAL_SEC, ROUTES, TRACK_GRACE)
from .naver import NaverBusClient
from .tracker import Tracker

log = logging.getLogger(__name__)


def keep_awake(on: bool):
    """Windows: 수집 중에는 시스템 절전 진입을 막는다 (화면 꺼짐은 허용)."""
    if sys.platform != "win32":
        return
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0)
    ctypes.windll.kernel32.SetThreadExecutionState(flags)


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


def run(force: bool = False, once: bool = False, duration_min: int | None = None):
    conn = db.connect()
    tracker = Tracker(conn)
    client = NaverBusClient()
    started = datetime.now(KST)
    log.info("수집기 시작 (수집 %s~%s, %ss 간격%s)", COLLECT_START, COLLECT_END, POLL_INTERVAL_SEC,
             ", 시간대 무시" if force else "")
    while True:
        now = datetime.now(KST)
        try:
            active = cycle(client, tracker, now, force=force)
        except Exception:
            log.exception("수집 사이클 오류 (다음 분에 재시도)")
            active = True
        keep_awake(active)
        if once:
            keep_awake(False)
            return
        if duration_min and now - started >= timedelta(minutes=duration_min):
            log.info("지정 시간 %d분 경과, 종료", duration_min)
            keep_awake(False)
            return
        if active:
            # 다음 정각 분에 맞춰 대기
            sleep = POLL_INTERVAL_SEC - (datetime.now(KST).timestamp() % POLL_INTERVAL_SEC)
        else:
            # 비수집 시간: 다음 수집 시작까지 (최대 10분 단위로 깨어나 확인)
            nxt = now.replace(hour=COLLECT_START.hour, minute=COLLECT_START.minute, second=0, microsecond=0)
            if nxt <= now:
                nxt += timedelta(days=1)
            sleep = min(600, max(1, (nxt - now).total_seconds()))
        _time.sleep(sleep)
