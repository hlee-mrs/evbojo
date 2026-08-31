<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<!-- Google Analytics (GA4) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-2Q0YFZGWWB"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-2Q0YFZGWWB');</script>
<!-- Google AdSense -->
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-7688026325140831" crossorigin="anonymous"></script>
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- 하위 경로(/region/ 등)에서도 상대 URL이 루트 기준으로 풀리도록 base 고정 — app.js의 data/*.json fetch·nav 링크가 그대로 동작 -->
<base href="/">
<title>{{TITLE}}</title>
<meta name="description" content="{{DESC}}">{{ROBOTS}}
<link rel="canonical" href="{{CANONICAL}}">
<link rel="stylesheet" href="assets/css/main.css">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>⚡</text></svg>">
<meta name="naver-site-verification" content="29413de3319d0b4b5a504cdbb92084043d6d663b" />
<meta name="naver-site-verification" content="6a560bf53350f3b601da82f08e43384e76844919" />
<meta name="naver-site-verification" content="a5ce2391aae3ed03c0769d1d857d7a22e02ffb61" />
{{JSONLD}}
</head>
<body>
<!-- 정적 nav — app.js가 동일 마크업으로 재렌더(내용 동일 → 시프트 없음). JS 꺼져도 완전한 내비게이션 -->
<header id="site-header" class="site-header"><div class="inner">
  <a class="logo" href="/"><span class="bolt">⚡</span>EV보조금</a>
  <nav class="gnb" aria-label="주 메뉴"><a href="/">홈</a><a href="status.html">전국 현황판</a><details class="nav-dd"><summary>도구</summary><div class="dd"><a href="calc.html">유지비 계산기</a><a href="check.html">자격 진단</a><a href="refund.html">환수 계산</a><a href="compare.html">차종 비교</a></div></details><details class="nav-dd"><summary>가이드</summary><div class="dd"><a href="guide.html">신청 절차</a><a href="law.html">제도·법령</a><a href="faq.html">FAQ</a></div></details><details class="nav-dd"><summary>읽을거리</summary><div class="dd"><a href="articles.html">읽을거리 전체</a><a href="brief/">일일 브리핑</a><a href="model/">모델별 시리즈</a></div></details></nav>
</div></header>

<main class="container">
<nav class="small muted" aria-label="현재 위치" style="margin:14px 0 0">{{BREADCRUMB}}</nav>
{{MAIN}}
</main>

<footer id="site-footer" class="site-footer"><div class="inner">
  <div class="links">
    <a href="about.html">사이트 소개</a><a href="articles.html">읽을거리</a><a href="privacy.html">개인정보처리방침</a>
    <a href="donate.html">💛 후원하기</a>
    <a href="https://ev.or.kr" target="_blank" rel="noopener">무공해차 통합누리집 ↗</a>
    <a href="report.html">오류 제보</a>
  </div>
  <div id="foot-stamp">단가 수집일 <b>{{META_UPDATED}}</b> · 출처 무공해차 통합누리집(ev.or.kr) · 2026년 전기승용 기준</div>
  <div class="disclaimer">
    본 사이트는 <b>정부·공공기관과 무관한 개인 운영 정보 사이트</b>입니다. 게시된 보조금·제도 정보는 참고용이며 법적 효력이 없습니다.
    실제 지원 금액·자격·잔여 물량은 반드시 <b>무공해차 통합누리집(ev.or.kr)</b>과 관할 지자체 공고문으로 확인하세요.
    본 사이트는 광고(Google AdSense 등)를 게재하며, 광고 수익으로 운영됩니다.
  </div>
  <div class="mt8">© 2026 EV보조금 · 데이터 출처: 무공해차 통합누리집(ev.or.kr)</div>
</div></footer>
<script src="assets/js/app.js" defer></script>
<script src="assets/js/detail.js" defer></script>
</body>
</html>
