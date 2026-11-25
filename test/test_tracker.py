"""오프라인 시뮬레이션: python -m unittest discover test"""
import sqlite3
import unittest
from datetime import datetime, timedelta

from bus_to_seoul import db
from bus_to_seoul.config import KST
from bus_to_seoul.naver import Bus, RouteArrival
from bus_to_seoul.tracker import Tracker

R8507 = 11039196


def ra(t, buses):
    return {R8507: RouteArrival(R8507, "8507", "RUNNING" if buses else "NO_RESULT", t,
                                [Bus(p, s, st, 40, "여유", "RUNNING") for p, s, st in buses])}


class TrackerTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(db.SCHEMA)
        self.tr = Tracker(self.conn)

    def test_full_trip(self):
        t0 = datetime(2026, 11, 24, 16, 30, tzinfo=KST)   # 화요일
        m = lambda n: t0 + timedelta(minutes=n)
        # 광명역: 3분 전 -> 1분 전(50초) -> 사라짐(다른 버스는 보임)
        self.tr.update_origin(m(0), ra(m(0), [("A1", 180, 2)]), True)
        self.tr.update_dest(m(0), ra(m(0), []))
        self.tr.update_origin(m(1), ra(m(1), [("A1", 50, 1), ("A2", 700, 5)]), True)
        self.tr.update_origin(m(2), ra(m(2), [("A2", 640, 4)]), True)
        row = self.conn.execute("SELECT * FROM trips WHERE plate_no='A1'").fetchone()
        self.assertEqual(row["stage"], "passed_a")
        self.assertEqual(row["a_arrival"], "2026-11-24 16:31:50")
        self.assertEqual(row["weekday_name"], "화")
        # 서울대입구역: 처음엔 목록에 없음 -> 나타남 -> 마지막 90초 -> 사라짐(목록 비어있음: 3회 필요)
        self.tr.update_dest(m(5), ra(m(5), [("Z9", 100, 1)]))
        self.tr.update_dest(m(10), ra(m(10), [("A1", 1500, 6)]))
        self.tr.update_dest(m(35), ra(m(35), [("A1", 90, 1)]))
        self.tr.update_dest(m(36), ra(m(36), []))
        self.tr.update_dest(m(37), ra(m(37), []))
        self.assertEqual(self.conn.execute("SELECT stage FROM trips WHERE plate_no='A1'").fetchone()[0], "passed_a")
        self.tr.update_dest(m(38), ra(m(38), []))
        row = self.conn.execute("SELECT * FROM trips WHERE plate_no='A1'").fetchone()
        self.assertEqual(row["stage"], "done")
        # 예측(17:06:30)보다 먼저(17:06:00) 사라졌으므로 사라진 시각으로 잘림
        self.assertEqual(row["b_arrival"], "2026-11-24 17:06:00")
        self.assertEqual(row["travel_sec"], 34 * 60 + 10)
        self.assertEqual(row["accurate"], 1)
        st = self.conn.execute("SELECT * FROM v_travel_stats").fetchone()
        self.assertEqual((st["weekday_name"], st["hour"], st["trips"]), ("화", 16, 1))

    def test_flaky_no_result_does_not_close(self):
        t0 = datetime(2026, 11, 24, 16, 0, tzinfo=KST)
        self.tr.update_origin(t0, ra(t0, [("A1", 400, 3)]), True)
        self.tr.update_origin(t0 + timedelta(minutes=1), None, True)          # 응답 실패
        self.tr.update_origin(t0 + timedelta(minutes=2), ra(t0, []), True)    # NO_RESULT
        self.tr.update_origin(t0 + timedelta(minutes=3), ra(t0 + timedelta(minutes=3), [("A1", 200, 2)]), True)
        row = self.conn.execute("SELECT stage, a_miss FROM trips").fetchone()
        self.assertEqual((row["stage"], row["a_miss"]), ("approaching_a", 0))

    def test_no_new_trips_outside_window(self):
        t0 = datetime(2026, 11, 24, 19, 1, tzinfo=KST)
        self.tr.update_origin(t0, ra(t0, [("A1", 400, 3)]), False)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
