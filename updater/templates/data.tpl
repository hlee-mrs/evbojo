<div class="hero" style="text-align:left;padding-bottom:0">
  <p class="muted small">데이터·방법론</p>
  <h1>전기차 보조금 데이터는 어떻게 수집·검증·공개되나</h1>
  <p>이 사이트의 모든 숫자는 어디서 오고, 무엇을 뜻하고, 어디까지 믿어도 되는지 — 그리고 그대로 내려받는 법.</p>
</div>

<p class="stamp"><span>글: HyeongHun Lee (<a href="about.html#operator">EV보조금 운영자</a>) · <span data-derived>잔여현황 기준 {{STATUS_UPDATED}} · 단가 수집일 {{META_UPDATED}}</span> · 이 페이지의 수치는 매시간 자동 갱신</span></p>

<section class="card">
  <h2 class="mt0">무엇을 모으나</h2>
  <p style="line-height:1.75;margin:10px 0">무공해차 통합누리집(ev.or.kr) 보조금관리시스템이 공개하는 2026년 전기승용 구매보조금 자료를 <b>지자체 <span data-derived>{{N_REGIONS}}</span>곳 × 현행 트림 <span data-derived>{{N_TRIMS}}</span>종</b>(단종 포함 <span data-derived>{{N_TRIMS_ALL}}</span>종) 단위로 모읍니다. 공단 데이터에는 지자체별 공고 차수와 접수기간, 유형별(우선순위·법인·기관·택시·일반) 물량도 있어 함께 수집합니다.</p>
  <div class="tbl-wrap"><table class="tbl">
    <thead><tr><th>파일</th><th>내용</th><th>갱신</th></tr></thead>
    <tbody>
      <tr><td><a href="data/regions.csv">regions.csv</a></td><td>지역코드·지역명·시도·승용 최대 보조금(국비+지방비, 만원)·올해 공고·접수·출고·잔여 대수·공단 등록 접수상태·이 사이트의 상태 판정·기준시각</td><td>매시간</td></tr>
      <tr><td><a href="data/cars.csv">cars.csv</a></td><td>트림 ID·제조사·트림명·국비(만원)·상온/저온 주행거리(km)·배터리 용량(kWh)·단종 여부·단가 수집일</td><td>매일</td></tr>
      <tr><td><a href="data/regions.json">regions.json</a></td><td>지역별 메타(담당부서·전화)와 트림별 [지방비, 전환지방비] 행렬</td><td>매일</td></tr>
      <tr><td><a href="data/status.json">status.json</a></td><td>지역별 공고·접수·출고·잔여, 유형별 분해, 공단 접수상태, 지자체 공지 원문, 신청마감</td><td>매시간</td></tr>
      <tr><td><a href="data/rounds.json">rounds.json</a></td><td>지역별 공고 회차(본공고·추경)의 게시일·접수기간·신청마감과 최근 90일 공단 변경 이력</td><td>매시간</td></tr>
      <tr><td><a href="data/history.json">history.json</a></td><td>지역별 일별 승용 잔여 이력(<span data-derived>{{HIST_START}}</span>부터 <span data-derived>{{HIST_DAYS}}</span>일치)과 추가공고 감지 이벤트</td><td>매일</td></tr>
      <tr><td><a href="calendar/evbojo.ics">evbojo.ics</a></td><td>전국 접수 일정 캘린더(공단 등록 회차의 접수 시작·마감, 지난 30일~앞으로 90일) — 캘린더 앱에서 구독하면 일정이 자동 갱신됩니다</td><td>매시간</td></tr>
      <tr><td><a href="data/articles.json">articles.json</a></td><td>데이터 해설 시리즈 목록(<span data-derived>{{N_ARTICLES}}</span>편) · <a href="feed.xml">RSS</a></td><td>발행 시</td></tr>
    </tbody>
  </table></div>
  <p class="small muted mt8">CSV는 UTF-8(BOM)이라 엑셀에서 바로 열립니다. 모든 금액 단위는 만원, 대수는 대입니다.</p>
</section>

<section class="card">
  <h2 class="mt0">어떻게 모으나 — 수집 주기와 예절</h2>
  <ul style="padding-left:20px;margin:8px 0;color:var(--text2);font-size:14.5px;line-height:1.7">
    <li><b>접수 현황</b>(공고·접수·출고·잔여·공지·회차 일정)은 매시간, <b>전체 단가표</b>(지역×트림 지방비)는 매일 새벽 04시에 자동 수집합니다. 수집기는 운영자 Mac에서 예약 실행되며 사람이 매번 손대지 않습니다.</li>
    <li>공공 사이트에 부담을 주지 않도록 요청 간격을 1.2초 이상 두고, 연락처를 밝힌 식별자(User-Agent)로 접근하며, 실패 시 간격을 늘려 최대 3회만 재시도합니다.</li>
    <li>수집 결과는 정적 파일로 공개되므로 이용자가 페이지를 열 때 공단 서버로 요청이 가지 않습니다.</li>
  </ul>
</section>

<section class="card">
  <h2 class="mt0">무엇을 믿고, 무엇을 걸러내나 — 검증 규칙</h2>
  <ul style="padding-left:20px;margin:8px 0;color:var(--text2);font-size:14.5px;line-height:1.7">
    <li><b>교체하지 않는 경우</b>: 새로 받은 표의 행 수가 모자라거나 값이 이상하면(형식 불일치·범위 이탈) 기존 데이터를 그대로 두고 다음 시간에 다시 시도합니다. 깨진 데이터가 화면에 나가지 않게 하는 첫 번째 장치입니다.</li>
    <li><b>보류하는 경우</b>: 전체 단가표가 직전 대비 40% 이상 바뀌면 자동 반영하지 않고 보류 폴더에 두었다가 사람이 확인한 뒤에만 반영합니다. 공단 사이트 구조가 바뀌어 엉뚱한 값이 들어오는 상황을 막습니다.</li>
    <li><b>결손으로 보는 경우</b>: 한 지역의 공고·접수·출고가 갑자기 모두 0으로 떨어지면 '소진'이 아니라 '수집 결손'으로 보고 직전 값을 유지하며 로그에 남깁니다. 동시에 많은 지역이 그러면 그 회차 전체를 버립니다.</li>
    <li><b>원자적 교체</b>: 파일은 완성본을 만든 뒤 한 번에 바꿉니다. 수집 도중 페이지를 열어도 반쯤 쓰인 파일을 보는 일은 없습니다.</li>
    <li><b>자동 회귀 검사</b>: 매 회차 배포 전에 상태 배지와 공단 신호의 모순, 산문과 표의 1위 불일치, 금지 표현(점추정 예측·D-day·조건부 마감), 깨진 내부 링크, 광고 게이트 등 14종을 자동 점검하고 위반은 로그에 남깁니다.</li>
  </ul>
</section>

<section class="card">
  <h2 class="mt0">숫자의 뜻 — 잔여·마감·상태 판정</h2>
  <ul style="padding-left:20px;margin:8px 0;color:var(--text2);font-size:14.5px;line-height:1.7">
    <li><b>잔여</b>는 공단 통계의 '공고 − 출고'(0 미만은 0)입니다. 접수가 다 차도 출고 전까지는 줄지 않으므로 '잔여 0'이 곧 접수 마감이 아니고, 잔여가 남아도 접수가 끝났을 수 있습니다.</li>
    <li><b>유형별 잔여</b>는 유형마다 따로 계산된 값이라 합이 전체와 다를 수 있습니다. 화면에는 전체 잔여를 상한으로 표시합니다.</li>
    <li><b>마감 판정</b>은 보수적입니다. 지자체 공지에 완료형 마감 선언('접수 마감', '접수 종료')이 있거나 공단 등록 상태가 '마감'·'접수예정'이거나 등록된 모든 회차의 접수기간이 지난 경우에만 '마감' 계열 배지를 씁니다. '예산 소진 시 조기 마감' 같은 조건부·미래형 문구는 마감으로 보지 않습니다.</li>
    <li><b>예측하지 않습니다</b>. 소진되는 날짜를 점치는 표현(예상일·디데이)이나 '실시간' 같은 말을 쓰지 않고, 등록된 일정과 기록된 추이만 보여 줍니다.</li>
    <li><b>최대 보조금</b>은 승용 기준 국비+지방비 상한이며, 휠체어 접근 차량(WAV)과 미지원 트림은 최고액 서술에서 뺍니다.</li>
  </ul>
</section>

<section class="card">
  <h2 class="mt0">알려진 한계</h2>
  <ul style="padding-left:20px;margin:8px 0;color:var(--text2);font-size:14.5px;line-height:1.7">
    <li>공단 집계와 지자체 실제 접수 창구 사이에 시차가 있습니다. 일부 지자체 공지는 "누리집 잔여대수와 실제 잔여대수는 일치하지 않는다"고 직접 밝힙니다.</li>
    <li>광역시·특별자치시는 자치구 구분 없이 단일 단가표로 공개되므로 구 단위 차이는 담지 못합니다.</li>
    <li>차량 기본가격(실구매가 계산에 필요한 값)은 수집 대상이 아니라 제공하지 않습니다. 가격 구간은 제조사 신고 기본가격 기준이며 <a href="price-tiers.html">가격구간 해설</a>을 참고하세요.</li>
    <li>지자체 공고문의 세부 조건(거주 기간, 우선순위 기준, 서류)은 원문이 정본이며 이 사이트는 요약·연결만 합니다.</li>
  </ul>
</section>

<section class="card">
  <h2 class="mt0">인용·이용과 정정</h2>
  <p style="line-height:1.75;margin:10px 0">원 데이터의 권리는 공단과 각 지자체에 있고, 이 사이트가 정리한 표·이력·해설은 EV보조금이 만들었습니다. 출처를 "EV보조금(evbojo.co.kr), 기준 시각"으로 밝히면 비상업적 인용·연구 이용에 제한을 두지 않습니다. 상업적 이용이나 대량 재배포는 <a href="about.html#operator">운영자</a>에게 먼저 문의해 주세요.</p>
  <p style="line-height:1.75;margin:10px 0">틀린 수치나 어긋난 설명을 보셨다면 <a href="report.html">오류 제보</a>로 알려 주세요. 확인 후 고치고 <a href="changelog.html">변경·정정 이력</a>에 날짜와 내용을 남깁니다. 용어가 낯설다면 <a href="glossary.html">용어집</a>부터 보세요.</p>
</section>
