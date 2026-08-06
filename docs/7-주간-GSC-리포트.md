# 7. 주간 서치콘솔 리포트 자동화

매주 **월요일 09:20**, launchd 잡 `com.evbojo.gscreport`이 Google Search Console 실적을 API로 받아
주간 리포트를 만들고 macOS 알림으로 요약을 띄운다.

## 산출물 (repo가 public이라 전부 git 미추적 — 로컬 전용)

| 파일 | 내용 |
|---|---|
| `updater/reports/latest.md` | 최신 리포트 (총괄 WoW · 관심 키워드 순위 · TOP 검색어/페이지 · 신규 진입 · 일별 추이) |
| `updater/reports/gsc-<종료일>.md` | 주차별 보관본 |
| `updater/reports/raw/*.json` | 원시 데이터 (추이 분석·재가공용) |
| `updater/gsc_report.log` | 실행 로그 (1000줄 롤링) |

리포트 기간 = "최근 확정 7일"(오늘−3일까지 — GSC 데이터가 약 3일 지연되므로) + 직전 7일 비교.
관심 키워드 목록은 `updater/gsc_report.py` 상단 `WATCH_QUERIES`에서 수정.

## 1회 설정 — 서비스계정 키 발급 (이것만 하면 끝)

리포트는 서비스계정 키 `updater/secrets/gsc-sa.json`이 있어야 동작한다. 없으면
"설정 필요" 알림만 뜨고 조용히 넘어간다. 발급 절차(구글 계정 = 서치콘솔 소유 계정, metlit):

1. **Google Cloud 콘솔**(console.cloud.google.com) → 프로젝트 선택/생성 (예: `evbojo-reports`)
2. **API 및 서비스 → 라이브러리** → "Google Search Console API" 검색 → **사용 설정**
3. **API 및 서비스 → 사용자 인증 정보 → 사용자 인증 정보 만들기 → 서비스 계정**
   - 이름 예: `gsc-report` → 만들기 (역할 부여 불필요 — 건너뛰기)
4. 만든 서비스 계정 클릭 → **키 탭 → 키 추가 → 새 키 만들기 → JSON** → 다운로드
5. 다운로드한 JSON을 이 경로에 저장:
   ```bash
   mkdir -p "updater/secrets" && chmod 700 "updater/secrets"
   mv ~/Downloads/<다운로드된-키>.json "updater/secrets/gsc-sa.json"
   ```
6. **서치콘솔**(search.google.com/search-console) → `evbojo.co.kr` 도메인 속성 → **설정 → 사용자 및 권한 → 사용자 추가**
   - 이메일 = 서비스계정 이메일(JSON 안 `client_email`, `...@....iam.gserviceaccount.com`)
   - 권한 = **제한된 사용자**(읽기만이라 충분)
7. 검증:
   ```bash
   bash updater/run_gsc_report.sh && cat updater/reports/latest.md
   ```

## 설치 / 재설치 (launchd)

```bash
cp deploy/launchd/com.evbojo.gscreport.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.evbojo.gscreport.plist
# 즉시 1회 실행해보기
launchctl kickstart gui/$(id -u)/com.evbojo.gscreport
```

## 장애 대응

- **알림 "설정 필요"**: 위 1회 설정 미완 — 키 파일 경로 확인.
- **API 403**: 서치콘솔 속성에 서비스계정 이메일이 사용자로 추가 안 됨(6번 단계). 로그에 이메일이 찍힌다.
- **토큰 발급 오류**: 키 JSON 손상 또는 시계 오차. 키 재발급이 가장 빠름.
- **데이터가 비어 보임**: 신생 사이트라 노출 자체가 적은 기간엔 정상. 리포트는 0값도 표로 표시한다.
- 리포트·키는 절대 커밋 금지(.gitignore로 방어됨) — repo가 public이다.
