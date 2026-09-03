  <div class="hero">
    <h1>보조금 많이 주는 지역 <span class="hl">TOP 20</span></h1>
    <p>같은 차인데 주소지에 따라 최대 {{GAP}}만원 차이. 전국 전수 데이터로 줄 세웠습니다.</p>
  </div>
  <p class="stamp">📌 무공해차 통합누리집(ev.or.kr) 지자체 단가 실측 수집 · 단가 수집일 {{ASOF}} · 작성일 2026-08-08 · 최근 갱신 {{MODIFIED}} · 순위는 단가 수집일의 스냅샷이며 잔여·접수 상태는 별개입니다</p>
  <p class="small muted" style="margin:4px 0 0">글: <b>HyeongHun Lee</b> · EV보조금 운영자 — {{N_ALL}}개 지자체 보조금 데이터를 매시간 직접 수집·검증합니다. <a href="/about.html#operator">소개</a></p>

  <div class="callout callout-green">
    <b>3줄 요약</b><br>
    ① 전국 {{N_ALL}}개 지자체의 전기승용 <b>최대 보조금(국비+지방비 합계)</b>을 줄 세우면 1위는 {{FIRST_SIDO}} {{FIRST_NAME}} <b>{{FIRST_AMT}}만원</b>, 최하위는 <b>{{LAST_AMT}}만원</b>{{LAST_PAREN}} — 격차 <b>{{GAP}}만원</b>.<br>
    ② 상위 20위(공동 순위 포함 {{N_TOP}}곳)에 특별·광역시는 <b>{{METRO_TOP}}곳</b>. {{SIDO_MIX}} 등 군 단위와 도 공통 단가 지역이 상위권을 채웁니다.<br>
    ③ 보조금은 <b>주소지(주민등록) 기준</b> — 순위가 높다고 옮겨 가서 받을 수 있는 돈이 아닙니다. 거주요건 판정 기준일은 구매지원신청서 <b>접수일</b>입니다.
  </div>

  <section class="card">
    <h2>승용 최대 보조금 상위 20위 — 전체 표</h2>
    <p class="sub">각 지자체 단가표에서 가장 큰 모델 기준의 국비+지방비 합계입니다(WAV·미지원 표기 모델 제외). 동일 금액은 <b>공동 순위</b>로 묶어, 20위 이내에 든 <b>{{N_TOP}}곳 전체</b>를 실었고, 동률 안에서는 가나다순입니다.</p>
    <div class="tbl-wrap"><table class="tbl">
      <thead><tr><th>순위</th><th>지역 (누르면 상세)</th><th>승용 최대</th></tr></thead>
      <tbody>
{{TOP_ROWS}}
      </tbody>
    </table></div>
    <p class="muted small">{{TIE_NOTE}}표의 금액은 '그 지역에서 가장 많이 받는 모델' 기준이므로, 내 차의 실제 금액은 지역명을 눌러 차종별 표에서 확인하세요. 단가 수집일: {{ASOF}}.</p>
  </section>

  <section class="card">
    <h2>격차는 얼마나 벌어지나 — 숫자로</h2>
    <ul style="padding-left:20px;margin:8px 0;color:var(--text2);font-size:14.5px">
      <li><b>1위 vs 최하위</b> — {{FIRST_NAME}} {{FIRST_AMT}}만원 vs {{LAST_AMT}}만원 → <b>{{GAP}}만원 차이</b>. 같은 차를 사도 주소지가 다르면 이만큼 벌어질 수 있다는 뜻입니다.</li>
      <li><b>상위 5곳 평균 vs 하위 5곳 평균</b> — {{TOP5_AVG}}만원 vs {{BOT5_AVG}}만원 → 약 <b>{{AVG_GAP}}만원 차이</b>.</li>
      <li><b>최하위 {{LAST_AMT}}만원 동률은 {{LAST_COUNT}}곳</b> — {{LAST_LIST}}. {{NEXT_ABOVE}}</li>
    </ul>
    <p>국비 산정액은 전국 어디서나 같은 차면 같습니다. 그러니 이 격차는 <b>전액 지방비(지자체 추가 보조금)에서</b> 나옵니다. 최하위 동률 {{LAST_COUNT}}곳은 지방비가 가장 얇은 지역들인데, {{LAST_SHAPE}}</p>
  </section>

  {{AD1}}

  <section class="card">
    <h2>왜 군 단위가 상위권을 휩쓰나</h2>
    <p>표를 보면 규칙이 하나 보입니다. 상위 {{N_TOP}}곳 중 <b>군 단위가 {{N_GUN}}곳</b>({{TOP_GUN_LIST}} 등){{COMMON_CLAUSE}}입니다. 반대로 인구가 많은 특별·광역시는 {{METRO_POS}}입니다.</p>
    <p>배경으로는 이런 구조가 자주 거론됩니다. 지방비는 각 지자체가 자기 예산과 보급 목표에 맞춰 정하는데, 인구가 적은 지역은 <b>배정 대수가 적은 대신 1대당 단가를 높게</b> 설정해 보급 목표를 채우려는 경향이 있고, 충전 여건·수요가 약한 지역일수록 구매를 당길 유인이 더 필요하다는 점도 꼽힙니다. 다만 단가를 정하는 사정은 지자체마다 달라서, 어느 한 가지 이유로 단정할 수는 없습니다. 확실한 것은 결과뿐입니다 — <b>단가표 위쪽은 군 단위가 차지하고 있다</b>는 것.</p>
    <p>주의할 점도 그 구조에서 나옵니다. 단가가 높은 지역은 물량 자체가 수십 대 수준인 경우가 많아, 금액이 크다고 여유가 있다는 뜻이 아닙니다. 접수 가능 여부는 <a href="status.html">전국 현황판</a>과 해당 지역 페이지에서 따로 확인해야 합니다.</p>
  </section>

  <section class="card">
    <h2>같은 도 안에서도 갈린다 — 실데이터 사례 {{N_CASES}}개</h2>
    <ul style="padding-left:20px;margin:8px 0;color:var(--text2);font-size:14.5px">
{{CASE_ROWS}}
    </ul>
    <p>"우리 도는 얼마"라는 말이 성립하지 않는 이유입니다. 도가 같아도 시·군이 자체적으로 지방비를 정하는 지역에서는 이렇게 벌어집니다. 반드시 <b>내 시·군 단위</b> 페이지로 확인하세요. 전체 지도는 <a href="/">지역별 보조금 현황</a>에 있습니다.</p>
  </section>

  <section class="card">
    <h2>이 랭킹을 오해하면 안 되는 3가지</h2>
    <ul style="padding-left:20px;margin:8px 0;color:var(--text2);font-size:14.5px">
      <li>① <b>주소지 기준이라 이사 없이는 못 받습니다.</b> 보조금은 주민등록상 주소지 지자체에 신청하고, 거주요건 판정 기준일은 <b>구매지원신청서 접수일</b>입니다(계약일·공고일 아님). 지자체별로 '일정 기간 이상 거주' 요건이 붙기도 하니 세부는 공고문으로 — 정리는 <a href="residency.html">거주요건 가이드</a>에. 순위를 보고 주소만 옮기는 위장전입은 부정수급으로 환수 대상입니다.</li>
      <li>② <b>단가 수집일의 스냅샷입니다.</b> 이 표는 {{ASOF}} 수집 단가 기준이며, 추경·단가 조정·회차 변경으로 달라질 수 있습니다. 단가가 바뀌면 이 표도 다음 수집 회차에 함께 갱신됩니다. 유형(우선순위·법인 등)에 따라 금액이 다른 지역도 있습니다.</li>
      <li>③ <b>잔여 상태는 별개입니다.</b> 단가 1위여도 접수가 끝났을 수 있고, 최하위권이어도 물량이 남았을 수 있습니다. 접수 가능 여부는 <a href="status.html">전국 현황판</a>에서, 소진됐다면 <a href="sold-out.html">소진 이후 선택지</a>를 참고하세요.</li>
    </ul>
  </section>

  <p class="muted mt24">함께 보면 좋은 페이지</p>
  <div class="chips">
    <a class="chip" href="/">지역별 보조금 현황</a>
    <a class="chip" href="status.html">전국 현황판</a>
    <a class="chip" href="residency.html">거주요건 가이드</a>
    <a class="chip" href="sold-out.html">소진됐다면 할 일</a>
    <a class="chip" href="articles.html">읽을거리 전체</a>
  </div>
