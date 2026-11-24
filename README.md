# Bus to Seoul — 광명역 → 서울대입구역 광역버스 모니터

KTX광명역5번출구 → 서울대입구역2번출구 구간의 **8507 / 6401** 버스를 네이버 지도 실시간 정보로 모니터링하고,
16:00~19:00 동안 1분 단위로 수집해 차량번호별로 추적하여 **요일·시간대별 소요시간을 DB화**합니다.

## 실행

운영·점검 방법은 **[MANUAL.md](MANUAL.md)** 참고.

```powershell
pip install -r requirements.txt
py -m bus_to_seoul web        # 대시보드 http://127.0.0.1:8507
py -m bus_to_seoul monitor    # 터미널 모니터 (30초 갱신)
py -m bus_to_seoul collect    # 수집기 (상시 실행; 16~19시에만 조회)
py -m bus_to_seoul check      # 스케줄러·DB 축적·로그 점검
py -m bus_to_seoul stats      # 요일·시간대별 평균 소요시간
py -m unittest discover tests # 추적 로직 테스트
```

매일 자동 수집: `register_task.ps1` 실행 (매일 15:55 작업 스케줄러 등록).

## 데이터 출처 (네이버 지도 내부 API)

| 용도 | 엔드포인트 |
|---|---|
| 정류장 실시간 도착 | `map.naver.com/p/api/pubtrans/realtime/bus/arrivals?stopId={id}` |
| 노선 정보(정류장 목록) | `map.naver.com/p/api/pubtrans/bus/routes/{routeId}` |

| 대상 | 네이버 ID |
|---|---|
| KTX광명역5번출구 (14389) | stopId `92965` |
| 서울대입구역2번출구 (21252) | stopId `150834` |
| 8507 | routeId `11039196` |
| 6401 | routeId `20046644` |

비공식 API라 예고 없이 바뀔 수 있습니다. 분당 2회(정류장 2곳)만 조회합니다.

## 추적 방식

도착 목록은 노선별로 가장 가까운 1~2대만 보여주므로, **목록에 있던 차량번호가 빠지는 순간을 도착(통과)** 으로 봅니다.
도착 시각 = 마지막 관측의 `기준시각 + 남은시간`을 `[마지막 관측, 빠진 걸 확인한 시각]` 범위로 잘라 추정(오차 ≤ 1분).

```
approaching_a ─(광명역 목록에서 빠짐)→ passed_a ─(서울대입구역 목록에 나타났다 빠짐)→ done
                                           └─(150분 초과)→ lost
```

- 네이버가 가끔 `NO_RESULT`(빈 목록)를 주므로 빈 목록/응답 실패는 3회 연속일 때만 통과로 판정
- 19:00 이후엔 새 버스는 안 받고, 이미 잡힌 버스만 최대 2시간 더 추적
- 사라지기 직전 남은시간이 양쪽 모두 3분 이하인 운행만 `accurate=1` → 통계에 사용

## DB (`data/bus.db`, SQLite)

- `observations` — 1분 단위 원본 (정류장, 노선, 차량번호, 남은시간/정거장/좌석, 예측도착시각)
- `trips` — 차량 1회 운행: 광명역 도착, 서울대입구역 도착, `travel_sec`, 요일/시/10분 슬롯
- `v_travel_stats` / `v_travel_stats_slot10` — 요일×시간대(시/10분) 평균·최소·최대 소요시간
- `v_origin_arrivals` — 광명역 도착 기록
- `polls` — 조회 성공/실패 로그

실시간 화면의 "서울대입구역 예상 도착"은 같은 요일·시간대 평균 → 같은 시간대 전체 → 전체 평균 순으로 사용합니다.
