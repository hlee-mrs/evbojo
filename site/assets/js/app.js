/* EV보조금 공통 런타임 ─ 데이터 로드 · 헤더/푸터 · 포맷 · 상태뱃지 · 비교바구니 · 광고 */
(function () {
  'use strict';
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => [...(el || document).querySelectorAll(s)];

  /* ── 사이트 설정 ── */
  const SITE = {
    name: 'EV보조금',
    tagline: '전기차 구매보조금 한눈에',
    // ── 광고 설정 ─────────────────────────────────────────
    // 1) 카카오 애드핏 승인 후: provider:'adfit' + adfitUnits에 슬롯별 광고단위 ID 입력 + enabled:true
    // 2) AdSense 승인 후:      provider:'adsense' + client에 본인 ca-pub ID 입력 + enabled:true
    //    (각 페이지 슬롯의 data-ad-slot 번호는 AdSense 광고단위 생성 후 기입)
    ads: {
      enabled: true,
      provider: 'adsense',                    // 'adsense' | 'adfit'
      client: 'ca-pub-7688026325140831',      // AdSense 게시자 ID (metlit 계정)
      // AdSense 광고단위 ID. 슬롯 이름이 '-2'로 끝나면 하단, 그 외는 상단 단위를 씀
      // (16개 자리마다 단위를 만들면 관리가 불가능 → 상단/하단 2개로 성과만 구분)
      adUnits: {
        top: '5347890513',                    // EV보조금 - 본문 상단
        bottom: '7246727325',                 // EV보조금 - 본문 하단
      },
      adfitUnits: {                           // 애드핏: 슬롯이름 → 광고단위 ID (예: 'DAN-xxxxxxxx')
        // 'home-1': 'DAN-XXXXXXXX', 'region-1': 'DAN-XXXXXXXX', ...
      },
      adfitSize: { width: 320, height: 100 }, // 애드핏 반응형 미지원 → 모바일 배너 기준
    },
    // ── 후원(기부) 설정 ───────────────────────────────────
    // Payoneer '결제 요청(Request a Payment)' 링크를 넣으면 후원 버튼이 활성화됨.
    //   Payoneer 로그인 → 받기(Get Paid) → 결제 요청 링크 생성 → 그 URL을 아래에 붙여넣기
    donate: {
      payoneerUrl: 'https://link.payoneer.com/Token?t=BC4B67FF13CD4007A359F1F7E8BB9EA9&src=pl',  // 지급인이 금액 입력(USD)
    },
    staleDays: 14,
  };
  window.SITE = SITE;

  /* ── 데이터 로더 (병렬 fetch + 메모리 캐시) ── */
  const cache = {};
  function load(name) {
    if (!cache[name]) {
      cache[name] = fetch(`data/${name}.json`, { cache: 'no-cache' }).then(r => {
        if (!r.ok) throw new Error(name + ' load fail');
        return r.json();
      }).then(d => {
        // regions: 도 단위 복제 지역은 ref로 압축되어 있음 → 원본 v 연결
        if (name === 'regions') {
          Object.values(d).forEach(r => { if (r.ref && d[r.ref]) r.v = d[r.ref].v; });
        }
        return d;
      });
    }
    return cache[name];
  }
  window.EVData = {
    cars: () => load('cars'),
    regions: () => load('regions'),
    meta: () => load('meta'),
    status: () => load('status').catch(() => null),
    history: () => load('history').catch(() => null),   // 소진 예측용 잔여 이력(없으면 무소음 강등)
    all: () => Promise.all([load('cars'), load('regions'), load('meta'), load('status').catch(() => null)]),
  };

  /* ── 포맷터 ── */
  const fmt = n => (n == null ? '-' : n.toLocaleString('ko-KR'));
  const manwon = n => (n == null ? '-' : fmt(n) + '만원');
  // 만원 → 억/만원 표기 (5240 → 5,240만원 / 12400 → 1억 2,400만원)
  const manwonLong = n => {
    if (n == null) return '-';
    if (n < 10000) return fmt(n) + '만원';
    const eok = Math.floor(n / 10000), rest = n % 10000;
    return eok + '억' + (rest ? ' ' + fmt(rest) + '만원' : '원');
  };
  const won = n => fmt(Math.round(n)) + '원';
  window.fmt = fmt; window.manwon = manwon; window.manwonLong = manwonLong; window.won = won;

  /* ── URL 파라미터 ── */
  window.qs = key => new URLSearchParams(location.search).get(key);
  window.setQs = obj => {
    const p = new URLSearchParams(location.search);
    Object.entries(obj).forEach(([k, v]) => (v == null || v === '') ? p.delete(k) : p.set(k, v));
    history.replaceState(null, '', location.pathname + '?' + p.toString());
  };

  /* ── 지역 기억 (localStorage) ── */
  const LS = { region: 'ev.myRegion', cmp: 'ev.compare' };
  window.myRegion = {
    get: () => { try { return localStorage.getItem(LS.region); } catch (e) { return null; } },
    set: cd => { try { cd ? localStorage.setItem(LS.region, cd) : localStorage.removeItem(LS.region); } catch (e) {} },
  };

  /* ── 비교 바구니 (최대 3) ── */
  window.cmpBasket = {
    get() { try { return JSON.parse(localStorage.getItem(LS.cmp) || '[]'); } catch (e) { return []; } },
    toggle(id) {
      let arr = this.get();
      if (arr.includes(id)) arr = arr.filter(x => x !== id);
      else { if (arr.length >= 3) { alert('비교는 최대 3대까지 가능해요. 기존 차량을 빼주세요.'); return this.get(); } arr.push(id); }
      try { localStorage.setItem(LS.cmp, JSON.stringify(arr)); } catch (e) {}
      renderCmpBar(); return arr;
    },
    clear() { try { localStorage.removeItem(LS.cmp); } catch (e) {} renderCmpBar(); },
  };
  function renderCmpBar() {
    let bar = $('#cmp-bar');
    const arr = window.cmpBasket.get();
    if (!bar) { bar = document.createElement('div'); bar.id = 'cmp-bar'; document.body.appendChild(bar); }
    if (!arr.length || location.pathname.endsWith('compare.html')) { bar.classList.remove('show'); return; }
    bar.innerHTML = `🚗 ${arr.length}대 담김 <a href="compare.html">비교하기 →</a> <button class="x" aria-label="비우기">✕</button>`;
    bar.querySelector('.x').onclick = () => window.cmpBasket.clear();
    bar.classList.add('show');
  }
  window.renderCmpBar = renderCmpBar;

  /* ── HTML 이스케이프 ── */
  window.esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* ── 신청 유형 (잔여물량 배열 인덱스 = ev.or.kr 표 순서 [우선순위,법인·기관,택시,일반]) ──
     표시 순서는 일반 우선(대부분의 사용자). key/idx로 매핑. */
  window.CATS = [
    { key: 'general',  label: '일반',      idx: 3, tip: '일반 개인 구매자에게 배정된 물량이에요. 대부분의 신청자가 여기에 해당해요.' },
    { key: 'priority', label: '우선순위',  idx: 0, tip: '다자녀·차상위·기초수급, 생애최초 청년 등 우대 대상에게 우선 배정된 물량이에요. 해당 여부는 자격 진단에서 확인하세요.' },
    { key: 'corp',     label: '법인·기관', idx: 1, tip: '법인·공공기관·단체 명의 구매에 배정된 물량이에요. 개인 구매와는 별도예요.' },
    { key: 'taxi',     label: '택시',      idx: 2, tip: '전기택시(영업용) 전용 물량이에요. 개인 승용 신청과 무관해요.' },
  ];
  window.catByKey = k => CATS.find(c => c.key === k) || CATS[0];
  window.myCategory = {
    get() { try { return localStorage.getItem('ev.myCat') || 'general'; } catch (e) { return 'general'; } },
    set(k) { try { localStorage.setItem('ev.myCat', k); } catch (e) {} },
  };

  /* ── 접수 상태 판정 ──
     잔여율 = 출고잔여 / 공고. 데이터 기준시각이 오래되면 중립 강등(fail-safe).
     catKey 지정 시 해당 신청 유형(일반/우선순위/…)의 잔여로 판정. */
  window.statusBadge = function (st, statusUpdated, catKey) {
    if (!st) return { cls: 'badge-closed', label: '현황 확인 필요', stale: true };
    const ageDays = statusUpdated ? (Date.now() - new Date(statusUpdated).getTime()) / 864e5 : 99;
    if (ageDays > SITE.staleDays) return { cls: 'badge-closed', label: '직접 확인 필요(데이터 오래됨)', stale: true };
    const regionClosed = (st.left != null && st.left <= 0);   // 지역 전체 소진 여부
    let left = st.left, quota = st.n, pfx = '';
    if (catKey && st.d && st.d.left) {
      const c = catByKey(catKey);
      left = st.d.left[c.idx];
      quota = st.d.n ? st.d.n[c.idx] : null;
      pfx = c.label + ' ';
    }
    if (left == null) return { cls: 'badge-closed', label: pfx + '물량 정보 없음', stale: false };
    if (left <= 0) {
      // 애초에 배정 물량이 없던 유형(공고량 0)은 '소진'이 아니라 '해당 없음'으로 구분
      if (catKey && quota != null && quota <= 0) return { cls: 'badge-closed', label: pfx + '해당 물량 없음', stale: false };
      return { cls: 'badge-closed', label: pfx + '잔여 소진(추가공고 확인)', stale: false };
    }
    // 지역 전체가 소진됐는데 특정 유형에만 이월 잔여가 남은 경우: 초록 '접수 중'이 아니라 마감 맥락으로 표기.
    // (ev.or.kr 회차 이월로 항목 잔여 > 0 이지만 실제 접수는 마감된 상태 — 오인 방지)
    if (catKey && regionClosed) return { cls: 'badge-low', label: `${pfx}전체 마감 · 유형 잔여 ${fmt(left)}대(추가공고 확인)`, stale: false };
    const ratio = quota ? left / quota : 1;
    if (left < 30 || ratio < 0.06) return { cls: 'badge-low', label: `${pfx}마감 임박 · 잔여 ${fmt(left)}대`, stale: false };
    return { cls: 'badge-open', label: `${pfx}접수 중 · 잔여 ${fmt(left)}대`, stale: false };
  };

  /* ── 예측 소진 시기 (전체 잔여 기준) ──
     history.json(잔여 이력)에서 최근 4주/1주 두 창의 '잔여가 줄어드는 속도'(영업일 기준)를 구해
     0 도달 시기를 '이르면~늦으면' 범위로 추정. 점추정·D-day 금지, 회차 리셋·정체·신선도 명시 처리.
     이력 부족·로드 실패 시 '수집 중'으로 무소음 강등(페이지 절대 안 깨짐). */
  const FC = { RESET_MIN: 10, RESET_PCT: 0.05,                    // updater와 동일 리셋 임계
               MIN_OBS: 4, MIN_BDAYS: 3, MIN_SOLD: 5, MIN_DECR: 2, // 정식 예측 최소조건 4종
               GRADE_FAST: 5, GRADE_LONG: 40, RELAX_DAYS: 14,      // 등급 경계(영업일)·낙관 해금
               STALE_TAG: 48, STALE_ALERT: 24, STALE_HIDE: 120 };  // 신선도(시간)
  const CLOSED_RE = /접수\s*마감|조기\s*마감|접수\s*종료|접수\s*중단|신청\s*마감/;
  const DAY0 = Date.UTC(2026, 0, 1);                               // d0=2026-01-01(목)
  const isoToDay = iso => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || ''); return m ? Math.round((Date.UTC(+m[1], +m[2] - 1, +m[3]) - DAY0) / 864e5) : null; };
  const dayDate = d => new Date(DAY0 + d * 864e5);
  const isoOf = d => dayDate(d).toISOString().slice(0, 10);
  const md = d => `${dayDate(d).getUTCMonth() + 1}/${dayDate(d).getUTCDate()}`;
  const soon = d => { const t = dayDate(d), x = t.getUTCDate(); return `${t.getUTCMonth() + 1}월 ${x <= 10 ? '초순' : x <= 20 ? '중순' : '하순'}`; };  // 순(旬) 버킷
  const isBiz = (d, hol) => (d + 3) % 7 < 5 && !hol.has(isoOf(d)); // 주말·공휴일 제외
  const bizDays = (d1, d2, hol) => { let b = 0; for (let d = d1 + 1; d <= d2; d++) if (isBiz(d, hol)) b++; return b; };
  const addBiz = (d, k, hol) => { while (k > 0) { d++; if (isBiz(d, hol)) k--; } return d; };

  const TIP_MAIN = "이렇게 계산해요 — ① ev.or.kr의 '남은 대수(잔여)'를 이 사이트가 갱신될 때마다 기록해요. ② 최근 4주와 최근 1주 동안 잔여가 하루 평균 몇 대씩 줄었는지 구해요. 접수가 거의 없는 주말·공휴일은 빼고 셉니다. ③ 남은 대수 ÷ 하루 감소량 = 며칠 뒤 0이 되는지 — 두 속도로 각각 계산해 '이르면~늦으면' 범위로 보여드려요. 주의: 많은 지역에서 잔여는 신청 순간이 아니라 차가 출고될 때 줄어요. 그래서 실제 접수는 이 예상보다 먼저 마감될 수 있어요. 추가공고가 나면 잔여가 다시 늘고, 그때는 처음부터 다시 계산해요. '언제 마감된다'는 약속이 아니라 '지금 속도가 이어진다면'이라는 가정 계산이니 참고용으로만 봐 주세요.";
  const TIP_COLLECT = "잔여 대수가 줄어드는 속도를 사이트가 갱신될 때마다 기록하고 있어요. 며칠치 기록이 모이면 '이 속도라면 언제쯤 0이 될지'를 여기에 범위로 보여드려요. 그동안은 위의 잔여 대수와 지자체 공지의 접수기간을 확인해 주세요.";

  function renderForecast(el, st, ctx) {
    if (!el) return;
    if (!st) { el.innerHTML = ''; return; }
    const P = (html, tip, wide) => `<p class="small muted cat-note" style="margin-top:2px">${html}${tip ? `<button class="tip${wide ? ' tip--wide' : ''}" type="button" data-tip="${esc(tip)}" aria-label="계산 방식 설명">?</button>` : ''}</p>`;
    const lines = [];
    const done = () => { el.innerHTML = lines.join(''); };
    // ── 상시 고지 (예측 게이트와 독립) ──
    if (st.a != null && st.n != null && st.a > st.n && st.left > 0)
      lines.push(P(`접수는 이미 공고 물량을 넘었어요(+${fmt(st.a - st.n)}대). 지금 신청하면 취소·미배정분이 나와야 받을 수 있어요.`));
    if (/출고/.test(st.m || '') && st.left > 0)
      lines.push(P(`이 지역은 신청 순서가 아니라 <b>출고 순서</b>로 보조금이 배정돼요.`));
    // ── 게이트 결정 트리 (순서 고정, 첫 매치에서 종료) ──
    if (st.left == null || st.left <= 0) return done();                        // ① 마감: 예측 없음(뱃지가 담당)
    if (CLOSED_RE.test(st.note || '')) {                                       // ② 공지상 마감(잔여>0이어도)
      lines.push(P(`지자체 공지상 접수가 마감된 지역이에요. 남은 숫자는 아직 출고되지 않은 물량일 수 있어요 — 예측을 표시하지 않아요.`));
      return done();
    }
    const collecting = obs => P(`소진 시기 예측: <b>기록을 모으고 있어요</b>${obs ? ` (관측 ${obs}일째)` : ''}`, TIP_COLLECT, true);
    done();                                                                     // 이력 로드 전 상시 고지 먼저 표시
    EVData.history().then(hist => {
      const updatedISO = ctx && ctx.updated, asOf = isoToDay(updatedISO);
      const e = hist && hist.v === 1 && ctx && hist.r[ctx.cd];
      if (!e || !e.L || !e.L.rd || asOf == null) { lines.push(collecting(null)); return done(); }
      const hol = new Set(hist.holidays || []);
      // 시리즈 = 이력(현재 회차만) + 라이브 포인트 방어 결합
      let pts = hist.days.map((d, i) => [d, e.l[i]]).filter(p => p[1] != null);
      let clientReset = false;
      if (pts.length) {
        const prev = pts[pts.length - 1][1];
        const thr = Math.max(FC.RESET_MIN, Math.ceil(FC.RESET_PCT * (e.n || prev || 1)));
        if (st.left - prev >= thr) clientReset = true;                          // 미기록 리셋 → 방어 분기
        else if (st.left > prev) { if (asOf > pts[pts.length - 1][0]) pts.push([asOf, prev]); }   // 환입: 클램프
        else if (asOf > pts[pts.length - 1][0]) pts.push([asOf, st.left]);
        else pts[pts.length - 1][1] = Math.min(prev, st.left);
      }
      pts = pts.filter(p => p[0] >= e.L.rd.t);
      if (!pts.length) { lines.push(collecting(null)); return done(); }
      // ③ 추가공고 리셋 7일 내 — 실제 리셋 이벤트(ev 타입0)가 있을 때만.
      //    (관측 첫날의 rd.t는 '기록 시작'이지 공고가 아님 → rd.t만 보면 전 지역에 거짓 안내가 나감)
      const hadReset = (e.L.ev || []).some(v => v[1] === 0 && asOf - v[0] <= 7);
      if (clientReset || hadReset) {
        lines.push(P(`${md(e.L.rd.t)} <b>추가공고로 물량이 늘었어요.</b> 재공고 직후에는 며칠 안에 마감되는 경우가 많아요 — 신청 계획이 있다면 지자체 공지를 바로 확인하세요. (새 공고 기준으로 다시 기록하는 중)`));
        return done();
      }
      const rate = W => { const s = pts.find(p => p[0] >= asOf - W) || pts[0]; const nw = pts[pts.length - 1];
        const B = bizDays(s[0], asOf, hol), N = Math.max(0, s[1] - nw[1]);
        return { B, N, r: B > 0 ? N / B : 0, oldest: asOf - s[0] }; };
      const r28 = rate(28);
      const idle = e.L.lc != null ? bizDays(e.L.lc, asOf, hol) : r28.B;
      if (idle >= 5 && r28.N === 0) {                                           // ④ 정체 ≠ 여유
        lines.push(P(`최근 ${idle}영업일간 잔여가 줄지 않았어요. 접수가 일시 중지됐거나 집계가 멈췄을 수 있어요 — '여유 있다'는 뜻은 아니에요. 지자체 공지를 확인하세요.`));
        return done();
      }
      const ageH = (Date.now() - Date.parse(updatedISO)) / 3.6e6;
      const obs = pts.length, dec = pts.filter((p, i) => i && p[1] < pts[i - 1][1]).length;
      if (!(obs >= FC.MIN_OBS && r28.B >= FC.MIN_BDAYS && r28.N >= FC.MIN_SOLD && dec >= FC.MIN_DECR)) {   // ⑤ 표본 부족
        if (obs >= 2 && r28.B >= 2 && r28.N >= FC.MIN_SOLD && r28.r > 0 && st.left / r28.r <= FC.GRADE_FAST && ageH <= FC.STALE_ALERT)
          lines.push(P(`<b>빠르게 줄고 있어요.</b> 지금 속도라면 며칠 안에 잔여가 0이 될 수 있어요 (관측 ${obs}일째 기준이라 오차가 커요)`, TIP_MAIN, true));   // 조기경보(비대칭 예외)
        else lines.push(collecting(obs));
        return done();
      }
      if (st.left < 20) {                                                       // ⑥ 소량: 나눗셈 착시 차단
        lines.push(P(`잔여가 20대 미만이라 날짜 예측이 의미 없어요 — 곧 마감될 수 있으니 신청 전에 지자체·제조사에 바로 확인하세요.`));
        return done();
      }
      if (ageH > FC.STALE_HIDE) { lines.push(P(`자료가 오래되어 예측을 표시하지 않아요 (${md(asOf)} 기준)`)); return done(); }
      // ⑦ 이중창(4주/1주) 영업일 secant 예측
      const r7raw = rate(7);
      const r7 = (r7raw.oldest >= 3 && r7raw.B >= 2) ? r7raw.r : null;          // 몇 시간짜리 창의 과민 반응 방지
      const u = Math.min(0.8, 1.6 / Math.sqrt(Math.max(r28.N, 1)) + 0.2);       // 불확실성 계수
      const rHi = (r7 != null ? Math.max(r7, r28.r) : r28.r) * (1 + u);
      const rLo = (r7 != null ? Math.min(r7, r28.r) : r28.r) * (1 - u);
      const dE = st.left / rHi, dL = rLo > 0.01 ? st.left / rLo : Infinity;     // 영업일
      if (dE <= FC.GRADE_FAST && ageH > FC.STALE_ALERT) {                       // 임박 + 오래된 자료 → 경보 강등
        lines.push(P(`빠르게 줄던 지역이에요. 자료가 ${Math.max(1, Math.round(ageH / 24))}일 지나 지금은 마감됐을 수 있어요 — 지자체에 바로 확인하세요.`));
        return done();
      }
      let body;
      if (dE <= FC.GRADE_FAST) body = `<b>빠르게 줄고 있어요.</b> 지금 속도라면 며칠 안에 잔여가 0이 될 수 있어요`;   // 날짜 표기 금지(정밀 착시)
      else if (dE <= FC.GRADE_LONG) {
        const aTxt = soon(addBiz(asOf, Math.floor(dE), hol));
        const bTxt = (isFinite(dL) && dL <= 120) ? soon(addBiz(asOf, Math.ceil(dL), hol)) : null;
        body = bTxt ? (aTxt === bTxt
          ? `<b>꾸준히 줄고 있어요.</b> 지금 속도라면 잔여가 ${aTxt}쯤 0이 될 수 있어요`
          : `<b>꾸준히 줄고 있어요.</b> 지금 속도라면 잔여가 이르면 ${aTxt}, 늦으면 ${bTxt}쯤 0이 될 수 있어요`)
          : `<b>꾸준히 줄고 있어요.</b> 지금 속도라면 잔여가 이르면 ${aTxt}쯤 0이 될 수 있어요 (속도가 느려지면 더 걸릴 수 있어요)`;
      } else if (asOf - pts[0][0] >= FC.RELAX_DAYS && (r7 == null || r7 <= 1.3 * r28.r))
        body = `<b>천천히 줄고 있어요.</b> 이 속도라면 두 달 이상 남은 것으로 보여요. 다만 신청이 몰리면 갑자기 빨라질 수 있어요`;   // 낙관 해금 조건 충족 시만
      else body = `이 속도라면 두 달 이상으로 계산되지만 <b>기록이 짧아 확실하지 않아요</b>`;
      const spanLbl = r28.oldest >= 21 ? '최근 4주' : `최근 ${r28.oldest}일`;   // 창이 짧으면 짧다고 말함
      let tail = ` · ${spanLbl} 하루 평균 ${r28.r >= 1 ? Math.round(r28.r) + '대' : '약 ' + Math.round(1 / Math.max(r28.r, 1e-9)) + '일에 1대꼴'} 감소 (전체 기준)`;
      if (r7 != null && r7 > 2 * r28.r) tail += ' · 최근 1주는 평소보다 빨라요';
      if (ageH > FC.STALE_TAG) tail += ` · ${md(asOf)} 자료 기준`;
      lines.push(P(body + tail, TIP_MAIN, true));
      done();
    });
  }

  /* ── 신청 유형 선택 바 ──
     mount에 4개 유형 탭(잔여 미리보기 포함)을 렌더. 선택 시 유형을 저장하고 onChange(catKey) 호출.
     status.d(항목별 데이터)가 없으면 아무것도 렌더하지 않음(구버전 데이터 호환). */
  window.categoryBar = function (mount, st, onChange, ctx) {
    if (!mount) return;
    if (!st || !st.d || !st.d.left) { mount.innerHTML = ''; return; }
    const cur = myCategory.get();
    mount.innerHTML = `
      <div class="cat-head">내 신청 유형 선택<button class="tip" type="button" data-tip="지자체는 물량을 신청 유형별로 나눠 배정해요. 내 유형의 잔여가 중요합니다 — 개인 구매자는 보통 '일반'(우대 대상이면 '우선순위')을 보세요." aria-label="신청 유형 설명">?</button></div>
      <div class="cat-tabs">${CATS.map(c => {
        const n = st.d.left[c.idx];
        const state = n == null ? '' : (n > 0 ? 'has' : 'none');
        // cat-tab은 div(role=button) — 내부에 tip <button>이 있어 button 중첩(무효 HTML)을 피함
        return `<div class="cat-tab ${c.key === cur ? 'on' : ''} ${state}" data-cat="${c.key}" role="button" tabindex="0" aria-pressed="${c.key === cur}">
          <span class="cat-nm">${c.label}<button class="tip" type="button" data-tip="${esc(c.tip)}" aria-label="${c.label} 설명">?</button></span>
          <b>${n == null ? '-' : fmt(n) + '대'}</b></div>`;
      }).join('')}</div>
      <p class="small muted cat-note">숫자는 각 유형의 남은 물량이에요. 항목 합계는 '전체'와 다를 수 있어요<button class="tip" type="button" data-tip="본공고·추경 등 공고 회차가 나뉘면 이월분 때문에 항목 합계와 전체가 다를 수 있어요. ev.or.kr 원본 수치를 그대로 보여드립니다." aria-label="합계 차이 설명">?</button></p>
      ${st.n != null ? `<p class="small muted cat-alloc">올해 공고 물량: <b>전체 ${fmt(st.n)}대</b>${st.d && st.d.n ? ` (${CATS.map(c => `${c.label} ${fmt(st.d.n[c.idx])}`).join(' · ')})` : ''}<button class="tip" type="button" data-tip="지자체가 올해 공고한 보급 물량이에요(ev.or.kr 공고 기준). 추경·추가공고가 나면 늘어날 수 있고, 회차 구분 때문에 유형별 합계가 전체와 다를 수 있어요." aria-label="공고 물량 설명">?</button></p>` : ''}
      <div class="cat-forecast" data-forecast></div>`;
    renderForecast(mount.querySelector('[data-forecast]'), st, ctx);
    function selectTab(tab) {
      myCategory.set(tab.dataset.cat);
      mount.querySelectorAll('.cat-tab').forEach(b => { const on = b === tab; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on); });
      onChange && onChange(tab.dataset.cat);
    }
    mount.querySelectorAll('.cat-tab').forEach(tab => {
      tab.addEventListener('click', e => { if (e.target.closest('.tip')) return; selectTab(tab); });
      tab.addEventListener('keydown', e => {
        if (e.target.closest('.tip')) return;            // 툴팁에 포커스가 있으면 무시
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectTab(tab); }
      });
    });
  };

  /* ── 모델 그룹핑 (브랜드→차종→트림 선택용) ── */
  const MODEL_RULES = [
    [/아이오닉\s?5/, '아이오닉5'], [/아이오닉\s?6/, '아이오닉6'], [/아이오닉\s?9|아이오닉9/, '아이오닉9'],
    [/EV3/i, 'EV3'], [/EV4/i, 'EV4'], [/EV5/i, 'EV5'], [/EV6/i, 'EV6'], [/EV9/i, 'EV9'], [/PV5/i, 'PV5'],
    [/코나/, '코나 일렉트릭'], [/캐스퍼/, '캐스퍼 일렉트릭'], [/레이/, '레이 EV'], [/니로/i, '니로 EV'], [/스타리아/, '스타리아 일렉트릭'],
    [/GV60/i, 'GV60'], [/GV70/i, 'GV70'], [/G80/i, 'G80'],
    [/Model 3/i, '모델3'], [/Model Y/i, '모델Y'],
    [/EQA/i, 'EQA'], [/EQB/i, 'EQB'], [/EX30/i, 'EX30'], [/토레스/, '토레스 EVX'],
    [/ID\.4/i, 'ID.4'], [/ID\.5/i, 'ID.5'], [/Q4/i, 'Q4 e-tron'], [/Q6/i, 'Q6 e-tron'],
    [/Countryman/i, 'MINI 컨트리맨'], [/Aceman/i, 'MINI 에이스맨'], [/Cooper|JCW/i, 'MINI 쿠퍼'],
    [/iX1/i, 'iX1'], [/iX2/i, 'iX2'], [/iX3/i, 'iX3'], [/i4/i, 'i4'], [/i5/i, 'i5'],
    [/ATTO/i, 'BYD 아토3'], [/DOLPHIN/i, 'BYD 돌핀'], [/SEALION/i, 'BYD 씨라이언7'], [/SEAL/i, 'BYD 씰'],
  ];
  window.modelGroup = function (c) {
    for (const [re, g] of MODEL_RULES) { if (re.test(c.name)) return g; }
    return c.name.replace(/\(단종\)/, '').trim();
  };

  /* ── 차량 표시 헬퍼 ── */
  window.carDisp = c => (c.maker === '기아' || c.maker === '현대자동차' ? '' : '') + c.name;
  window.makerShort = m => ({ '현대자동차': '현대', '테슬라코리아': '테슬라', '메르세데스벤츠코리아': '벤츠', '볼보자동차코리아': '볼보', '케이지모빌리티': 'KGM', '폭스바겐그룹코리아': '폭스바겐그룹', '비와이디코리아': 'BYD' })[m] || m;
  // 추정 전비(km/kWh): 인증 상온 주행거리 ÷ 배터리용량 (충전손실 미포함 → 계산기에서 10% 반영)
  window.carEff = c => (c.range && c.batt) ? +(c.range / c.batt).toFixed(1) : null;
  window.coldRatio = c => (c.range && c.rangeCold) ? Math.round(c.rangeCold / c.range * 100) : null;

  /* ── 헤더/푸터 주입 ── */
  const NAV = [
    ['index.html', '홈'], ['calc.html', '유지비 계산기'], ['check.html', '자격 진단'],
    ['guide.html', '신청 절차'], ['law.html', '제도·법령'], ['refund.html', '환수 계산'], ['faq.html', 'FAQ'],
  ];
  function header() {
    const here = location.pathname.split('/').pop() || 'index.html';
    const el = $('#site-header'); if (!el) return;
    el.className = 'site-header';
    el.innerHTML = `<div class="inner">
      <a class="logo" href="index.html"><span class="bolt">⚡</span>${SITE.name}</a>
      <nav class="gnb" aria-label="주 메뉴">${NAV.map(([h, t]) => `<a href="${h}" class="${here === h ? 'on' : ''}">${t}</a>`).join('')}</nav>
    </div>`;
  }
  function footer() {
    const el = $('#site-footer'); if (!el) return;
    el.className = 'site-footer';
    el.innerHTML = `<div class="inner">
      <div class="links">
        <a href="about.html">사이트 소개</a><a href="privacy.html">개인정보처리방침</a>
        <a href="donate.html">💛 후원하기</a>
        <a href="https://ev.or.kr" target="_blank" rel="noopener">무공해차 통합누리집 ↗</a>
        <a href="report.html">오류 제보</a>
      </div>
      <div id="foot-stamp"></div>
      <div class="disclaimer">
        본 사이트는 <b>정부·공공기관과 무관한 개인 운영 정보 사이트</b>입니다. 게시된 보조금·제도 정보는 참고용이며 법적 효력이 없습니다.
        실제 지원 금액·자격·잔여 물량은 반드시 <b>무공해차 통합누리집(ev.or.kr)</b>과 관할 지자체 공고문으로 확인하세요.
        본 사이트는 광고(Google AdSense 등)를 게재하며, 광고 수익으로 운영됩니다.
      </div>
      <div class="mt8">© ${new Date().getFullYear()} ${SITE.name} · 데이터 출처: 무공해차 통합누리집(ev.or.kr)</div>
    </div>`;
    window.EVData.meta().then(m => {
      const s = $('#foot-stamp');
      if (s) s.innerHTML = `단가 기준일 <b>${m.updated}</b> · 출처 ${m.source} · 2026년 전기승용 기준`;
      freshness(m);
    }).catch(() => {});
  }
  function freshness(meta) {
    const days = Math.floor((Date.now() - new Date(meta.updated).getTime()) / 864e5);
    if (days > SITE.staleDays) {
      const b = document.createElement('div');
      b.className = 'stale-banner show container';
      b.textContent = `⚠️ 데이터 확인일(${meta.updated})로부터 ${days}일이 지났어요. 최신 공고는 ev.or.kr에서 확인하세요.`;
      const h = $('#site-header'); h && h.after(b);
    }
  }

  /* ── 광고 슬롯 ──
     data-slot 이름별 슬롯. SITE.ads.enabled=false 면 자리표시(고정 높이 유지 → CLS 없음).
     AdSense 승인 후: client 설정 + enabled:true + 각 슬롯 data-ad-slot 번호 입력. */
  function renderAds() {
    const slots = $$('.ad-slot');
    if (!slots.length) return;
    if (SITE.ads.enabled && SITE.ads.provider === 'adsense') {
      // adsbygoogle.js 는 각 페이지 <head> 에 이미 있음 → 여기서 다시 주입하지 않음(중복 로드 방지)
      slots.forEach(slot => {
        const box = slot.querySelector('.ad-box');
        if (!box) return;
        const adId = /-2$/.test(slot.dataset.slot || '') ? SITE.ads.adUnits.bottom : SITE.ads.adUnits.top;
        if (!adId) return;                                   // 단위 ID 없으면 아무것도 안 함
        box.innerHTML = `<ins class="adsbygoogle" style="display:block;width:100%" data-ad-client="${SITE.ads.client}" data-ad-slot="${adId}" data-ad-format="auto" data-full-width-responsive="true"></ins>`;
        box.style.border = 'none';
        try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) {}
        // 광고가 안 채워지면(미승인·재고없음) 빈 'AD' 박스가 남지 않게 자리째 숨김
        const ins = box.querySelector('ins');
        const hideIfUnfilled = () => { if (ins.getAttribute('data-ad-status') === 'unfilled') slot.style.display = 'none'; };
        new MutationObserver(hideIfUnfilled).observe(ins, { attributes: true, attributeFilter: ['data-ad-status'] });
        setTimeout(() => { if (!ins.getAttribute('data-ad-status')) slot.style.display = 'none'; }, 4000);
      });
    } else if (SITE.ads.enabled && SITE.ads.provider === 'adfit') {
      const s = document.createElement('script');
      s.async = true;
      s.src = 'https://t1.daumcdn.net/kas/static/ba.min.js';
      document.head.appendChild(s);
      slots.forEach(slot => {
        const unit = SITE.ads.adfitUnits[slot.dataset.slot];
        const box = slot.querySelector('.ad-box');
        if (!unit || !box) return;
        box.innerHTML = `<ins class="kakao_ad_area" style="display:none" data-ad-unit="${unit}" data-ad-width="${SITE.ads.adfitSize.width}" data-ad-height="${SITE.ads.adfitSize.height}"></ins>`;
        box.style.border = 'none';
        box.style.minHeight = SITE.ads.adfitSize.height + 'px';
      });
    } else {
      slots.forEach(slot => {
        const box = slot.querySelector('.ad-box');
        if (box && !box.textContent.trim()) box.textContent = '광고 영역 (광고 승인 후 표시됩니다)';
      });
    }
  }

  /* ── 지역 셀렉터 (시도 → 시군구) ──
     mount(el, {onPick, value}) */
  window.regionPicker = async function (el, opts) {
    opts = opts || {};
    const regions = await window.EVData.regions();
    const sidos = [...new Set(Object.values(regions).map(r => r.sido))];
    el.innerHTML = `<div class="grid2">
      <select class="select" data-r="sido" aria-label="시·도 선택"><option value="">시·도</option>${sidos.map(s => `<option>${s}</option>`).join('')}</select>
      <select class="select" data-r="gu" aria-label="시·군·구 선택" disabled><option value="">시·군·구</option></select>
    </div>`;
    const sidoSel = el.querySelector('[data-r=sido]'), guSel = el.querySelector('[data-r=gu]');
    function fillGu(sido, pick) {
      const list = Object.entries(regions).filter(([, r]) => r.sido === sido);
      const single = list.length === 1;   // 광역시·특별시·세종·제주 등: 하위 시·군·구 없음(시 전체 단일 단가)
      // 단일 지역은 placeholder 없이 그 지역만 표시하고 잠금 → "구를 골라야 하나?" 혼동 제거
      guSel.innerHTML = (single ? '' : `<option value="">시·군·구</option>`) +
        list.map(([cd, r]) => `<option value="${cd}">${r.name}</option>`).join('');
      if (single) {
        guSel.value = list[0][0];
        guSel.dispatchEvent(new Event('change'));   // onPick은 활성 상태에서 발생
        guSel.disabled = true;                       // 이후 잠금(자동 선택 고정)
      } else {
        guSel.disabled = false;
        if (pick) guSel.value = pick;
      }
    }
    // 시·도 변경: 단일 지역이면 fillGu가 gu change를 발생시켜 onPick(valid) 호출.
    // 다지역이면 gu가 미선택(빈값)으로 리셋되므로 onPick(null)로 '선택 해제'를 알려 화면을 갱신.
    sidoSel.onchange = () => {
      fillGu(sidoSel.value);
      if (!guSel.value) opts.onPick && opts.onPick(null);
    };
    guSel.onchange = () => {
      if (guSel.value) { window.myRegion.set(guSel.value); opts.onPick && opts.onPick(guSel.value, regions[guSel.value]); }
      else opts.onPick && opts.onPick(null);
    };
    const init = opts.value || window.myRegion.get();
    if (init && regions[init]) { sidoSel.value = regions[init].sido; fillGu(regions[init].sido, init); }
    return { get: () => guSel.value || null };
  };

  /* ── 부팅 ── */
  document.addEventListener('DOMContentLoaded', () => {
    header(); footer(); renderCmpBar(); renderAds();
  });

  /* ── (?)툴팁: 모바일 탭 토글, 바깥 탭으로 닫기 ── */
  document.addEventListener('click', e => {
    const tip = e.target.closest && e.target.closest('.tip');
    $$('.tip.on').forEach(t => { if (t !== tip) t.classList.remove('on'); });
    if (tip) { tip.classList.toggle('on'); e.preventDefault(); e.stopPropagation(); }
  });
})();
