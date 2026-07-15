# 🔎 검색엔진 등록 · AdSense 현황 (2026-07-15)

## 완료된 것 ✅
| 항목 | 상태 |
|---|---|
| **Google Search Console** | ✅ 소유권 인증 완료 (HTML 파일: site/google26c5d436316c40f8.html — 삭제 금지) |
| **Google 사이트맵** | ✅ sitemap.xml 제출 완료 (277개 URL) |
| **Google 색인** | ✅ 홈이 이미 색인되어 있음 + 재색인 요청 제출 — 수일 내 "전기차 보조금" 롱테일부터 노출 시작 |
| **evbojo.co.kr / evbojo.kr** | ✅ 둘 다 미등록(등록 가능) 확인 — KISA whois 기준 |
| **키워드 최적화** | ✅ 메타 키워드·설명, 페이지별 동적 타이틀, FAQ 구조화데이터(JSON-LD), OG 태그 |

## 남은 것 (짧은 사용자 작업) ⬜

### ① 도메인 구매 — evbojo.co.kr (약 5분, 연 1.5~2만원)
1. gabia.com → 검색창에 `evbojo.co.kr` → 장바구니 → 결제 (개인정보 노출방지 서비스 무료 체크)
2. 구매 직후 저에게 알려주시면: DNS 연결(가이드 2번), 사이트 도메인 전환(`python3 tools/set_domain.py https://evbojo.co.kr` + CNAME 파일), 서치콘솔 도메인 속성 추가, 다음 검색등록까지 이어서 처리합니다.

### ② 네이버 서치어드바이저 (약 3분 — 브라우저 확장이 naver 접근을 차단해 직접 못 했습니다)
1. searchadvisor.naver.com → 네이버 로그인 → 웹마스터 도구
2. 사이트 등록: `https://hlee-mrs.github.io/evbojo/` (도메인 연결 후엔 evbojo.co.kr 추가)
3. 소유확인 → **HTML 파일 업로드** 방식 선택 → 파일명(naverXXXX.html)과 내용이 표시됨
   → **그 파일명/내용을 저에게 알려만 주세요. 사이트 배포는 제가 합니다** → 소유확인 클릭
4. 확인 후: 요청 → 사이트맵 제출: `https://hlee-mrs.github.io/evbojo/sitemap.xml`
   요청 → 웹 페이지 수집: 홈 URL 1회
> 네이버는 국내 검색의 절반 이상 — 꼭 해두세요. 초기 6개월은 네이버 블로그에 요약글+본진 링크 병행이 효과적입니다(수익화 가이드 참고).

### ③ 다음(Daum) 검색등록 (도메인 연결 후 — 제가 처리)
다음 검색등록은 **대표 도메인만** 받습니다(서브패스 불가 — 실제 시도로 확인).
evbojo.co.kr 연결 후 register.search.daum.net에서 제가 대신 제출해 드립니다 (로그인 불필요, 처리 결과 수신 이메일만 필요).

### ④ AdSense / 애드핏 (계정 생성·약관 동의·수취 계좌는 본인만 가능)
**순서 추천: 애드핏 먼저(심사 빠름) → 도메인 연결 + 콘텐츠 보강 후 AdSense**
- **카카오 애드핏**: adfit.kakao.com → 가입 → 매체 등록(사이트 URL) → 승인 후 광고단위(DAN-…) 생성
  → `site/assets/js/app.js`의 `ads.adfitUnits`에 슬롯별 ID 입력 + `provider:'adfit'`, `enabled:true` (코드는 이미 준비됨)
- **AdSense**: adsense.google.com → 가입(사이트: evbojo.co.kr 권장) → 심사 통과 후
  → `ads.client`에 ca-pub ID + `enabled:true`, `site/ads.txt` 주석 해제, 각 슬롯 data-ad-slot 번호 입력
- 두 경우 모두 코드 수정이 어렵다면 승인 ID만 저에게 알려주세요 — 제가 반영합니다.

## 색인 확인 방법
- 구글: `site:hlee-mrs.github.io/evbojo` 검색 / Search Console → 색인생성 → 페이지
- 네이버: 서치어드바이저 → 리포트 → 색인 현황
- 보통 구글 수일, 네이버 1~2주, 다음 2~4주(심사제) 걸립니다.
