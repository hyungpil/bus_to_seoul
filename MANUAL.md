# 운영 매뉴얼 — 광명역 → 서울대입구역 버스 모니터

모든 명령은 PowerShell에서 **프로젝트 폴더**에서 실행합니다.

```powershell
cd C:\Users\skplanet\Bus_to_Seoul
```

> 이 PC에서는 `python`이 MS Store 바로가기라 동작하지 않습니다. 항상 **`py`** 로 실행하세요.

---

## 1. 실시간 도착정보 보기

수집기와는 별개입니다. 필요할 때 켜고, 다 보면 꺼도 됩니다(수집에 영향 없음).

### 웹 대시보드 (권장)
```powershell
py -m bus_to_seoul web
```
브라우저에서 **http://127.0.0.1:8507** 을 엽니다. 끄려면 PowerShell 창에서 `Ctrl+C`를 누릅니다.

화면 구성
- **광명역5번출구 도착 예정**: 노선별로 다가오는 1~2대의 도착 시각, 몇 분 후, 몇 정거장 전, 차량번호, 잔여좌석, 혼잡도
- **서울대입구역2번출구 예상**: 같은 요일·시간대의 과거 평균 소요시간으로 계산합니다. 데이터가 쌓이기 전에는 "과거 데이터 없음"으로 나옵니다.
- **광명역 통과 후 추적 중**: 수집기가 추적 중인 버스의 서울대입구역 도착 예정 시각(실시간 값 또는 과거 평균)
- **요일·시간대별 평균 소요시간 / 최근 광명역 통과 기록**: DB에 쌓인 내용

실시간 정보는 30초마다, 통계는 2분마다 자동으로 갱신됩니다.

### 터미널로 보기
```powershell
py -m bus_to_seoul monitor            # 30초마다 갱신, Ctrl+C로 종료
py -m bus_to_seoul monitor --once     # 한 번만 출력
```

---

## 2. 자동 수집 — PC만 켜져 있으면 되나?

**네. 아래 조건을 지키면 매일 자동으로 수집됩니다.**

| 항목 | 내용 |
|---|---|
| 자동 실행 | 작업 스케줄러 `BusToSeoul-Collector`가 매일 **15:55**에 수집기를 띄움 (콘솔 창 없음) |
| 수집 | **16:00~19:00**에 1분마다 광명역·서울대입구역을 조회 |
| 추적 | 19시 이후에는 새 버스를 받지 않고, 이미 잡은 버스만 서울대입구역 도착까지 최대 2시간 더 추적 |
| 종료 | 시작 후 5시간(약 20:55)이 지나면 스스로 종료 |
| 절전 방지 | 수집 중에는 PC가 절전 모드에 들어가지 않음 (화면은 꺼져도 됨) |
| 배터리 | 배터리 사용 중에도 실행됨 |

### 지켜야 할 것
1. **16:00~19:00에 PC가 켜져 있고 내 계정으로 로그인돼 있어야 합니다.** 화면이 잠겨 있는 건 괜찮지만, 로그아웃하거나 PC를 끄면 수집하지 않습니다.
2. **덮개를 닫지 마세요.** 노트북은 덮개를 닫으면 절전으로 들어갈 수 있습니다. 덮개를 닫아야 한다면 `제어판 → 전원 옵션 → 덮개를 닫으면 수행되는 작업`에서 **"아무 것도 안 함"** 으로 바꿔야 합니다(회사 정책으로 막혀 있을 수 있음).
3. **15:55에 PC가 꺼져 있었다면** 켜고 로그인하는 즉시 수집기가 시작됩니다. 꺼져 있던 시간의 데이터는 비게 됩니다.
4. **인터넷 연결**이 필요합니다. 연결이 잠깐 끊기면 그 분만 실패로 기록되고 다음 분에 다시 조회합니다.

### 스케줄러 관리
```powershell
# 등록 상태 확인 (State = Ready 이면 정상)
Get-ScheduledTask -TaskName BusToSeoul-Collector | Get-ScheduledTaskInfo

# 지금 바로 한 번 실행 (16~19시가 아니면 대기만 함)
Start-ScheduledTask -TaskName BusToSeoul-Collector

# 실행 중인 수집기 중지
Stop-ScheduledTask -TaskName BusToSeoul-Collector

# 다시 등록 (설정을 바꿨을 때)
powershell -ExecutionPolicy Bypass -File .\register_task.ps1

# 등록 삭제
Unregister-ScheduledTask -TaskName BusToSeoul-Collector -Confirm:$false
```
GUI로 보려면 `Win+R → taskschd.msc → 작업 스케줄러 라이브러리 → BusToSeoul-Collector`로 들어갑니다.

---

## 3. 데이터가 잘 쌓이는지 확인하기

### 한 번에 점검 (권장)
```powershell
py -m bus_to_seoul check            # 최근 7일
py -m bus_to_seoul check --days 30  # 최근 30일
```

출력 예
```
=== 1. 작업 스케줄러 ===
  상태: Ready / 마지막 실행: 2026-11-25 15:55 (성공) / 다음 실행: 2026-11-26 15:55

=== 2. DB (C:\Users\skplanet\Bus_to_Seoul\data\bus.db) ===
  마지막 조회: 2026-11-25 20:31:00

  날짜          요일    조회   실패   광명역통과   완료   정확   유실
  2026-11-25  수      410     2       24     21     19      3
```

**정상 판단 기준 (평일 하루)**

| 컬럼 | 의미 | 정상 범위 |
|---|---|---|
| 조회 | 네이버 API 조회 횟수 | **약 360회 이상**: 16~19시 동안 2곳 × 180분, 여기에 19시 이후 추적분이 더해짐 |
| 실패 | 조회 실패 횟수 | 0에 가까울수록 좋음. 수십 회 이상이면 네트워크나 API 문제 |
| 광명역통과 | 광명역5번출구 통과가 기록된 버스 수 | 8507은 10~12분, 6401은 20~40분 간격이므로 **대략 20~25대** |
| 완료 | 서울대입구역 도착까지 추적이 끝난 운행 | 광명역통과와 비슷해야 함 |
| 정확 | 통계에 쓰는 운행 (양쪽 도착 판정 오차 3분 이내) | 완료의 대부분 |
| 유실 | 추적에 실패한 운행 | 소수면 정상 (버스 회차, 결행, API 누락 등) |

**이상 신호와 조치**

| 증상 | 원인 | 조치 |
|---|---|---|
| 그날 줄이 아예 없음 | 그 시간에 PC가 꺼져 있었거나 절전, 로그아웃 상태 | 2장 "지켜야 할 것" 확인 |
| 조회가 360보다 훨씬 적음 | 수집 도중 PC가 절전에 들어감 | 덮개, 전원 설정 확인 |
| 마지막 실행이 "오류 코드 ..." | 수집기 실행 오류 | 아래 로그 확인 |
| 실패가 많고 로그에 HTTPError가 반복됨 | 네이버 API 변경 또는 차단 | 로그 내용을 개발 담당에게 전달 |

### 로그 확인
로그 파일은 `C:\Users\skplanet\Bus_to_Seoul\logs\collector.log`에 있습니다.

```powershell
# 마지막 30줄
Get-Content .\logs\collector.log -Tail 30 -Encoding UTF8

# 실시간으로 따라 보기 (수집 중에 실행, Ctrl+C 종료)
Get-Content .\logs\collector.log -Tail 20 -Wait -Encoding UTF8

# 경고, 오류만 보기
Select-String -Path .\logs\collector.log -Pattern "WARNING|ERROR" -Encoding UTF8 | Select-Object -Last 20

# 오늘 서울대입구역 도착(소요시간)만 보기
Select-String -Path .\logs\collector.log -Pattern "$(Get-Date -Format yyyy-MM-dd).*서울대입구역2번출구 도착" -Encoding UTF8
```

정상일 때는 이런 로그가 보입니다.
```
INFO collector: 수집기 시작 (수집 16:00:00~19:00:00, 60s 간격)
INFO tracker: [8507] 경기72사1293 광명역 접근 감지 (도착예정 16:52:21, 1정거장 전)
INFO tracker: [8507] 경기72사1293 광명역5번출구 통과 16:50:52
INFO tracker: [8507] 경기72사1293 서울대입구역2번출구 도착 17:24:10, 소요 33.3분
INFO collector: 지정 시간 300분 경과, 종료
```
- `WARNING ... 조회 실패`: 그 분의 조회가 실패한 것입니다. 가끔 나오면 무시해도 됩니다.
- `(정확도 낮음)`: 도착 판정 오차가 커서 통계에서 제외된 운행입니다.
- 2026-11-24 16시 이전 로그에는 설치 때 돌린 테스트 기록이 섞여 있습니다. 이 기록은 실제 DB(`data\bus.db`)에는 들어가지 않았습니다.

### 쌓인 통계 보기
```powershell
py -m bus_to_seoul stats
```
노선 × 요일 × 시간대별 운행 건수와 평균·최소·최대 소요시간(분)을 보여줍니다. 웹 대시보드 하단에서도 같은 내용을 볼 수 있습니다.

### DB 직접 보기 (선택)
DB 파일은 `data\bus.db`(SQLite)입니다. [DB Browser for SQLite](https://sqlitebrowser.org/) 같은 도구로 열 수 있습니다.

| 테이블/뷰 | 내용 |
|---|---|
| `v_travel_stats` | 요일 × 시간대별 평균 소요시간 |
| `v_travel_stats_slot10` | 요일 × 10분 슬롯별 평균 소요시간 |
| `v_origin_arrivals` | 버스별 광명역 통과 시각, 서울대입구역 도착 시각, 소요시간 |
| `trips` | 운행 추적 원본 |
| `observations` | 1분 단위 원본 관측 |

엑셀로 내보내기:
```powershell
py -c "import sqlite3,csv; c=sqlite3.connect('data/bus.db'); cur=c.execute('select * from v_origin_arrivals'); w=csv.writer(open('trips.csv','w',newline='',encoding='utf-8-sig')); w.writerow([d[0] for d in cur.description]); w.writerows(cur)"
```
실행하면 `trips.csv`가 생기고, 엑셀에서 바로 열 수 있습니다.

---

## 빠른 점검 체크리스트

- [ ] 처음 며칠은 저녁에 `py -m bus_to_seoul check`를 실행해 그날 줄이 생겼고 조회가 360회 이상인지 확인
- [ ] 1주일에 한 번 `check --days 7`로 빠진 날짜가 없는지 확인
- [ ] 16~19시에는 PC를 켜고 로그인한 상태로, 덮개는 열어 둠
- [ ] 출퇴근 전 실시간 정보는 `py -m bus_to_seoul web`으로 확인
