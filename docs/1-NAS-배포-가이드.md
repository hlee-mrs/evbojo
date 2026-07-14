# 🖥️ NAS 배포 가이드 (A to Z)

목표: NAS에서 `EV보조금` 사이트를 서빙하고, **매시간 자동으로 데이터가 갱신**되게 만들기.
Synology 기준으로 설명하며 QNAP/기타 Docker 지원 NAS도 동일한 구조입니다.

## 0. 준비물
- Docker(Container Manager) 지원 NAS
- 이 프로젝트 폴더 전체를 NAS로 복사 (예: `/volume1/docker/evbojo/`)
  - `site/` — 웹사이트 본체 (정적 파일 + data/*.json)
  - `deploy/` — docker-compose.yml, nginx.conf
  - `updater/` — 자동 갱신기 (Playwright)

## 1. 컨테이너 실행 (5분)
SSH 접속 후:
```bash
cd /volume1/docker/evbojo
docker compose -f deploy/docker-compose.yml up -d
```
확인:
```bash
curl -s http://localhost:8080/data/meta.json   # JSON 나오면 성공
docker logs -f evbojo-updater                   # 갱신기 로그
```
> Synology GUI로 하려면: Container Manager → 프로젝트 → 생성 → `deploy/docker-compose.yml` 선택.

- 웹서버: `evbojo-web` (nginx, 8080 포트 → 원하는 포트로 변경 가능)
- 갱신기: `evbojo-updater`
  - **매시간** 접수현황(잔여대수) → `status.json`
  - **매일 새벽 4시(KST)** 차종·지자체 단가 전체 재수집 → `cars.json`, `regions.json`, `meta.json`
  - 주기 변경: docker-compose.yml의 `STATUS_EVERY_MIN`, `FULL_AT_HOUR`

### 갱신기 안전장치 (알아두면 좋아요)
| 상황 | 동작 |
|---|---|
| ev.or.kr 접속 실패 | 3회 재시도(20s→40s→80s) 후 포기, **기존 데이터 유지** |
| 수집 데이터 검증 실패(행 수 부족 등) | 교체하지 않음, `updater/updater.log` 기록 |
| 단가 변경률 40% 초과(사이트 개편 의심) | `data/_pending/`에 보류 저장. 확인 후 `FORCE=1`로 적용 |
| 파일 교체 | 원자적(os.replace) — 서빙 중 깨진 JSON 없음 |
| 화면 표시 | 데이터가 14일 이상 오래되면 사이트가 자동으로 "오래됨" 배너 표시 |

수동 실행:
```bash
docker exec evbojo-updater python /app/updater/update.py --status   # 현황만
docker exec evbojo-updater python /app/updater/update.py --full     # 전체 (약 5~8분)
```

## 2. 외부 공개 (포트포워딩)
1. 공유기 관리자 페이지 → 포트포워딩: 외부 `80, 443` → NAS IP의 `8080` (또는 리버스 프록시 사용 시 그대로)
2. **Synology 리버스 프록시(권장)**: 제어판 → 로그인 포털 → 고급 → 리버스 프록시
   - 소스: `https://도메인:443` → 대상: `http://localhost:8080`
3. 방화벽에서 80/443 허용

## 3. HTTPS
- **방법 A (권장) — Cloudflare 프록시**: 도메인 가이드(2번 문서) 참고. NAS 인증서 불필요, 캐싱·DDoS 방어 덤.
- **방법 B — Synology Let's Encrypt**: 제어판 → 보안 → 인증서 → Let's Encrypt 추가 (80 포트 개방 필요), 리버스 프록시에 연결.

## 4. Web Station으로만 서빙하고 싶다면 (Docker 없이)
- Web Station → 웹 서비스 포털 생성 → 문서 루트를 `site/` 폴더로.
- 이 경우 갱신기는 **작업 스케줄러**로:
  - 제어판 → 작업 스케줄러 → 사용자 정의 스크립트
  - 매시간: `docker run --rm -v /volume1/docker/evbojo/site:/app/site -v /volume1/docker/evbojo/updater:/app/updater -e DATA_DIR=/app/site/data mcr.microsoft.com/playwright/python:v1.45.0-jammy bash -c "pip -q install playwright && python /app/updater/update.py --status"`
  - (Docker 없이 순수 파이썬은 불가 — ev.or.kr 웹방화벽 때문에 실제 브라우저가 필요합니다)

## 5. 업데이트/백업
- 사이트 수정: `site/` 파일 교체만 하면 즉시 반영 (정적 파일)
- 데이터 백업: `site/data/*.json.bak` 자동 생성 + NAS 스냅샷/Hyper Backup 권장
- 로그 확인: `updater/updater.log`

## 문제 해결
| 증상 | 해결 |
|---|---|
| updater가 계속 실패 | `docker logs evbojo-updater` 확인. ev.or.kr 점검 시간일 수 있음(새벽). 지속되면 사이트 구조 변경 → update.py 셀렉터 점검 |
| 잔여대수가 안 변함 | status.json의 updated 값 확인. 컨테이너 시간대(TZ=Asia/Seoul) 확인 |
| 포트 충돌 | docker-compose.yml에서 `8080:80`을 `8081:80` 등으로 변경 |
