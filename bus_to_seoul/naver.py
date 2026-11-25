"""네이버 지도 대중교통 실시간 API 클라이언트."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import requests

from .config import KST

BASE = "https://map.naver.com/p/api/pubtrans"
HEADERS = {
    "User-Agent": "BusToSeoul/1.0",
    "Referer": "https://map.naver.com/",
    "Accept": "application/json",
}


@dataclass
class Bus:
    plate_no: str
    remaining_sec: int | None
    remaining_stop: int | None
    remaining_seat: int | None
    congestion: str | None
    status: str | None
    low_floor: bool = False
    last: bool = False


@dataclass
class RouteArrival:
    route_id: int
    route_name: str
    status: str               # RUNNING / NO_RESULT / ...
    reference_time: datetime
    buses: list[Bus] = field(default_factory=list)


class NaverBusClient:
    def __init__(self, timeout: float = 10.0):
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self.timeout = timeout

    def _get(self, path: str, **params):
        r = self.s.get(f"{BASE}{path}", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def arrivals_raw(self, stop_id: int) -> list[dict]:
        return self._get("/realtime/bus/arrivals", stopId=stop_id)

    def route(self, route_id: int) -> dict:
        return self._get(f"/bus/routes/{route_id}")

    def arrivals(self, stop_id: int, route_ids) -> dict[int, RouteArrival]:
        """정류장의 실시간 도착 정보 중 route_ids 노선만 파싱해 돌려준다."""
        return parse_arrivals(self.arrivals_raw(stop_id), route_ids)


def _parse_time(s: str | None) -> datetime:
    if not s:
        return datetime.now(KST)
    return datetime.fromisoformat(s).astimezone(KST)


def parse_arrivals(raw: list[dict], route_ids) -> dict[int, RouteArrival]:
    wanted = set(route_ids)
    out: dict[int, RouteArrival] = {}
    for item in raw:
        rid = item.get("id")
        if rid not in wanted:
            continue
        arr = item.get("arrival") or {}
        buses = []
        for b in arr.get("buses") or []:
            if not b.get("plateNo"):
                continue
            buses.append(Bus(
                plate_no=b["plateNo"],
                remaining_sec=b.get("remainingTime"),
                remaining_stop=b.get("remainingStop"),
                remaining_seat=b.get("remainingSeat"),
                congestion=(b.get("congestion") or {}).get("desc"),
                status=(b.get("operatingStatus") or {}).get("code") or b.get("status"),
                low_floor=bool(b.get("lowFloor")),
                last=bool(b.get("last")),
            ))
        out[rid] = RouteArrival(
            route_id=rid,
            route_name=item.get("name", str(rid)),
            status=arr.get("status") or "UNKNOWN",
            reference_time=_parse_time(arr.get("referenceTime")),
            buses=buses,
        )
    return out
