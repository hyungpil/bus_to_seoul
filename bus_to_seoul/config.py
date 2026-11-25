"""서비스 설정값.

정류장/노선 ID는 네이버 지도 내부 ID다.
  - 노선 ID: map.naver.com/p/api/search/instant-search?query=8507
  - 정류장 ID: map.naver.com/p/api/pubtrans/bus/routes/{routeId} 의 busStops[].id
"""
import os
from datetime import time, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))  # 한국은 DST 없음

# 출발 정류장: KTX광명역5번출구 (정류장번호 14389)
ORIGIN_STOP_ID = 92965
ORIGIN_STOP_NAME = "KTX광명역5번출구"

# 도착 정류장: 서울대입구역2번출구 (정류장번호 21252)
DEST_STOP_ID = 150834
DEST_STOP_NAME = "서울대입구역2번출구"

# 대상 노선 (네이버 routeId -> 노선번호)
ROUTES = {
    11039196: "8507",
    20046644: "6401",
}

# GitHub Actions 수집 시간대 (KST). 이 구간에 광명역 도착을 수집하고,
# 이미 광명역을 지난 버스는 TRACK_GRACE 동안 서울대입구역까지 계속 추적한다.
COLLECT_START = time(10, 0)
COLLECT_END = time(23, 59, 59, 999999)
TRACK_GRACE = timedelta(minutes=120)

# 광명역 통과 후 이 시간 안에 서울대입구역 도착이 확인되지 않으면 lost 처리
TRIP_TIMEOUT = timedelta(minutes=150)

# 사라짐 판정: 같은 노선의 다른 버스는 보이는데 이 차량만 빠진 경우 1회,
# 노선 목록 자체가 비었거나 응답 실패(네이버가 가끔 NO_RESULT를 줌)인 경우 3회 연속
MISS_THRESHOLD_LISTED = 1
MISS_THRESHOLD_EMPTY = 3

# 통계에 쓸 '정확한' 도착 판정 기준: 사라지기 직전 관측의 남은시간이 이 값 이하
ACCURATE_LAST_REMAINING_SEC = 180

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("BUS_DB") or ROOT / "data" / "bus.db")  # 테스트 시 BUS_DB로 분리
LOG_DIR = ROOT / "logs"
