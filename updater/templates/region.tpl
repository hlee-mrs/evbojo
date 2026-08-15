<div class="hero" style="text-align:left;padding-bottom:0">
  <h1>{{NAME}} <span class="hl">전기차 보조금</span></h1>
  <p>{{SUB}}</p>
</div>

<section class="card">
  <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
    <span data-live="badge" data-cd="{{CD}}"><span class="badge {{BADGE_CLS}}" style="font-size:14px;padding:6px 14px"><span class="dot"></span>{{BADGE_LABEL}}</span></span>
    {{HEAD_NUMS}}
  </div>
  {{PROG}}
  {{STATUS_LINES}}
  <div data-live="cats" data-cd="{{CD}}"></div>
  <div class="grid2 mt8">
    {{TEL_BTN}}
    <a class="btn btn-ghost" href="https://ev.or.kr/nportal/buySupprt/initSubsidyPaymentCheckAction.do" target="_blank" rel="noopener">ev.or.kr에서 잔여 확인 ↗</a>
  </div>
  <p class="stamp">{{STAMP}}</p>
</section>

<section class="card">
  <h2 class="mt0">📝 {{NAME}} 보조금 한눈에</h2>
  {{PROSE}}
</section>

{{NOTE_SECTION}}

{{AD1}}

<section class="card">
  <h2 class="mt0">차종별 보조금 <span class="sub">{{TABLE_SUB}}</span></h2>
  <div class="tbl-wrap">
    <table class="tbl" data-live="fulltable" data-kind="region" data-cd="{{CD}}">
      <thead><tr><th>차종</th><th class="num">국비</th><th class="num">지방비</th><th class="num">합계</th><th></th></tr></thead>
      <tbody>{{TABLE_ROWS}}</tbody>
    </table>
  </div>
  <button class="btn btn-ghost btn-block" data-live="expand" hidden>전체 {{MODEL_COUNT}}개 모델 모두 보기</button>
  <div class="callout mt16 small">
    · 표의 금액은 <b>2026년 전기승용 기준 단가</b>(만원, 국비+지방비) — 실제 지급액은 공고·차량 인증사양별 기본가격 구간에 따라 변동 가능<br>
    · <b>전환지원금</b>: 기존 내연기관차를 폐차·처분하고 전기차로 전환할 때 추가 지원(국비 최대 100만원+지방비, 세부 요건은 지자체 공고 확인)<br>
    · 지방비 0원 차종은 해당 지자체 미지원 또는 공고 확인 필요
  </div>
</section>

<section class="card">
  <h2 class="mt0">같은 {{SIDO_LABEL}} 다른 지역</h2>
  <div class="chips">{{SIBLINGS}}</div>
  <p class="small muted mt8"><i class="chip-dot" style="background:var(--badge-open)"></i>접수 중 · <i class="chip-dot" style="background:var(--badge-low)"></i>임박 · <i class="chip-dot" style="background:var(--badge-closed)"></i>마감/소진 — 보조금은 <b>주민등록 주소지</b> 기준이에요</p>
</section>

<section class="card">
  <h2 class="mt0">다음 단계</h2>
  <div class="chips">
    <a class="chip" href="check.html">✅ 내 자격·추가혜택 진단</a>
    <a class="chip" href="calc.html">⛽ 유지비 계산</a>
    <a class="chip" href="guide.html">📋 신청 절차</a>
    <a class="chip" href="price-tiers.html">💰 가격구간(기본가격) 읽는 법</a>
  </div>
</section>

{{AD2}}
