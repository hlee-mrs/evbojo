# 전기차 보조금 현황(evbojo) — 프로젝트 헌법 (모든 대화에 자동 로드)

> 목적: 매 세션 결과가 **흔들리지 않게(no drift)** 불변식·절차를 고정한다. 제정 2026-08-15.
> 상세 운영은 `docs/1~7` — 특히 [docs/6 자동화 운영](docs/6-자동화-운영-가이드.md). ⚠️ **이 repo(hlee-mrs/evbojo)는 public이다.**

## 0. 정체성 (1줄)

2026년 전국 **161개 지자체 × 117개 전기승용 모델**의 구매보조금·접수 잔여현황 정적 사이트(**evbojo.co.kr** = GitHub Pages+Cloudflare). 이 Mac의 launchd가 매시 무인 수집·배포하며, 수익모델은 AdSense(3차 심사 대비 재설계 완료). 데이터 정확성 실측: 지역별 최대보조금 ev.or.kr 공식 요약표와 **161/161 일치**(2026-07-15).

## 1. ★이 repo 특유의 함정: 매시 :10에 봇이 커밋·푸시한다

`com.evbojo.updater`(launchd)가 매시 :10에 `run_auto.sh` 실행: lock → `git fetch`+`rebase --autostash` → 수집 → `git add site/data`(+프리렌더 시 `site/region site/car site/sido site/sitemap.xml`) → 커밋 → **main 전체 push** → `subtree split`으로 gh-pages 강제 푸시.

- 세션 시작 시 `git pull --rebase --autostash` 먼저.
- **push하면 안 되는 변경은 커밋도 하지 않는다** — 로컬 커밋은 다음 정시에 봇이 그대로 밀어버린다. 이 repo에서 **커밋 = 배포 승인**으로 취급하고, 배포까지 의도된 변경만 커밋한다.
- 봇 스테이징 경로 밖의 파일(이 파일 포함)은 untracked로 두면 봇이 건드리지 않는다.
- `updater/.auto.lock/`이 존재하면 수집이 진행 중 — git 조작을 보류한다.

## 2. 불변식 (INVARIANTS)

| # | 불변식 | 이유 / 근거 | 변경 시 필수 절차 |
|---|---|---|---|
| I1 | **`history.json` 단일 작성자 = 이 Mac의 launchd**. NAS·GitHub Actions 등 다른 수집 주체 추가 금지. | 동시 기록 시 이력 꼬임 → 예측 기능 오염 ([docs/6 §단일 작성자](docs/6-자동화-운영-가이드.md)). | 다른 주체를 세우려면 **먼저 이쪽 launchd를 끈다**. |
| I2 | **fail-safe 교체 정책 약화 금지**: 검증 실패(행 수 부족·값 이상) 시 교체 안 함, full 40%↑ 급변은 `_pending/` 보류, 모든 쓰기는 `os.replace` 원자 교체. | 서빙 중 깨진 JSON 노출 방지 + 사이트 구조 변경(수집 오염) 방어 — `update.py` 설계 원칙. | `FORCE=1`은 `_pending/` diff를 **사람이 확인한 뒤에만**. |
| I3 | **콘텐츠는 실측 사실만**: 점추정 예측 금지 · 마감은 **완료형 선언만** 인정(조건부·미래형은 절대 마감 아님) · WAV/미지원 차종은 최고액 서술 제외 · 데이터 모순 시 단정 문장 생략. | 보조금 오정보는 실구매 결정에 직결. `detectClosed`·prerender 산문 로직이 보수적으로 설계된 이유. | `prerender.py`/`app.js` 산문·마감 로직 변경 시 이 원칙 유지 + 프리뷰로 실제 문장 확인. |
| I4 | **AdSense 정책 설계 약화 금지**: 정적 산문 1,200자 미만·noindex 페이지엔 광고 슬롯 자체를 생성 안 함 · 고정 높이(CLS<0.1)+"AD" 라벨+입력폼과 24px 간격 · '전기차 보조금' 키워드 문단당 1회 이하. | **심사 2회 탈락 후** 정책 원문 기반 전면 재설계(commit `004b8e8`)로 확립. | 광고·콘텐츠 밀도 관련 변경은 [docs/3](docs/3-수익화-가이드.md) 정책 항목 대조 후. |
| I5 | **GitHub Pages "Enforce HTTPS"는 OFF 유지**. | Cloudflare **Flexible SSL** 구조 — 켜면 리다이렉트 루프로 사이트 전체 다운 (docs/6 경고). | SSL 모드 자체를 바꾸는 작업(docs/4)에서만, 사용자 확인 후. |
| I6 | **public repo 방어선**: `updater/secrets/`·`updater/reports/`·로그는 커밋 금지(.gitignore가 정본), GSC 소유확인 파일 `site/google26c5d436316c40f8.html` 삭제 금지. | repo가 public이라 유출 = 즉시 공개 (docs/7 경고). | .gitignore 방어선 축소 금지. |
| I7 | **`prerender.py`는 stdlib 전용 + `/usr/bin/python3` 고정**, 전량 재생성·멱등, 부분 파일 금지(메모리 완성 후 원자 쓰기, 중간 오류 시 기존 파일 보존). | launchd 최소 환경에서 의존성 없이 돌아야 무인 운영이 유지됨. | 외부 패키지가 필요하면 prerender가 아니라 `update.py` 쪽에(Playwright 선례). |
| I8 | **크롤 예절 유지**: UA에 연락처 명시, `PAGE_DELAY` ≥ 1.2초, 재시도는 지수 백오프 3회. ev.or.kr은 WAF(JS 챌린지)라 Playwright 필수 — requests/curl 전환 금지. | 공공 사이트 차단당하면 데이터 파이프라인 전체가 죽는다. | 주기 단축·병렬화는 사용자 승인 후. |
| I9 | **발행 게이트·noindex 정책**: `publish`(KST)가 미래인 시리즈는 생성 안 함 · 9999(한국환경공단)·단종(disc) 페이지는 noindex · **/brief/ 전체 noindex**(자동 집계 페이지 — 발행·홈 배너는 유지) · **차종은 모델그룹 대표 트림(국비 최고 비단종)만 색인**, 비대표 트림은 noindex(트림 근사중복 차단) · noindex/미발행은 sitemap 제외 · 미발행 페이지로의 링크 금지 · sitemap lastmod는 실변경일만(정적=파일 mtime, 시리즈=발행일). | 시차 발행 + 애드센스 3차 반려(2026-08-26, 저가치) 감사 결과 — 심사·검색 표면에는 편집 콘텐츠와 대표 페이지만. | 색인 정책 완화(브리핑 재색인, 전 트림 색인)는 애드센스 승인 후 사용자 확인을 받고 단계적으로. |

> 불변식과 충돌하는 요청이 오면: 차단하지 말고 충돌을 설명한 뒤, 안전한 대안 + 위 표의 변경 절차를 제시한다.

## 3. 검증 게이트 (완료 선언·커밋 전)

```bash
# 1) 프리렌더 — exit 0 확인 (콘텐츠·데이터·템플릿 변경 시)
python3 updater/prerender.py

# 2) 로컬 프리뷰 — 변경 페이지 눈으로 확인 (.claude/launch.json과 동일 포트)
python3 -m http.server 8746 --directory site

# 3) 커밋 전 — 의도한 파일만 있는지
git status --short --branch

# 4) 자동화를 건드렸으면 — 잡 상태 + 최근 회차
launchctl list | grep evbojo
grep -E "RUN|OK|FAIL|SKIP" updater/auto.log | tail -10

# 5) 배포 검증 (push 후) — 라이브 신선도
curl -s https://evbojo.co.kr/data/status.json | python3 -c "import json,sys; print(json.load(sys.stdin)['updated'])"
```

- 수집기 수동 테스트는 가벼운 `/usr/bin/python3 updater/update.py --status`로만 (full은 04시 봇 소관).
- 라이브가 로컬보다 오래되면 GitHub Pages 빌드 지연부터 의심 — 진단·재빌드 명령은 docs/6 §장애 대응.

## 4. 안전 경계

- **자동 OK**: 읽기·분석 / `site/`·`updater/`·`docs/` 편집 / prerender / 로컬 프리뷰 / `auto.log`·`launchctl` 점검 / `update.py --status` 수동 1회(예절 파라미터 기본값 유지).
- **사용자 확인 필수**: 커밋(§1 — 이 repo에선 배포 승인과 동일) / launchd plist·스케줄 변경 / `FORCE=1` 적용 / gh-pages 수동 조작·Pages 설정 / Cloudflare·GSC·AdSense 콘솔 조작 / 도메인 작업.
- **`site/data/*.json` 직접 수정 금지**: 수집 산출물이라 다음 회차에 덮인다. 지속되는 수정은 `updater/` 로직으로.

## 5. 정본(source of truth) 포인터

- **데이터**: ev.or.kr 실측 → `site/data/*.json` (스키마·수집 로직 정본은 `update.py`)
- **서빙**: `site/`만 서빙. 배포 경로는 main push → 봇의 subtree → gh-pages → GitHub Pages+Cloudflare. NAS/docker는 대안 경로(docs/1)
- **자동화**: `updater/run_auto.sh` + plist 사본 `deploy/launchd/` + 운영 문서 docs/6. 로그 `updater/auto.log`(2000줄 롤링)
- **커밋 스타일**: Conventional Commits + 한국어 제목(`feat:`/`fix:`/`chore:`/`ops:`, scope 예 `(현황판)`), 본문은 개조식+실측치. 봇 커밋(`data: 자동 갱신…`)은 건드리지 않는다
- **SEO·수익화 현황**: docs/5(등록 상태·남은 작업) · docs/3(광고 정책). 시리즈 원고: `updater/content/{sido,model}/*.md`
- **도메인·SSL·캐시**: docs/2·4·6 (Cloudflare 계정 정보는 docs/6)

---
*이 파일은 현재 git 미추적(봇 스테이징 경로 밖). 내용은 public-safe로 작성했으므로 커밋해도 되지만, 커밋하면 다음 정시에 봇이 push하여 공개 repo에 올라간다 — 원하면 지시할 것.*
