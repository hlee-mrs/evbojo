#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EV보조금 데이터 자동 갱신기 (무공해차 통합누리집 ev.or.kr)
────────────────────────────────────────────────────────
ev.or.kr은 웹방화벽(JS 챌린지)이 있어 requests/curl로는 수집 불가.
→ Playwright 헤드리스 브라우저로 실제 렌더링 후 DOM에서 추출한다.

모드
  --status : 접수현황(공고/접수/출고/잔여) 갱신  → status.json      [매시간 권장]
  --full   : 차종 국비 + 161개 지자체 지방비 전체 재수집             [매일 새벽 권장]
  --once   : 둘 다 1회 실행

안전장치 (fail-safe)
  · 3회 재시도(지수 백오프) 후 실패 시 기존 파일 유지 + updater.log 기록
  · 검증 실패(행 수 부족, 값 이상) 시 교체하지 않음
  · --full 은 기존 대비 변경 행 비율이 40% 초과하면 '보류'(사이트 구조 변경 의심)
    → data/_pending/ 에 저장하고 알림 로그만 남김 (FORCE=1 env로 강제 적용)
  · 원자적 교체(os.replace) → 서빙 중인 사이트가 깨진 JSON을 읽는 일 없음
"""
import argparse, json, os, re, shutil, sys, time
from datetime import datetime, timezone, timedelta

from playwright.sync_api import sync_playwright

BASE = 'https://ev.or.kr'
KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get('DATA_DIR', os.path.join(ROOT, '..', 'site', 'data'))
LOG = os.path.join(ROOT, 'updater.log')
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 evbojo-updater(+contact: hlee9108@gmail.com)'
YEAR = os.environ.get('EV_YEAR', '2026')
PAGE_DELAY = float(os.environ.get('PAGE_DELAY', '1.2'))   # 지자체 팝업 간 대기(예의)


def log(msg):
    line = f"[{datetime.now(KST).isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def atomic_write(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def with_retry(fn, name, tries=3):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — 어떤 실패든 재시도
            wait = 20 * (2 ** i)
            log(f'{name} 실패({i+1}/{tries}): {e} → {wait}s 후 재시도')
            time.sleep(wait)
    raise RuntimeError(f'{name}: {tries}회 모두 실패')


# ─────────────────────────── 스크레이퍼 ───────────────────────────

def new_page(pw):
    browser = pw.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    ctx = browser.new_context(user_agent=UA, locale='ko-KR', viewport={'width': 1280, 'height': 900})
    page = ctx.new_page()
    page.set_default_timeout(45000)
    return browser, page


def wait_table(page, min_rows=1):
    page.wait_for_function(
        f"() => document.querySelectorAll('table tbody tr').length >= {min_rows}",
        timeout=45000,
    )


def scrape_status(page):
    """지급현황: 161개 지자체 공고/접수/출고/잔여 (전기승용)"""
    page.goto(f'{BASE}/nportal/buySupprt/initSubsidyPaymentCheckAction.do', wait_until='domcontentloaded')
    wait_table(page, 150)
    rows = page.evaluate(r"""() => {
      const t = [...document.querySelectorAll('table')].find(x => x.querySelectorAll('tbody tr').length >= 150);
      const num = s => { const m = (s||'').match(/^([0-9,]+)/); return m ? +m[1].replace(/,/g,'') : null; };
      return [...t.querySelectorAll('tbody tr')].map(tr => {
        const c = [...tr.querySelectorAll('td,th')].map(x => x.textContent.replace(/\s+/g,' ').trim());
        return { name: c[1], m: (c[4]||'').replace('*일반: ','일반 ').replace('*우선: ',' · 우선 '),
                 n: num(c[5]), a: num(c[6]), r: num(c[7]), left: num(c[8]) };
      });
    }""")
    if len(rows) < 150:
        raise ValueError(f'현황 행 수 이상: {len(rows)}')
    return rows


def scrape_local_units(page, cd):
    """지자체 모델별 단가 팝업 → [(국비, 지방비, 전환지방비, 모델명), ...]"""
    page.goto(f'{BASE}/nportal/buySupprt/psPopupLocalCarModelPrice.do?year={YEAR}&local_cd={cd}&car_type=11',
              wait_until='domcontentloaded')
    wait_table(page, 5)
    return page.evaluate(r"""() => [...document.querySelectorAll('table tbody tr')].map(tr => {
      const c = [...tr.querySelectorAll('td,th')].map(x => x.textContent.replace(/,/g,'').trim());
      return { name: c[2], nat: +c[3], loc: +c[4], convNat: +(c[6]||0), convLoc: +(c[7]||0), cls: c[0] };
    })""")


def scrape_specs(page):
    """구매보조금 지급대상 차종(승용) — 주행거리/배터리"""
    page.goto(f'{BASE}/nportal/buySupprt/initSubsidyTargetVehicleAction.do', wait_until='domcontentloaded')
    page.wait_for_selector('div.infoBox', timeout=45000)
    try:
        page.evaluate("goPage('statsList', 300, 1)")
        page.wait_for_load_state('domcontentloaded')
        page.wait_for_selector('div.infoBox', timeout=45000)
    except Exception:
        log('goPage(300) 실패 — 첫 페이지만 수집')
    return page.evaluate(r"""() => {
      const MAKERS=['현대자동차','기아','테슬라코리아','메르세데스벤츠코리아','볼보자동차코리아','케이지모빌리티','폭스바겐그룹코리아','BMW','비와이디코리아','아우디폭스바겐코리아'];
      return [...document.querySelectorAll('div.infoBox')].map(el => {
        const t = el.textContent.replace(/\s+/g,' ').trim();
        const head = t.split(/-\s*승차인원/)[0].trim();
        const maker = MAKERS.find(m => head.startsWith(m)) || '';
        const g = re => { const m = t.match(re); return m ? +m[1].replace(/,/g,'') : null; };
        return { maker, name: head.slice(maker.length).trim(),
                 range: g(/상온\)?\s*([0-9,]+)\s*km/), rangeCold: g(/저온\)?\s*([0-9,]+)\s*km/),
                 batt: (t.match(/\(([0-9.]+)\s*kWh/) || [null,null])[1] && +t.match(/\(([0-9.]+)\s*kWh/)[1] };
      });
    }""")


# ─────────────────────────── 갱신 작업 ───────────────────────────

def norm_name(s):
    s = re.sub(r'\(\d+만원\)', '', s).replace('(단종)', '')
    return re.sub(r'[^0-9a-zA-Z가-힣]', '', s).lower()


def update_status(page):
    regions = read_json(os.path.join(DATA, 'regions.json'))
    if not regions:
        raise RuntimeError('regions.json 없음 — full 갱신을 먼저 실행')
    rows = with_retry(lambda: scrape_status(page), '지급현황 수집')
    # 이름 → cd 매핑 (중복 지명은 등장 순서 = 표 순서)
    by_name = {}
    for cd, r in regions.items():
        by_name.setdefault(r['name'], []).append(cd)
    data, used = {}, {}
    for row in rows:
        cds = by_name.get(row['name'])
        if not cds:
            continue
        idx = used.get(row['name'], 0)
        if idx < len(cds):
            data[cds[idx]] = {'m': row['m'], 'n': row['n'], 'a': row['a'], 'r': row['r'], 'left': row['left']}
            used[row['name']] = idx + 1
    if len(data) < 150:
        raise ValueError(f'매핑된 지역 수 이상: {len(data)}')
    atomic_write(os.path.join(DATA, 'status.json'),
                 {'updated': datetime.now(KST).isoformat(timespec='minutes'), 'data': data})
    log(f'status.json 갱신 완료 ({len(data)}개 지역)')


def update_full(page):
    """차종 마스터(서울 팝업 기준 순서) + 전 지역 지방비 + 제원 재수집"""
    old_regions = read_json(os.path.join(DATA, 'regions.json')) or {}
    old_cars = read_json(os.path.join(DATA, 'cars.json')) or []
    meta = read_json(os.path.join(DATA, 'meta.json')) or {}

    # 1) 서울 팝업 = 마스터 모델 목록·순서·국비
    seoul = with_retry(lambda: scrape_local_units(page, '1100'), '마스터(서울) 수집')
    if len(seoul) < 100:
        raise ValueError(f'마스터 행 수 이상: {len(seoul)}')
    cars = []
    for i, m in enumerate(seoul):
        cars.append({'id': i, 'cls': 'S' if '경' in m['cls'] else 'P', 'maker': '', 'name': m['name'],
                     'nat': m['nat'], 'convNat': m['convNat'], 'disc': m['name'].startswith('(단종)'),
                     'range': None, 'rangeCold': None, 'batt': None})
    nat_seq = [c['nat'] for c in cars]

    # 2) 제원 병합
    specs = with_retry(lambda: scrape_specs(page), '제원 수집')
    smap = {norm_name(s['name']): s for s in specs if s['name']}
    mmap = {norm_name(s['name']): s['maker'] for s in specs if s['name']}
    for c in cars:
        k = norm_name(c['name'])
        sp = smap.get(k) or (smap.get(norm_name('Pv5 WAV')) if k.startswith('pv5wav') else None)
        if sp:
            c.update({'range': sp['range'], 'rangeCold': sp['rangeCold'], 'batt': sp['batt']})
        c['maker'] = mmap.get(k) or next((o['maker'] for o in old_cars if norm_name(o['name']) == k and o.get('maker')), '') or c['maker']

    # 3) 전 지역 지방비 (요약표에서 지역 목록 추출)
    page.goto(f'{BASE}/nportal/buySupprt/initPsLocalCarPirceAction.do', wait_until='domcontentloaded')
    wait_table(page, 150)
    region_list = page.evaluate(r"""() => {
      const t = [...document.querySelectorAll('table')].find(x => x.querySelectorAll('tbody tr').length >= 150);
      return [...t.querySelectorAll('tbody tr')].map(tr => {
        const td = [...tr.querySelectorAll('td,th')].map(c => c.textContent.replace(/\s+/g,' ').trim());
        const btn = tr.querySelector('[href*=psPopupLocalCarModelPrice],[onclick*=psPopupLocalCarModelPrice]');
        const m = btn ? ((btn.getAttribute('onclick')||btn.getAttribute('href')||'').match(/'(\d{4})','(\d+)','([^']+)'/)) : null;
        const p = s => { const x = s.match(/승용\s*([0-9,]+)/); return x ? +x[1].replace(/,/g,'') : null; };
        const q = s => { const x = s.match(/소형\s*([0-9,]+)/); return x ? +x[1].replace(/,/g,'') : null; };
        return { cd: m ? m[2] : null, sido: td[0], name: td[1], maxP: p(td[3]||''), maxS: q(td[3]||'') };
      }).filter(r => r.cd);
    }""")
    if len(region_list) < 150:
        raise ValueError(f'지역 목록 이상: {len(region_list)}')

    regions_out = {}
    for idx, r in enumerate(region_list):
        rows = with_retry(lambda cd=r['cd']: scrape_local_units(page, cd), f"지자체 {r['name']}")
        # 국비 시퀀스 기준 정렬(그리디) — 지역별 누락 모델 대응
        vals, j = [], 0
        for i in range(len(cars)):
            if j < len(rows) and rows[j]['nat'] == nat_seq[i]:
                vals.append([rows[j]['loc'], rows[j]['convLoc']]); j += 1
            else:
                vals.append(None)
        if j != len(rows):
            raise ValueError(f"{r['name']} 정렬 실패 {j}/{len(rows)} — 모델 목록 변경 의심, full 중단")
        old = old_regions.get(r['cd'], {})
        regions_out[r['cd']] = {'name': r['name'], 'sido': r['sido'],
                                'dept': old.get('dept', ''), 'tel': old.get('tel', ''),
                                'maxP': r['maxP'], 'maxS': r['maxS'], 'rep': False, 'v': vals}
        time.sleep(PAGE_DELAY)
        if (idx + 1) % 20 == 0:
            log(f'  지자체 진행 {idx+1}/{len(region_list)}')

    # 4) 변경 감지 + 급변 보류
    changed = 0
    for cd, r in regions_out.items():
        if json.dumps(r['v']) != json.dumps(old_regions.get(cd, {}).get('v')):
            changed += 1
    nat_changed = sum(1 for c in cars if c['id'] < len(old_cars) and old_cars[c['id']]['nat'] != c['nat'])
    ratio = changed / max(1, len(regions_out))
    log(f'변경: 지자체 {changed}곳, 국비 {nat_changed}건 (변경률 {ratio:.0%})')
    if old_regions and ratio > 0.4 and os.environ.get('FORCE') != '1':
        pend = os.path.join(DATA, '_pending')
        os.makedirs(pend, exist_ok=True)
        atomic_write(os.path.join(pend, 'cars.json'), cars)
        atomic_write(os.path.join(pend, 'regions.json'), regions_out)
        log('⚠ 변경률 40% 초과 — 적용 보류(_pending). 확인 후 FORCE=1로 재실행하거나 수동 반영하세요.')
        return

    today = datetime.now(KST).strftime('%Y-%m-%d')
    atomic_write(os.path.join(DATA, 'cars.json'), cars)
    atomic_write(os.path.join(DATA, 'regions.json'), regions_out)
    meta.update({'updated': today, 'source': '무공해차 통합누리집(ev.or.kr)',
                 'natMax': max(nat_seq), 'year': int(YEAR)})
    atomic_write(os.path.join(DATA, 'meta.json'), meta)
    log(f'full 갱신 완료: 차종 {len(cars)}, 지자체 {len(regions_out)}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--status', action='store_true')
    ap.add_argument('--full', action='store_true')
    ap.add_argument('--once', action='store_true')
    a = ap.parse_args()
    if not (a.status or a.full or a.once):
        ap.print_help(); sys.exit(1)
    os.makedirs(DATA, exist_ok=True)
    # 백업 (최근 1세대)
    for f in ('cars.json', 'regions.json', 'status.json', 'meta.json'):
        p = os.path.join(DATA, f)
        if os.path.exists(p):
            shutil.copy2(p, p + '.bak')
    with sync_playwright() as pw:
        browser, page = new_page(pw)
        try:
            if a.full or a.once:
                update_full(page)
            if a.status or a.once:
                update_status(page)
        finally:
            browser.close()


if __name__ == '__main__':
    main()
