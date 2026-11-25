# Bus to Seoul — 광명역 → 서울대입구역 광역버스 모니터

GitHub Actions와 GitHub Pages로 운영되는 KTX광명역5번출구 → 서울대입구역2번출구 버스 모니터링 프로젝트입니다.
네이버 지도 실시간 도착정보를 수집해 8507과 6401의 차량번호별 통과 시각과 소요시간을 SQLite에 저장하고,
정적 JSON과 GitHub Pages 화면으로 제공합니다.

## 운영 방식

- 외부 cron이 매 5분마다 GitHub Actions를 호출합니다. GitHub schedule 트리거는 사용하지 않습니다.
- 각 실행에서 `python -m bus_to_seoul collect`를 단회 실행합니다.
- 수집 시간은 한국 시간 기준 10:00~24:00이며, 그 시간에 광명역 통과 후보를 새로 기록합니다.
- 이미 광명역을 지난 버스는 최대 150분까지 추적합니다.
- 각 실행마다 SQLite와 정적 JSON을 갱신하고 GitHub 저장소에 변경분을 커밋합니다.
- GitHub Pages는 별도의 로컬 서버나 로컬 PC 작업 스케줄러 없이 동작합니다.

실행 주기는 [.github/workflows/pages.yml](/workspaces/bus_to_seoul/.github/workflows/pages.yml)에 정의되어 있습니다.

## 데이터 수집 주기

GitHub Actions가 매 5분마다 한 번 조회합니다.
10:00~24:00에 차량번호를 확인해 광명역 접근을 감지하고, 같은 차량을 이후 실행에서 서울대입구역에서 추적합니다.
목록에서 차량이 빠진 시점을 기준으로 통과 시각을 추정합니다.

## 주요 명령

```bash
python -m bus_to_seoul collect        # GitHub Actions 단회 수집
python -m bus_to_seoul collect --force # 수집 시간대 무시
python -m bus_to_seoul export-static  # live.json, stats.json 생성
python -m bus_to_seoul stats          # 누적 통계 출력
python -m bus_to_seoul check --days 7 # 최근 수집 상태 점검
python -m unittest discover test       # 추적 로직 테스트
```

`collect`는 상시 루프나 로컬 데몬이 아닌 한 번의 수집 사이클로 종료합니다.

## GitHub Pages

GitHub Actions가 다음 순서로 정적 사이트를 배포합니다.

1. 저장소와 Python 의존성을 준비합니다.
2. 실시간 버스 데이터를 한 번 조회합니다.
3. SQLite와 정적 JSON을 갱신합니다.
4. 변경된 데이터를 저장소에 커밋합니다.
5. [site/](/workspaces/bus_to_seoul/site/)를 GitHub Pages에 배포합니다.

수동 실행은 GitHub 저장소의 Actions에서 `Deploy GitHub Pages` 워크플로우의 `Run workflow`를 사용합니다.

## 외부 cron 설정

Cron 서비스는 5분마다 다음 GitHub API를 호출합니다.

- URL: `https://api.github.com/repos/hyungpil/bus_to_seoul/dispatches`
- HTTP method: `POST`
- Headers: `Accept: application/vnd.github+json`, `Authorization: Bearer <GitHub PAT>`
- Body: `{"event_type":"collect-bus-data"}`

PAT에는 이 저장소에 대한 Actions 실행 권한이 필요하며, cron 서비스의 비밀 값으로 저장합니다.

## 데이터 출처

네이버 지도 내부 공개 전송 대중교통 API의 실시간 도착정보를 사용합니다.

| 항목 | 설정 |
|---|---|
| 출발 정류장 | KTX광명역5번출구 |
| 도착 정류장 | 서울대입구역2번출구 |
| 대상 노선 | 8507, 6401 |
| 수집 시간 | 매일 10:00~24:00 |
| 외부 cron 주기 | 매 5분 |
