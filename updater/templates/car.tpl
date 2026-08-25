<div class="hero" style="text-align:left;padding-bottom:0">
  <p class="muted small">{{MAKER}}</p>
  <h1>{{NAME}}</h1>
  <p>{{SUB}}</p>
</div>

{{DISC_BANNER}}

<section class="card">
  <h2 class="mt0">📝 {{NAME}} 보조금 정리</h2>
  {{PROSE}}
</section>

{{AD1}}

<section class="card">
  <h2 class="mt0">📊 인증 제원</h2>
  {{SPECS}}
  {{WINTER}}
</section>

<section class="card">
  <h2 class="mt0">시도별 보조금 요약 <span class="sub">{{NAME}} 기준 · 국비 동일, 지방비만 지역차</span></h2>
  <div class="tbl-wrap">
    <table class="tbl">
      <thead><tr><th>시도</th><th class="num">지역 수</th><th class="num">합계 범위</th><th>최고 지역</th></tr></thead>
      <tbody>{{SIDO_ROWS}}</tbody>
    </table>
  </div>
  <p class="small muted mt8">{{DIST_LINE}}</p>
</section>

<section class="card">
  <h2 class="mt0">지역별 국비+지방비 합계 <span class="sub">{{TABLE_SUB}}</span></h2>
  <div class="tbl-wrap">
    <table class="tbl" data-live="fulltable" data-kind="car" data-id="{{ID}}">
      <thead><tr><th>지역</th><th class="num">지방비</th><th class="num">합계</th></tr></thead>
      <tbody>{{TABLE_ROWS}}</tbody>
    </table>
  </div>
  <button class="btn btn-ghost btn-block" data-live="expand" hidden>전체 {{REGION_COUNT}}개 지역 모두 보기</button>
  <p class="small muted mt8">금액은 단가 기준(만원)으로 접수 마감 여부와 무관 — 우리 지역 잔여·마감 상태는 각 지역 페이지에서 확인</p>
</section>

<div class="grid2">
  <button class="btn btn-ghost" data-live="cmp" data-id="{{ID}}">🚗 비교함에 담기</button>
  <a class="btn btn-ghost" href="calc.html?id={{ID}}">⛽ 유지비 계산기로 보기</a>
</div>

<section class="card">
  <h2 class="mt0">같은 모델 다른 트림</h2>
  <div class="rowlist">{{TRIMS}}</div>
</section>

<section class="card">
  <h2 class="mt0">함께 읽으면 좋은 글</h2>
  <div class="chips">{{RELATED}}</div>
  <p class="stamp mt8">데이터 수집·검증: EV보조금 운영자 <a href="/about.html#operator" style="color:inherit;text-decoration:underline">HyeongHun Lee</a> · <a href="/about.html#method" style="color:inherit;text-decoration:underline">수집·검증 방법</a> · 출처 무공해차 통합누리집(ev.or.kr)</p>
</section>

{{AD2}}
