<div class="hero" style="text-align:left;padding-bottom:0">
  <p class="muted small">모델별 보조금 심층 시리즈</p>
  <h1>{{NAME}}</h1>
  <p>{{SUB}}</p>
</div>

<p class="stamp">글·데이터: HyeongHun Lee (<a href="about.html#operator">EV보조금 운영자</a>) · 게시 {{PUBLISHED}} · 데이터 기준 {{ASOF}}</p>

<section class="card">
  {{PROSE}}
</section>

{{AD1}}

<section class="card">
  <h2 class="mt0">{{GROUP}} 트림별 국비·제원 <span class="sub">{{TRIM_SUB}}</span></h2>
  <div class="tbl-wrap">
    <table class="tbl">
      <thead><tr><th>트림</th><th class="num">국비</th><th class="num">주행거리 상온/저온</th><th class="num">추정 전비</th></tr></thead>
      <tbody>{{TRIM_ROWS}}</tbody>
    </table>
  </div>
  <p class="small muted mt8">국비 단위는 만원, 주행거리는 국내 인증값(km), 추정 전비는 주행거리÷배터리 용량(km/kWh·충전 손실 제외). 트림명을 누르면 트림별 상세 페이지로 이동해요.</p>
</section>

<section class="card">
  <h2 class="mt0">지역별 국비+지방비 합계 상위 15 <span class="sub">{{REGION_SUB}}</span></h2>
  <p class="small muted">대표 트림 <b>{{REP_NAME}}</b>(그룹 내 국비 최고 현행 트림) 기준</p>
  <div class="tbl-wrap">
    <table class="tbl">
      <thead><tr><th>지역</th><th class="num">합계</th><th>접수 상태</th></tr></thead>
      <tbody>{{REGION_ROWS}}</tbody>
    </table>
  </div>
  {{DIST}}
</section>

<section class="card">
  <h2 class="mt0">함께 보면 좋은 자료</h2>
  <div class="chips">{{RELATED}}</div>
</section>

{{AD2}}
