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
        // cars: 표시명(사양코드 제거) 우선 — 원문 name은 수집 매칭용이라 UI에는 disp 사용
        if (name === 'cars') {
          d.forEach(c => { if (c.disp) c.name = c.disp; });
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
    if (!arr.length || location.pathname.endsWith('compare.html')) { bar.classList.remove('show'); document.body.style.paddingBottom = ''; return; }
    bar.innerHTML = `🚗 ${arr.length}대 담김 <a href="compare.html">비교하기 →</a> <button class="x" aria-label="비우기">✕</button>`;
    bar.querySelector('.x').onclick = () => window.cmpBasket.clear();
    bar.classList.add('show');
    document.body.style.paddingBottom = '68px';   // 하단 고정 비교바가 페이지 말미 콘텐츠·광고를 가리지 않게 여백 확보
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

  /* ── 공지문 마감 감지 ──
     지자체 공지(note)에서 "이번 회차 접수/선정 종료"를 감지. 161개 공지 전수 분류로 검증(오탐 0) —
     패턴·가드는 검증본이라 동작 변경 금지. ES2018 안전: 룩비하인드 금지(구형 iOS Safari 파스 에러).
     원칙: 완료형 선언("마감되었습니다")만 신뢰, 조건부/미래형("예산 소진 시 조기 마감", "마감 예정")은 무시.
     최악의 오류는 열린 지역을 마감으로 오판 — 애매하면 closed:false(놓치는 쪽)를 택한다. */
  function detectClosed(note) {
    const res = { closed: false, partial: false, closedDate: null, nextRound: null, evidence: null };
    if (!note) return res;
    const t = String(note).replace(/\s+/g, ' ');
    const COND_PRE = /(소진\s?시|소진시|될\s?수|경우|한\s?때|시\s?조기\s?$)/;               // 조건부 문맥(직전 20자)
    const ALLOC = /(우선\s?순위|우선순위|우선\s?배정|택시|택배|이륜|어린이|버스|승합|수소)/;   // 특수물량 한정 마감
    const OPEN_SIG = /(접수\s?중|접수중|신청\s?가능|접수\s?시작|접수시작|접수\s?재개|접수\s?가능|선정\s?가능|추진\s?중)/; // 열림 신호(부분마감 판단)
    const patterns = [                                                   // 완료형 마감 선언
      /(마감|종료|소진)\s?(되었|됐|하였|했)/g,
      /마감\s?[(（][^()（）]{0,26}[)）]\s?(되었|됐)/g,                     // "마감(2026. 8. 7. 13:00)되었"
      /(마감|종료)\s?(입니다|임을|합니다|함)/g,
      /(전량|모두|전체\s?물량|물량\s?모두|전\s?물량)\s?(마감|소진)/g,
      /(대상자\s?)?선정[이은는]?\s?(모두\s?)?(마감|완료|끝났)/g,
      /추진\s?완료/g,
      /접수\s?종료/g,
      /(더\s?이상|현재)\s?접수\s?불가/g,
      /(본예산|예산|국비)\s?(조기\s?)?소진(되어|으로)/g,                    // 완료 사실 서술만
    ];
    const hits = [];
    const consider = (idx, len) => {
      const pre = t.slice(Math.max(0, idx - 20), idx), post = t.slice(idx + len, idx + len + 8);
      if (COND_PRE.test(pre)) return;                                      // ① 조건부 문맥
      if (/^\s?안\s?되|^\s?되지\s?않/.test(post)) return;                   // ② 부정형("마감 안내"는 부정 아님)
      if (ALLOC.test(pre) && !/(승용|화물|전체|전량|모두|사업|민간)/.test(pre)) return; // ③ 특수물량만의 마감
      if (/상반기/.test(pre) && OPEN_SIG.test(t)) return;                   // ④ 과거 회차 마감 + 새 회차 열림
      const fr = t.slice(idx + len, idx + len + 60).match(/([2-9])\s?차[^.]{0,10}(신청|접수)\s?기간/);
      if (fr) {                                                            // ⑤ "1차 마감" 직후 더 높은 회차 신청기간 = 과거 회차
        const pr = pre.match(/([1-9])\s?차(?![가-힣])/);
        if (pr && parseInt(fr[1], 10) > parseInt(pr[1], 10)) return;
      }
      hits.push({ idx, len, hasPass: /승용/.test(pre), hasTruck: /화물/.test(pre), isGlobal: !/승용|화물/.test(pre) });
    };
    let m;
    for (const re of patterns) {
      re.lastIndex = 0;
      while ((m = re.exec(t)) !== null) { consider(m.index, m[0].length); if (m.index === re.lastIndex) re.lastIndex++; }
    }
    const BARE = /마감/g;    // 맨몸 "마감"(어미 없음) — 강한 가드 하에서만 (예: "보급기간 : 마감", "★ 전기승용 마감")
    while ((m = BARE.exec(t)) !== null) {
      const idx = m.index, next = t.slice(idx + 2, idx + 8);
      if (/^(되|될|돼|됐|하|함|입|임|안)/.test(next)) continue;              // 어미형은 위 패턴 소관
      if (/^\s?(예정|임박|시|또는|여부|대수|일|기한|이후|전|후)/.test(next)) continue; // 미래·조건·명사수식
      if (!/(접수|공고|물량|사업|승용|화물|기간|신청|모집)/.test(t.slice(Math.max(0, idx - 12), idx))) continue; // 주어 단서 필수
      consider(idx, 2);
    }
    if (!hits.length) return res;
    hits.sort((a, b) => a.idx - b.idx);                                    // 공지 관행상 최신 내용이 맨 앞(★ 첫 줄) → 첫 매치가 대표
    res.closed = true;
    let anyGlobal = false, pass = false, truck = false;
    for (const h of hits) { if (h.isGlobal) anyGlobal = true; if (h.hasPass) pass = true; if (h.hasTruck) truck = true; }
    res.partial = (!anyGlobal && pass !== truck) || OPEN_SIG.test(t);       // 승용만/화물만 마감 or 열림 신호 공존
    // 날짜 창은 승용 문장 우선 → 전역 문장 → 첫 매치 순 — "화물 8.7 마감 ★ 승용 8.12 마감"에서 8/7 오집기 방지
    const h0 = hits.find(h => h.hasPass) || hits.find(h => h.isGlobal) || hits[0];
    res.evidence = t.slice(Math.max(0, h0.idx - 30), Math.min(t.length, h0.idx + h0.len + 20)).trim();
    if (res.evidence.length > 80) res.evidence = res.evidence.slice(res.evidence.length - 80);
    // 마감 시점(베스트에포트) — 창 시작은 해당 문장 경계로 제한: 앞 문장(화물 등)의 날짜 오집기 방지
    const sb = Math.max(...['.', '!', '?', '★', '☆', '※'].map(ch => t.lastIndexOf(ch, h0.idx - 1))) + 1;
    const win = t.slice(Math.max(sb, h0.idx - 40), Math.min(t.length, h0.idx + h0.len + 40));
    let dm = win.match(/(?:(20\d{2})|['’`]?(\d{2}))\s?[.년]\s?(\d{1,2})\s?[.월/]\s?(\d{1,2})[일.]?(?:\s?\([월화수목금토일]\))?(?:\s?기준)?(?:\s?(\d{1,2}:\d{2}))?/);
    if (!dm) dm = win.match(/()(?:^|[^\d.])(\d{1,2})()\s?[.\/]\s?(\d{1,2})\.?(?:\s?\([월화수목금토일]\))?(?:\s?(\d{1,2}:\d{2}))?/); // "7.16" "6/30"
    if (dm) {
      let y = dm[1] ? dm[1] : (dm[2] ? '20' + dm[2] : '2026'), mo = dm[3] || dm[2], dd = dm[4];
      if (!dm[3] && dm[2] && dm[4]) { mo = dm[2]; dd = dm[4]; y = '2026'; } // 연도 없는 형태: 그룹 재배치
      mo = ('0' + parseInt(mo, 10)).slice(-2); dd = ('0' + parseInt(dd, 10)).slice(-2);
      if (+mo >= 1 && +mo <= 12 && +dd >= 1 && +dd <= 31) res.closedDate = y + '-' + mo + '-' + dd + (dm[5] ? ' ' + dm[5] : '');
    }
    const nr = t.match(/(추경|추가\s?공고|다음\s?공고|[3-9]\s?차\s?(?:공고|접수|사업|보급)|하반기\s?공고|추가\s?모집)[^.★☆※]{0,36}(예정|예상|계획|가능)/); // 다음 회차 예고
    if (nr) { res.nextRound = nr[0].trim(); if (res.nextRound.length > 60) res.nextRound = res.nextRound.slice(0, 60); }
    return res;
  }
  /* closedInfo(st): note 문자열 기준 캐시. 마감 감지 시 결과 객체, 아니면 null(기존 잔여 기준 동작 유지) — 계약 API */
  const ciCache = new Map();
  window.closedInfo = function (st) {
    const note = st && st.note;
    if (!note) return null;
    if (!ciCache.has(note)) { const r = detectClosed(note); ciCache.set(note, r.closed ? r : null); }
    return ciCache.get(note);
  };
  // closedDate 'YYYY-MM-DD[ HH:MM]' → 'M/D[ HH:MM]'
  const fmtMD = (iso, withTime) => { const m2 = /^(\d{4})-(\d{2})-(\d{2})(?:\s(\d{1,2}:\d{2}))?/.exec(iso || ''); return m2 ? `${+m2[2]}/${+m2[3]}${withTime && m2[4] ? ' ' + m2[4] : ''}` : ''; };

  /* ── 접수 상태 판정 ──
     잔여율 = 출고잔여 / 공고. 데이터 기준시각이 오래되면 중립 강등(fail-safe).
     catKey 지정 시 해당 신청 유형(일반/우선순위/…)의 잔여로 판정.
     우선순위: ① stale ② 잔여≤0 ③ 공지상 마감(closedInfo — 잔여>0이어도 초록 금지)
               ④ 공단 등록 접수상태(st.st) ⑤ 임박/접수중.

     ── 공단(ev.or.kr) 등록 접수상태 = 지자체 공지와 독립된 두 번째 신호 ──
     status.json의 st.st('접수중'|'마감'|'접수예정')·st.dl(최종 신청마감)은 161/161 지역에 존재한다.
     '마감'·'접수예정'이면 잔여가 남아 있어도 badge-open(초록)·badge-low(임박)를 주지 않는다 —
     남은 숫자는 미출고분이거나 아직 창구가 열리지 않은 물량일 수 있기 때문(보수적 판정, I3).
     반대 방향(공단 '접수중' + 공지 원문 완료형 마감)은 closedInfo 판정을 그대로 유지한다.
     라벨에는 공단 상태를 병기해 사용자가 두 신호를 모두 보고 대조할 수 있게 한다.
     prerender.py badge_of()가 이 로직의 쌍둥이 — 규칙(초록 금지·마감 계열·병기)을 양쪽 동일하게 유지. */
  window.statusBadge = function (st, statusUpdated, catKey) {
    if (!st) return { cls: 'badge-closed', label: '현황 확인 필요', stale: true };
    const ageDays = statusUpdated ? (Date.now() - new Date(statusUpdated).getTime()) / 864e5 : 99;
    if (ageDays > SITE.staleDays) return { cls: 'badge-closed', label: '직접 확인 필요(데이터 오래됨)', stale: true };
    const regionClosed = (st.left != null && st.left <= 0);   // 지역 전체 소진 여부
    const ks = st.st || '';                                   // 공단 등록 접수상태
    const ksShut = (ks === '마감'), ksSoon = (ks === '접수예정');
    const ksTag = ksShut ? `공단 접수 마감${st.dl ? ` (${fmtMD(st.dl)})` : ''}` : (ksSoon ? '공단 접수 예정' : '');
    let left = st.left, quota = st.n, pfx = '';
    if (catKey && st.d && st.d.left) {
      const c = catByKey(catKey);
      left = st.d.left[c.idx];
      quota = st.d.n ? st.d.n[c.idx] : null;
      pfx = c.label + ' ';
      // 유형 잔여 > 전체 잔여 (161곳 중 148곳). 원본 산식이 유형별로 max(0, 공고−출고)라
      // 과접수된 유형의 초과 출고분이 다른 유형과 상계되지 않아 생기는 집계 특성이다
      // (전체 잔여는 상계 후 값 = 실제 상한). 유형 숫자를 '남은 물량'으로 내보내면
      // 전체보다 큰 값이 노출돼 오해를 부르므로, 전체 기준 판정으로 강등하고 숫자는 표기하지 않는다(I3).
      if (left != null && st.left != null && left > st.left) {
        const b = window.statusBadge(st, statusUpdated);
        return { cls: b.cls, label: `${b.label} · ${c.label} 잔여는 공고 기준 계산값이라 전체와 달라요`, stale: b.stale };
      }
    }
    if (left == null) return { cls: 'badge-closed', label: pfx + '물량 정보 없음', stale: false };
    if (left <= 0) {
      // 애초에 배정 물량이 없던 유형(공고량 0)은 '소진'이 아니라 '해당 없음'으로 구분
      if (catKey && quota != null && quota <= 0) return { cls: 'badge-closed', label: pfx + '해당 물량 없음', stale: false };
      return { cls: 'badge-closed', label: pfx + '잔여 소진(추가공고 확인)', stale: false };
    }
    // 지역 전체가 소진됐는데 특정 유형에만 이월 잔여가 남은 경우: 초록 '접수 중'이 아니라 마감 맥락으로 표기.
    // (ev.or.kr 회차 이월로 항목 잔여 > 0 이지만 실제 접수는 마감된 상태 — 오인 방지)
    if (catKey && regionClosed)
      return { cls: ksShut ? 'badge-shut' : ksSoon ? 'badge-closed' : 'badge-low',
               label: `${pfx}전체 마감 · 유형 잔여 ${fmt(left)}대(추가공고 확인)${ksTag ? ' · ' + ksTag : ''}`, stale: false };
    // 공지상 접수 마감인데 잔여>0 (예: 서울 8/7 마감·잔여 2,703대) — 잔여는 미출고분일 수 있음, 초록 금지
    const ci = window.closedInfo(st);
    if (ci) {
      const tag = ksTag ? ' · ' + ksTag : '';   // 공단 상태 병기(두 신호 대조용)
      if (catKey) return ci.partial     // 유형 탭: 유형 잔여 숫자는 유지하되 마감 맥락 표기(regionClosed 분기와 동일 철학)
        ? { cls: (ksShut || ksSoon) ? 'badge-shut' : 'badge-low', label: `${pfx}공지상 마감 안내 · 잔여 ${fmt(left)}대(유형별 확인)${tag}`, stale: false }
        : { cls: 'badge-shut', label: `${pfx}공지상 접수 마감 · 잔여 ${fmt(left)}대는 미출고분일 수 있음${tag}`, stale: false };
      return ci.partial                 // partial=일부 차종·유형만 마감일 수 있음 → 단정 금지 톤
        ? { cls: 'badge-shut', label: `공지상 마감 안내 · 유형별 확인 필요${tag}`, stale: false }
        : { cls: 'badge-shut', label: `공지상 접수 마감${ci.closedDate ? ` (${fmtMD(ci.closedDate)})` : ''} · 잔여 ${fmt(left)}대는 미출고분일 수 있음${tag}`, stale: false };
    }
    // 공지 원문엔 완료형 마감 선언이 없지만 공단 등록 상태가 마감/접수예정 — 초록·임박 금지(위 주석의 보수 규칙)
    if (ksShut) return { cls: 'badge-shut', label: `${pfx}${ksTag} · 잔여 ${fmt(left)}대는 미출고분일 수 있음 · 공고 일정 확인 필요`, stale: false };
    if (ksSoon) return { cls: 'badge-closed', label: `${pfx}공단 접수 예정 · 잔여 ${fmt(left)}대 · 공고 일정 확인 필요`, stale: false };
    const ratio = quota ? left / quota : 1;
    if (left < 30 || ratio < 0.06) return { cls: 'badge-low', label: `${pfx}마감 임박 · 잔여 ${fmt(left)}대`, stale: false };
    return { cls: 'badge-open', label: `${pfx}접수 중 · 잔여 ${fmt(left)}대`, stale: false };
  };

  /* ── 지자체 공지 콜아웃 (region/index 공용) ──
     원문 + 긴 글만 더보기/접기. 공지상 마감(closedInfo)이면 danger 승격 + 마감/다음공고 라인.
     note는 신뢰 불가 입력 → 전부 esc() 경유. id 대신 data-속성(한 페이지 다중 렌더에도 안전). */
  window.noteCallout = function (mount, st) {
    if (!mount) return;
    if (!st || !st.note) { mount.innerHTML = ''; return; }
    const LIMIT = 180, full = String(st.note), long = full.length > LIMIT, clip = full.slice(0, LIMIT) + '…';
    const ci = window.closedInfo(st);
    const head = ci
      ? `<div style="margin-bottom:6px"><b>🚫 공지상 접수 마감${ci.closedDate ? ` (${esc(fmtMD(ci.closedDate, true))})` : ''}</b>${ci.partial ? ' · 일부 차종·유형은 접수 가능할 수 있어요' : ''}</div>` +
        (ci.nextRound ? `<div style="margin-bottom:6px"><b>🔜 다음 공고 예고:</b> ${esc(ci.nextRound)}</div>` : '')
      : '';
    mount.innerHTML =
      `<div class="callout ${ci ? 'callout-danger' : 'callout-warn'} small" style="margin:10px 0 0">${head}📢 <b>지자체 공지</b> · <span data-note-body>${esc(long ? clip : full)}</span>` +
      (long ? `<button type="button" data-note-toggle style="background:none;border:0;color:var(--primary);font:inherit;font-weight:700;cursor:pointer;padding:0 0 0 6px;text-decoration:underline">더보기</button>` : '') +
      `</div>`;
    if (long) {
      const body = mount.querySelector('[data-note-body]'), btn = mount.querySelector('[data-note-toggle]');
      let open = false;
      btn.addEventListener('click', () => {
        open = !open;
        body.textContent = open ? full : clip;      // textContent = 자동 이스케이프
        btn.textContent = open ? '접기' : '더보기';
      });
    }
  };

  /* ── 예측 소진 시기 (전체 잔여 기준) ──
     history.json(잔여 이력)에서 최근 4주/1주 두 창의 '잔여가 줄어드는 속도'(영업일 기준)를 구해
     0 도달 시기를 '이르면~늦으면' 범위로 추정. 점추정·D-day 금지, 회차 리셋·정체·신선도 명시 처리.
     이력 부족·로드 실패 시 '수집 중'으로 무소음 강등(페이지 절대 안 깨짐). */
  const FC = { RESET_MIN: 10, RESET_PCT: 0.05,                    // updater와 동일 리셋 임계
               MIN_OBS: 4, MIN_BDAYS: 3, MIN_SOLD: 5, MIN_DECR: 2, // 정식 예측 최소조건 4종
               GRADE_FAST: 5, GRADE_LONG: 40, RELAX_DAYS: 14,      // 등급 경계(영업일)·낙관 해금
               STALE_TAG: 48, STALE_ALERT: 24, STALE_HIDE: 120 };  // 신선도(시간)
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
    if (window.closedInfo(st)) {                                               // ② 공지상 마감(잔여>0이어도 — 전수검증 감지)
      lines.push(P(`지자체 공지상 접수가 마감된 지역이에요. 남은 숫자는 아직 출고되지 않은 물량일 수 있어요 — 예측을 표시하지 않아요.`));
      return done();
    }
    // ②′ 공단(ev.or.kr) 등록 접수상태 — 공지 원문에 완료형 마감 선언이 없어도 등록상 '마감'·'접수예정'이면
    //     소진 예측을 그리지 않는다(마감 상태의 잔여로 소진일을 그리면 '아직 살 수 있다'는 오독을 만든다).
    //     statusBadge의 공단 상태 규칙과 동일한 판정 — 한쪽만 고치면 뱃지와 문장이 어긋난다.
    if (st.st === '마감') {
      const dlTxt = st.dl ? fmtMD(st.dl, true) : '';
      lines.push(P(`공단(ev.or.kr) 등록 접수상태가 <b>마감</b>이에요${dlTxt ? ` (최종 신청마감 ${dlTxt})` : ''}. 남은 숫자는 아직 출고되지 않은 물량일 수 있어요 — 소진 예측을 표시하지 않아요. 다음 공고 일정은 지자체 공지를 확인하세요.`));
      return done();
    }
    if (st.st === '접수예정') {
      lines.push(P(`공단(ev.or.kr) 등록 접수상태가 <b>접수예정</b>이에요. 아직 이번 회차 접수가 시작되지 않아 소진 예측을 표시하지 않아요 — 접수 일정은 지자체 공지를 확인하세요.`));
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
          // 상한(늦은 쪽)이 계산 범위를 벗어난 단측 분기 — 하한만 있는데 날짜를 하나만 쓰면
          // 점추정으로 읽힌다(I3). 방향이 드러나는 '빨라도 ~ 이후' 구간 표현만 쓰고 상한은 명시적으로 비운다.
          : `<b>꾸준히 줄고 있어요.</b> 지금 속도라면 잔여가 0이 되는 시점은 <b>빨라도 ${aTxt} 이후</b>예요 — 늦어지는 쪽은 범위가 잡히지 않아 시점을 특정하지 않아요`;
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
    // 유형 잔여의 상한 = 전체 잔여. 원본은 유형별로 max(0, 공고−출고)를 쓰기 때문에
    // 과접수된 유형의 초과 출고분이 상계되지 않아 유형 숫자가 전체보다 커지는 지역이 많다(161곳 중 148곳).
    // 원본 데이터는 그대로 두고, '남은 물량'으로 읽히는 표시값만 전체 잔여로 눌러 과대표시를 막는다(I3 보수 원칙).
    const tot = st.left;
    const cells = CATS.map(c => {
      const raw = st.d.left[c.idx];
      const over = raw != null && tot != null && raw > tot;
      return { c, over, n: over ? tot : raw };
    });
    const capped = cells.some(x => x.over);
    mount.innerHTML = `
      <div class="cat-head">내 신청 유형 선택<button class="tip" type="button" data-tip="지자체는 물량을 신청 유형별로 나눠 배정해요. 내 유형의 잔여가 중요합니다 — 개인 구매자는 보통 '일반'(우대 대상이면 '우선순위')을 보세요." aria-label="신청 유형 설명">?</button></div>
      <div class="cat-tabs">${cells.map(({ c, over, n }) => {
        const state = n == null ? '' : (n > 0 ? 'has' : 'none');
        // cat-tab은 div(role=button) — 내부에 tip <button>이 있어 button 중첩(무효 HTML)을 피함
        return `<div class="cat-tab ${c.key === cur ? 'on' : ''} ${state}" data-cat="${c.key}" role="button" tabindex="0" aria-pressed="${c.key === cur}">
          <span class="cat-nm">${c.label}<button class="tip" type="button" data-tip="${esc(c.tip)}" aria-label="${c.label} 설명">?</button></span>
          <b>${n == null ? '-' : fmt(n) + '대' + (over && n > 0 ? ' 이하' : '')}</b></div>`;
      }).join('')}</div>
      <p class="small muted cat-note">${capped
        ? `이 지역은 유형별 잔여가 전체 잔여(${fmt(tot)}대)보다 크게 집계돼 있어요 — 유형별 잔여는 공고 기준 계산값이라 전체 잔여를 상한으로 표시했어요. 실제 신청 가능 물량은 지자체 공고로 확인하세요`
        : `숫자는 각 유형의 남은 물량이에요. 항목 합계는 '전체'와 다를 수 있어요`}<button class="tip" type="button" data-tip="유형별 잔여는 원본에서 유형마다 '공고−출고'로 따로 계산해요. 어떤 유형이 배정보다 많이 출고되면 그 초과분이 다른 유형과 상계되지 않아, 유형 숫자의 합이 전체 잔여보다 커질 수 있어요. 본공고·추경으로 회차가 나뉜 지역에서도 같은 차이가 납니다. 원본 수치는 그대로 두되, 화면에는 전체 잔여를 넘지 않도록 표시합니다." aria-label="합계 차이 설명">?</button></p>
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

  /* ── 헤더/푸터 주입 ──
     상위 메뉴 5개로 통폐합: 성격이 비슷한 항목은 드롭다운(details — JS 없이도 동작) 하위로.
     프리렌더 정적 내비(page.tpl)와 구조 동일해야 함 — 한쪽 수정 시 양쪽 동기화. */
  const NAV = [
    ['index.html', '홈'],
    ['status.html', '전국 현황판'],
    ['도구', [['calc.html', '유지비 계산기'], ['check.html', '자격 진단'], ['refund.html', '환수 계산'], ['compare.html', '차종 비교']]],
    ['가이드', [['guide.html', '신청 절차'], ['law.html', '제도·법령'], ['faq.html', 'FAQ']]],
    ['읽을거리', [['articles.html', '읽을거리 전체'], ['brief/', '일일 브리핑'], ['model/', '모델별 시리즈']]],
  ];
  function header() {
    const path = location.pathname;
    const here = path.split('/').pop() || 'index.html';
    const inDir = h => h.endsWith('/') && path.indexOf('/' + h) >= 0;   // brief/·model/ 하위 페이지 매칭
    const el = $('#site-header'); if (!el) return;
    el.className = 'site-header';
    const item = ([h, t]) => {
      if (typeof t !== 'string') return '';
      // 지역·시도 상세는 '전국 현황판' 계열로 하이라이트
      const on = here === h || (h === 'status.html' && /\/(region|sido)\//.test(path));
      return `<a href="${h}" class="${on ? 'on' : ''}">${t}</a>`;
    };
    const group = (t, items) => {
      const on = items.some(([h]) => here === h || inDir(h));
      return `<details class="nav-dd"><summary class="${on ? 'on' : ''}">${t}</summary><div class="dd">${items.map(([h, l]) => `<a href="${h}" class="${here === h || inDir(h) ? 'on' : ''}">${l}</a>`).join('')}</div></details>`;
    };
    el.innerHTML = `<div class="inner">
      <a class="logo" href="index.html"><span class="bolt">⚡</span>${SITE.name}</a>
      <nav class="gnb" aria-label="주 메뉴">${NAV.map(n => Array.isArray(n[1]) ? group(n[0], n[1]) : item(n)).join('')}</nav>
    </div>`;
    // 드롭다운 UX: 하나 열면 나머지 닫기, 바깥 탭으로 닫기
    el.querySelectorAll('.nav-dd').forEach(d => d.addEventListener('toggle', () => {
      if (d.open) el.querySelectorAll('.nav-dd[open]').forEach(o => { if (o !== d) o.open = false; });
    }));
    document.addEventListener('click', e => {
      if (!e.target.closest('.nav-dd')) el.querySelectorAll('.nav-dd[open]').forEach(o => { o.open = false; });
    });
  }
  function footer() {
    const el = $('#site-footer'); if (!el) return;
    el.className = 'site-footer';
    el.innerHTML = `<div class="inner">
      <div class="links">
        <a href="about.html">사이트 소개</a><a href="articles.html">읽을거리</a><a href="privacy.html">개인정보처리방침</a>
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
      if (s) s.innerHTML = `단가 수집일 <b>${m.updated}</b> · 출처 ${m.source} · 2026년 전기승용 기준`;
      // 본문 중 단가 기준일을 적어 둔 곳(예: law.html)을 meta.json 값으로 동기화 —
      // 손으로 쓴 날짜가 굳어 페이지마다 기준일이 갈리는 것을 막는다. 정적 텍스트는 마지막 수집값 폴백.
      $$('[data-meta-updated]').forEach(n => { n.textContent = m.updated; });
      freshness(m);
    }).catch(() => {});
  }
  function freshness(meta) {
    // 신선도 기준 = 매시간 갱신되는 접수현황(status). 단가 기준일(meta.updated)은
    // 가격이 안 바뀌면 오래되는 게 정상이라 경고 기준으로 쓰면 오탐이 난다.
    window.EVData.status().then(st => {
      const ref = (st && st.updated) || meta.statusUpdated || meta.updated;
      const days = Math.floor((Date.now() - new Date(ref).getTime()) / 864e5);
      if (days > SITE.staleDays) {
        const b = document.createElement('div');
        b.className = 'stale-banner show container';
        b.textContent = `⚠️ 접수현황 갱신일(${String(ref).slice(0, 10)})로부터 ${days}일이 지났어요. 최신 공고는 ev.or.kr에서 확인하세요.`;
        const h = $('#site-header'); h && h.after(b);
      }
    });
  }

  /* ── 광고 슬롯 ──
     data-slot 이름별 슬롯. SITE.ads.enabled=false 면 자리표시(고정 높이 유지 → CLS 없음).
     AdSense 승인 후: client 설정 + enabled:true + 각 슬롯 data-ad-slot 번호 입력. */
  function renderAds(isRetry) {
    const slots = $$('.ad-slot');
    if (!slots.length) return;
    // 본문 게이트: main 텍스트가 1,200자 미만이면 광고 슬롯 자체를 렌더하지 않음(저가치·빈 페이지 광고 차단).
    // JS가 본문을 채우는 페이지(비교표·레거시 region/car 등)를 위해 2.5초 뒤 1회만 재평가 —
    // 재평가 시점에도 미달이면 그대로 미렌더. 게이트에 걸린 동안은 ins 주입이 없어 재호출해도 중복 push 없음.
    const mainEl = $('main');
    const bodyLen = mainEl ? mainEl.textContent.replace(/\s+/g, ' ').trim().length : 0;
    if (bodyLen < 1200) {
      slots.forEach(slot => { slot.style.display = 'none'; slot.dataset.gated = '1'; });
      if (!isRetry) setTimeout(() => renderAds(true), 2500);
      return;
    }
    slots.forEach(slot => { if (slot.dataset.gated) { delete slot.dataset.gated; slot.style.display = ''; } });
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
        // 광고가 안 채워지면(미승인·재고없음) 빈 '광고' 박스가 남지 않게 자리째 숨김
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
