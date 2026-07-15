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
      enabled: false,
      provider: 'adsense',                    // 'adsense' | 'adfit'
      client: 'ca-pub-XXXXXXXXXXXXXXXX',      // AdSense 게시자 ID
      adfitUnits: {                           // 애드핏: 슬롯이름 → 광고단위 ID (예: 'DAN-xxxxxxxx')
        // 'home-1': 'DAN-XXXXXXXX', 'region-1': 'DAN-XXXXXXXX', ...
      },
      adfitSize: { width: 320, height: 100 }, // 애드핏 반응형 미지원 → 모바일 배너 기준
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

  /* ── 접수 상태 판정 ──
     잔여율 = 출고잔여 / 공고. 데이터 기준시각이 오래되면 중립 강등(fail-safe) */
  window.statusBadge = function (st, statusUpdated) {
    if (!st) return { cls: 'badge-closed', label: '현황 확인 필요', stale: true };
    const ageDays = statusUpdated ? (Date.now() - new Date(statusUpdated).getTime()) / 864e5 : 99;
    if (ageDays > SITE.staleDays) return { cls: 'badge-closed', label: '직접 확인 필요(데이터 오래됨)', stale: true };
    if (st.left <= 0) return { cls: 'badge-closed', label: '잔여 소진(추가공고 확인)', stale: false };
    const ratio = st.n ? st.left / st.n : 0;
    if (st.left < 30 || ratio < 0.06) return { cls: 'badge-low', label: `마감 임박 · 잔여 ${fmt(st.left)}대`, stale: false };
    return { cls: 'badge-open', label: `접수 중 · 잔여 ${fmt(st.left)}대`, stale: false };
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
        <a href="https://ev.or.kr" target="_blank" rel="noopener">무공해차 통합누리집 ↗</a>
        <a href="mailto:hlee9108@gmail.com">오류 제보</a>
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
      const s = document.createElement('script');
      s.async = true;
      s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${SITE.ads.client}`;
      s.crossOrigin = 'anonymous';
      document.head.appendChild(s);
      slots.forEach(slot => {
        const box = slot.querySelector('.ad-box');
        const adId = slot.dataset.adSlot || '';
        box.innerHTML = `<ins class="adsbygoogle" style="display:block;width:100%" data-ad-client="${SITE.ads.client}" data-ad-slot="${adId}" data-ad-format="auto" data-full-width-responsive="true"></ins>`;
        box.style.border = 'none';
        (window.adsbygoogle = window.adsbygoogle || []).push({});
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
      guSel.innerHTML = `<option value="">시·군·구</option>` + list.map(([cd, r]) => `<option value="${cd}">${r.name}</option>`).join('');
      guSel.disabled = false;
      if (list.length === 1) { guSel.value = list[0][0]; guSel.dispatchEvent(new Event('change')); }
      else if (pick) guSel.value = pick;
    }
    sidoSel.onchange = () => { fillGu(sidoSel.value); if (guSel.value && opts.onPick) opts.onPick(guSel.value, regions[guSel.value]); };
    guSel.onchange = () => { if (guSel.value) { window.myRegion.set(guSel.value); opts.onPick && opts.onPick(guSel.value, regions[guSel.value]); } };
    const init = opts.value || window.myRegion.get();
    if (init && regions[init]) { sidoSel.value = regions[init].sido; fillGu(regions[init].sido, init); }
    return { get: () => guSel.value || null };
  };

  /* ── 부팅 ── */
  document.addEventListener('DOMContentLoaded', () => {
    header(); footer(); renderCmpBar(); renderAds();
  });
})();
