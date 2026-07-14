# ⚡ EV보조금 — 전국 전기차 구매보조금 현황 사이트

2026년 전국 **161개 지자체 × 117개 전기승용 모델**의 구매보조금(국비+지방비+전환지원금)과
접수 잔여현황을 한눈에 보여주는 정적 웹사이트. NAS에서 서빙하며 **매시간 자동 갱신**됩니다.

- 데이터 출처: 무공해차 통합누리집(ev.or.kr) — 2026-07-15 전량 실측 수집
- 검증: 계산된 지역별 최대보조금이 ev.or.kr 공식 요약표와 **161/161 일치**

## 폴더 구조
```
site/            ← 웹루트 (이 폴더만 서빙하면 됨)
  index.html       홈 (지역 선택 · 차종 검색 · TOP10 랭킹)
  region.html      지역 상세 (차종별 보조금 표 · 잔여현황 · 문의처)
  car.html         차종 상세 (보조금 · 실구매가 영수증 · 겨울 주행거리)
  calc.html        유지비 계산기 (집밥/급속 믹스 · 겨울 보정 · 충전손실 10%)
  compare.html     최대 3대 비교
  check.html       30초 자격 자가진단 (청년·다자녀·차상위·전환)
  refund.html      환수금 계산기 (의무운행 2년 · 요율표 · D-day)
  guide.html       신청 절차 7단계 / law.html 제도·법령 / faq.html FAQ
  about.html · privacy.html · 404.html · sitemap.xml · robots.txt · ads.txt
  assets/          css/js (프레임워크 없음, 시스템 폰트 — 빠름)
  data/            cars.json · regions.json · status.json · meta.json
updater/         자동 갱신기 (Playwright — ev.or.kr 웹방화벽 대응)
deploy/          docker-compose.yml + nginx.conf (NAS용)
docs/            1-NAS배포 · 2-도메인연결 · 3-수익화 가이드
```

## 빠른 시작
```bash
# 로컬 미리보기
python3 -m http.server 8899 --directory site

# NAS 배포 (웹 + 매시간 갱신기)
docker compose -f deploy/docker-compose.yml up -d
```

## 데이터 갱신 정책
| 데이터 | 주기 | 파일 |
|---|---|---|
| 접수현황(공고/접수/출고/잔여) | 매시간 | status.json |
| 차종 국비·지자체 지방비 단가 | 매일 04시 | cars.json, regions.json |
| 실패 시 | 기존 데이터 유지 + 로그, 14일 경과 시 화면에 자동 경고 배너 |
| 급변(40%↑) 감지 시 | `_pending/` 보류 후 수동 확인 (`FORCE=1`로 강제 적용) |

## 커스터마이즈 포인트
- 도메인: `site/robots.txt`, `site/sitemap.xml` 의 evbojo.com 교체
- 광고: `site/assets/js/app.js` 상단 `SITE.ads` (AdSense pub ID), `site/ads.txt`
- 이메일: app.js 푸터 / about / privacy 의 hlee9108@gmail.com
