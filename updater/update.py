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
import argparse, json, math, os, re, shutil, sys, time, zipfile, zlib
from datetime import datetime, timezone, timedelta, date
from io import BytesIO
from xml.etree import ElementTree as ET

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


# ─────────────────────────── 수집 (공식 엑셀 1회 다운로드) ───────────────────────────
# 2026-08-16 ev.or.kr 전면 개편으로 기존 표 스크레이핑 전체 폐기.
# 개편 사이트의 "Excel 다운로드"(localinfoExcelDownload2.do)가 전 시트를 제공:
#   sheet2 지역별 현황(접수상태·최종마감·비고·담당부서 포함) · sheet3 우선/법인/택시/일반 분해
#   sheet6 지역×모델 국비/지방비/전환/총액/배터리/주행거리 · sheet5 공고 목록 · sheet7 변경이력
# → 한 파일이 기존 status + full(팝업 161회) + 제원 수집을 전부 대체 (요청 수 165→2).

def new_page(pw):
    browser = pw.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    ctx = browser.new_context(user_agent=UA, locale='ko-KR', viewport={'width': 1280, 'height': 900})
    page = ctx.new_page()
    page.set_default_timeout(45000)
    return browser, ctx, page


def download_workbook(ctx, page):
    """지급현황 페이지 방문(WAF 세션) 후 공식 엑셀 다운로드 → bytes"""
    page.goto(f'{BASE}/nportal/buySupprt/initSubsidyPaymentCheckAction.do', wait_until='domcontentloaded')
    page.wait_for_function(r"() => /총\s*[0-9,]+\s*건/.test(document.body.innerText)", timeout=45000)
    time.sleep(PAGE_DELAY)
    resp = ctx.request.post(
        f'{BASE}/nportal/buySupprt/localinfoExcelDownload2.do',
        form={'car_type': '11', 'year1': YEAR, 'localDo_cd': 'all', 'local_cd1': 'all'},
    )
    if resp.status != 200:
        raise RuntimeError(f'엑셀 다운로드 HTTP {resp.status}')
    body = resp.body()
    if not body.startswith(b'PK'):
        raise ValueError(f'엑셀 형식 아님 (head={body[:20]!r})')
    return body


_XNS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
_XT = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t'


def parse_workbook(blob):
    """xlsx(bytes) → {시트번호: [ {열문자: 값} ]} (stdlib zipfile+ElementTree, inlineStr/sharedStrings 모두 지원)"""
    z = zipfile.ZipFile(BytesIO(blob))
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', _XNS):
            shared.append(''.join(t.text or '' for t in si.iter(_XT)))
    sheets = {}
    for name in z.namelist():
        m = re.fullmatch(r'xl/worksheets/sheet(\d+)\.xml', name)
        if not m:
            continue
        rows = []
        for r in ET.fromstring(z.read(name)).findall('.//m:row', _XNS):
            cells = {}
            for c in r.findall('m:c', _XNS):
                col = re.match(r'[A-Z]+', c.get('r', 'A')).group()
                v = c.find('m:v', _XNS)
                if v is not None:
                    cells[col] = shared[int(v.text)] if c.get('t') == 's' else v.text
                else:
                    iss = c.find('m:is', _XNS)
                    cells[col] = ''.join(t.text or '' for t in iss.iter(_XT)) if iss is not None else None
            rows.append(cells)
        sheets[int(m.group(1))] = rows
    return sheets


def _int(v):
    """'15430.0' → 15430, 빈 값 → None"""
    if v is None or v == '':
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def _cd(row):
    """관리번호 '2026-1100' → '1100' (형식 불일치는 None)"""
    m = re.fullmatch(r'\d{4}-(\d{4,5})', (row.get('A') or '').strip())
    return m.group(1) if m else None


def _clean(s, cap=2000):
    """비고/텍스트 공백 정규화 — 구 표 수집(textContent 공백 축약)과 동일 형태 유지"""
    if not s:
        return None
    return re.sub(r'\s+', ' ', s).strip()[:cap] or None


def build_status_rows(sheets):
    """sheet2(지역 현황)+sheet3(4분류) → 구 scrape_status와 동일 스키마 + 공식 접수상태(st)·최종마감(dl)·선정(sel/sleft)
    ※ 4분류 합계가 전체와 다를 수 있음(공고 회차 이월 등, ev.or.kr 원본 특성) — 그대로 보존."""
    s2, s3 = sheets.get(2, []), sheets.get(3, [])
    if not s2 or (s2[0].get('A') or '') != '관리번호':
        raise ValueError('sheet2 헤더 이상 — 엑셀 구조 변경 의심')
    # sheet3: cd → 구분(공고대수 등) → [우선, 법인, 택시, 일반]
    GUBUN = {'공고대수': 'n', '접수대수': 'a', '출고대수': 'r', '출고잔여': 'left'}
    brk = {}
    for r in s3[1:]:
        cd, key = _cd(r), GUBUN.get((r.get('G') or '').strip())
        if cd and key:
            brk.setdefault(cd, {})[key] = [_int(r.get('I')), _int(r.get('J')), _int(r.get('K')), _int(r.get('L'))]
    rows = []
    for r in s2[1:]:
        cd = _cd(r)
        if not cd:
            continue
        m = (r.get('G') or '').replace('*일반: ', '일반 ').replace(' / *우선: ', ' · 우선 ').replace('*우선: ', '우선 ')
        d = brk.get(cd)
        rows.append({'cd': cd, 'name': _clean(r.get('D'), 100), 'm': _clean(m, 200),
                     'n': _int(r.get('L')), 'a': _int(r.get('M')), 'r': _int(r.get('O')), 'left': _int(r.get('Q')),
                     'sel': _int(r.get('N')), 'sleft': _int(r.get('P')),
                     'st': _clean(r.get('H'), 20), 'dl': _clean(r.get('K'), 40),
                     'd': d if d and len(d) == 4 else None,
                     'note': _clean(r.get('Y')),
                     'dept': _clean(r.get('W'), 100), 'tel': _clean(r.get('X'), 40)})
    if len(rows) < 150:
        raise ValueError(f'현황 행 수 이상: {len(rows)}')
    return rows


def _batt(s):
    m = re.search(r'\(([0-9.]+)\s*kWh', s or '')
    return float(m.group(1)) if m else None


def _range(s):
    """'(상온) 470km (저온) 416km' → (470, 416)"""
    warm = re.search(r'상온\)?\s*([0-9,]+)\s*km', s or '')
    cold = re.search(r'저온\)?\s*([0-9,]+)\s*km', s or '')
    return (int(warm.group(1).replace(',', '')) if warm else None,
            int(cold.group(1).replace(',', '')) if cold else None)


def disp_name(s):
    """소비자 표시명: 피드의 제조사 내부 사양코드 괄호 제거 — 'iX1 eDrive20(11HM)' → 'iX1 eDrive20'.
    연식 '(2025)'·가격구간 '(5999만원)'·'(단종)' 등 의미 있는 괄호는 보존. 표기 교정: Pv5 → PV5."""
    out = re.sub(r'\(\s*[0-9]{1,2}[A-Z]{1,3}[0-9]?\s*\)', '', s or '')
    out = out.replace('Pv5', 'PV5')
    return re.sub(r'\s+', ' ', out).strip()


def _general_row(r):
    """일반 구매 가능 행만 — WAV·미지원 표기 모델은 헤드라인 '최대' 산출에서 제외(팩트체크 I3)"""
    g = r.get('G') or ''
    return 'WAV' not in g and '미지원' not in g


# ─────────────────────────── 갱신 작업 ───────────────────────────

def norm_name(s):
    s = re.sub(r'\(\d+만원\)', '', s).replace('(단종)', '')
    return re.sub(r'[^0-9a-zA-Z가-힣]', '', s).lower()


def update_status(sheets):
    regions = read_json(os.path.join(DATA, 'regions.json'))
    if not regions:
        raise RuntimeError('regions.json 없음 — full 갱신을 먼저 실행')
    rows = build_status_rows(sheets)
    # 관리번호가 cd를 직접 제공 — 구 이름 순서 매핑 폐기. regions.json과의 교집합으로 정합성 검증.
    data = {}
    for row in rows:
        cd = row['cd']
        entry = {'m': row['m'], 'n': row['n'], 'a': row['a'], 'r': row['r'], 'left': row['left']}
        if row.get('d'):
            entry['d'] = row['d']
        if row.get('note'):
            entry['note'] = row['note']
        # 개편 사이트의 공식 필드(추가분): 접수상태·최종 신청마감·선정/선정잔여
        if row.get('st'):
            entry['st'] = row['st']
        if row.get('dl'):
            entry['dl'] = row['dl']
        if row.get('sel') is not None:
            entry['sel'] = row['sel']
        if row.get('sleft') is not None:
            entry['sleft'] = row['sleft']
        data[cd] = entry
    known = sum(1 for cd in data if cd in regions)
    if known < 150:
        raise ValueError(f'regions.json과 겹치는 지역 수 이상: {known}')
    now = datetime.now(KST).isoformat(timespec='minutes')
    atomic_write(os.path.join(DATA, 'status.json'),
                 {'updated': now, 'data': data})
    # meta.statusUpdated = 잔여현황 기준시각. update_full은 단가 기준일(updated)만 갱신해서
    # 이 키가 과거 값에 고착돼 있었다(공개 JSON 노출). 여기서 status.json과 같은 시각으로 동기화.
    # (키 제거 대신 갱신을 택함 — app.js가 st.updated 미확보 시 폴백으로 이 값을 읽는다.)
    meta_path = os.path.join(DATA, 'meta.json')
    meta = read_json(meta_path)
    if isinstance(meta, dict):
        meta['statusUpdated'] = now
        atomic_write(meta_path, meta)
    else:
        log('⚠ meta.json 읽기 실패 — statusUpdated 동기화 생략(status.json은 정상 갱신)')
    update_history(data, datetime.now(KST))
    log(f'status.json 갱신 완료 ({len(data)}개 지역)')


def update_rounds(sheets):
    """공고 차수(sheet5)·공단 공식 변경이력(sheet7) → rounds.json.
    지역 페이지의 '그 지역에서만 참인' 고유 콘텐츠 원천 — 공고 연혁 타임라인용."""
    s5, s7 = sheets.get(5, []), sheets.get(7, [])
    rounds, events = {}, {}
    for r in s5[1:]:
        cd = _cd(r)
        if not cd:
            continue
        rounds.setdefault(cd, []).append({
            'k': _clean(r.get('G'), 20), 'nm': _clean(r.get('H'), 80),
            'post': _clean(r.get('I'), 20), 's': _clean(r.get('J'), 20),
            'e': _clean(r.get('K'), 20), 'd': _clean(r.get('L'), 20)})
    cutoff = (datetime.now(KST) - timedelta(days=90)).strftime('%Y-%m-%d')
    for r in s7[1:]:
        cd = _cd(r)
        t = _clean(r.get('C'), 20) or ''
        if not cd or t[:10] < cutoff:
            continue
        events.setdefault(cd, []).append([t, _clean(r.get('E'), 40), _clean(r.get('F'), 40), _clean(r.get('G'), 40)])
    # evn = 자르기 전 원 건수(최근 90일 전체). events는 12건으로 잘리므로, 이 값이 없으면
    # 프리렌더 라벨이 잘린 수를 전체 건수인 양 단정하게 된다(라벨-실제 불일치).
    evn = {cd: len(v) for cd, v in events.items()}
    for cd in events:
        events[cd] = sorted(events[cd], key=lambda e: e[0], reverse=True)[:12]
    if len(rounds) < 100:                      # 구조 변경 방어 — 이상 시 기존 파일 유지
        log(f'⚠ 공고 차수 지역 수 이상({len(rounds)}) — rounds.json 미교체')
        return
    atomic_write(os.path.join(DATA, 'rounds.json'),
                 {'updated': datetime.now(KST).isoformat(timespec='minutes'),
                  'rounds': rounds, 'events': events, 'evn': evn})
    log(f'rounds.json 갱신 ({len(rounds)}개 지역 · 최근 90일 변경 {sum(len(v) for v in events.values())}건)')


# ── 잔여 이력(history.json) — 소진 예측용 ─────────────────────────
# 일(日) 버킷 시간축(그날 마지막 관측 승리) + 지역별 병렬 배열. 45일 롤링, 100KB 하드캡.
# 시리즈: l=전체 잔여, g=일반 잔여(d.left[3]). 회차 리셋·정체는 시리즈별 메타(L/G)로 추적.
RESET_MIN, RESET_PCT, EV_CAP, KEEP_DAYS, SIZE_CAP = 10, 0.05, 4, 45, 100_000
HOLIDAYS = ['2026-08-17', '2026-09-24', '2026-09-25', '2026-09-26',
            '2026-10-05', '2026-10-09', '2026-12-25']   # 주중 법정공휴일·대체휴일만(연초 수동 갱신)
D0 = date(2026, 1, 1)


def note_hash(s):
    return zlib.crc32((s.get('note') or '').encode()) & 0xffffffff


def new_meta(day, v, n):
    return {'rd': {'t': day, 'v': v, 'n': n}, 'lc': None, 'ev': [], 'inc': None}


def last_nonnull(a):
    return next((v for v in reversed(a) if v is not None), None)


def do_reset(m, day, prev, val, n, t=None):
    m['rd'] = {'t': t if t is not None else day, 'v': val, 'n': n}
    m['lc'], m['inc'] = None, None
    m['ev'] = (m['ev'] + [[day, 0, prev, val]])[-EV_CAP:]


def detect(m, key, e, prev, val, n, day, note_changed):
    """리셋·정체 감지 (시리즈별 독립)"""
    thr = max(RESET_MIN, math.ceil(RESET_PCT * (n or prev or 1)))
    d = val - prev
    n_up = key == 'L' and n is not None and e.get('n') is not None and n > e['n']
    if d >= thr or n_up:                               # 회차 리셋(추가공고)
        do_reset(m, day, prev, val, n)
    elif 0 < d < thr:
        if note_changed:                               # 공지 변경 동반 소폭 증가 = 리셋
            do_reset(m, day, prev, val, n)
        else:                                          # 7일 누적 소급 리셋(취소 환입과 구분)
            if m['inc'] and day - m['inc'][0] <= 7:
                m['inc'][1] += d
            else:
                m['inc'] = [day, d]
            if m['inc'][1] >= thr:
                do_reset(m, day, prev, val, n, t=m['inc'][0])
    elif d < 0:                                        # 감소 관측 → 정체 시계 리셋
        m['lc'], m['inc'] = day, None


def update_history(data, now):
    path = os.path.join(DATA, 'history.json')
    h = read_json(path) or read_json(path + '.bak')
    if not h or h.get('v') != 1:
        h = {'v': 1, 'd0': '2026-01-01', 'days': [], 'r': {}}
    day = (now.date() - D0).days
    append = not h['days'] or h['days'][-1] != day     # 하루 여러 크롤 = 오늘 버킷 덮어쓰기
    if append:
        h['days'].append(day)
    L = len(h['days'])
    for cd, s in data.items():
        left, n = s.get('left'), s.get('n')
        darr = (s.get('d') or {}).get('left') or [None] * 4
        g = darr[3]                                    # 일반 = index 3 (CATS idx와 동일)
        e = h['r'].setdefault(cd, {'l': [], 'g': [], 'n': n, 'nh': note_hash(s),
                                   'L': new_meta(day, left, n), 'G': new_meta(day, g, n)})
        while len(e['l']) < L - 1:
            e['l'].append(None)                        # 신규 지역: 앞쪽 null 정렬
        while len(e['g']) < L - 1:
            e['g'].append(None)
        nch = note_hash(s) != e.get('nh')
        for key, arr, val in (('L', e['l'], left), ('G', e['g'], g)):
            prev = last_nonnull(arr)
            if prev is not None and val is not None:
                detect(e[key], key, e, prev, val, n, day, nch)
            if append:
                arr.append(val)
            elif val is not None:
                arr[-1] = val                          # null로 기존값을 덮지 않음
        if n is not None and e.get('n') is not None and n < e['n']:   # 공고 감액 정정: 이벤트만
            e['L']['ev'] = (e['L']['ev'] + [[day, 2, e['n'], n]])[-EV_CAP:]
        if s.get('a') and n and s['a'] > n:
            log(f'⚠ {cd} 초과접수 a={s["a"]}>n={n}')
        if n is not None:
            e['n'] = n
        e['nh'] = note_hash(s)
    if append:                                         # 이번 크롤에 빠진 기존 지역
        for cd, e in h['r'].items():
            if cd not in data:
                e['l'].append(None)
                e['g'].append(None)
    while len(h['days']) > KEEP_DAYS:                  # 45일 롤링
        h['days'].pop(0)
        for e in h['r'].values():
            e['l'].pop(0)
            e['g'].pop(0)
    h['r'] = {cd: e for cd, e in h['r'].items()
              if any(v is not None for v in e['l']) or any(v is not None for v in e['g'])}
    h['holidays'], h['updated'] = HOLIDAYS, now.isoformat(timespec='minutes')
    if len(json.dumps(h, ensure_ascii=False, separators=(',', ':'))) > SIZE_CAP:   # 100KB 하드캡
        cut = len(h['days']) - 30
        h['days'] = h['days'][cut:]
        for e in h['r'].values():
            e['l'] = e['l'][cut:]
            e['g'] = e['g'][cut:]
        log('⚠ history.json 100KB 초과 — 30일로 자동 축소')
    assert all(len(e['l']) == len(h['days']) == len(e['g']) for e in h['r'].values())
    atomic_write(path, h)


def update_full(sheets):
    """차종 마스터 + 전 지역 지방비 + 제원 — 엑셀 sheet6(지역×모델)·sheet2(지역 정보)에서 재구성.
    기존 car id(= /car/N.html URL)를 보존: 기존 모델은 기존 위치 유지, 신규만 뒤에 추가, 사라진 모델은 disc."""
    old_regions = read_json(os.path.join(DATA, 'regions.json')) or {}
    old_cars = read_json(os.path.join(DATA, 'cars.json')) or []
    meta = read_json(os.path.join(DATA, 'meta.json')) or {}

    s2, s6 = sheets.get(2, []), sheets.get(6, [])
    if not s6 or (s6[0].get('G') or '') != '모델명':
        raise ValueError('sheet6 헤더 이상 — 엑셀 구조 변경 의심')
    mrows = [r for r in s6[1:] if _cd(r) and (r.get('G') or '').strip()]

    # 모델 식별 키 = 정확한 모델명(공백 정규화). norm_name은 '(5999만원)' 같은 가격 구간 표기를 지워
    # 트윈 트림(국비 상이)을 충돌시키므로 마스터 키로 쓰지 않는다 — 모호하지 않을 때만 폴백.
    def key_name(s):
        return re.sub(r'\s+', ' ', (s or '').replace('(단종)', '').strip())

    # 1) 모델 마스터: 모델명 기준 대표 행(첫 등장 순서 = 엑셀 순서). 국비는 지역 불변(2026-08-19 실측 0건 예외).
    seen, order = {}, []
    for r in mrows:
        k = key_name(r['G'])
        if k not in seen:
            seen[k] = r
            order.append(k)
    if len(seen) < 100:
        raise ValueError(f'마스터 모델 수 이상: {len(seen)}')
    # norm 폴백 사전: 같은 norm에 후보가 정확히 1개일 때만 (띄어쓰기 변화 등 흡수)
    norm_map = {}
    for k in order:
        norm_map.setdefault(norm_name(k), []).append(k)

    def find_new(name):
        k = key_name(name)
        if k in seen:
            return k
        cand = norm_map.get(norm_name(k))
        return cand[0] if cand and len(cand) == 1 else None

    cars, used = [], set()
    for old in old_cars:                       # 기존 id·순서 보존
        k = find_new(old['name'])
        if k is None:                          # 개편 데이터에서 사라진 모델 → 단종 처리(값은 마지막 관측 유지)
            c = dict(old)
            c['disc'] = True
            cars.append(c)
            continue
        used.add(k)
        r = seen[k]
        warm, cold = _range(r.get('J'))
        cars.append({'id': old['id'], 'cls': 'S' if '경' in (r.get('F') or '') or '소형' in (r.get('F') or '') else 'P',
                     'maker': _clean(r.get('H'), 60) or old.get('maker', ''), 'name': _clean(r.get('G'), 120),
                     'nat': _int(r.get('K')), 'convNat': _int(r.get('M')) or 0, 'disc': False,
                     'range': warm or old.get('range'), 'rangeCold': cold or old.get('rangeCold'),
                     'batt': _batt(r.get('I')) or old.get('batt')})
    for k in order:                            # 신규 모델은 뒤에 추가 (id 이어붙임)
        if k in used:
            continue
        r = seen[k]
        warm, cold = _range(r.get('J'))
        cars.append({'id': len(cars), 'cls': 'S' if '경' in (r.get('F') or '') or '소형' in (r.get('F') or '') else 'P',
                     'maker': _clean(r.get('H'), 60) or '', 'name': _clean(r.get('G'), 120),
                     'nat': _int(r.get('K')), 'convNat': _int(r.get('M')) or 0, 'disc': False,
                     'range': warm, 'rangeCold': cold, 'batt': _batt(r.get('I'))})
    for c in cars:                             # 소비자 표시명(사양코드 제거) — 매칭 키(name)는 원문 유지
        c['disp'] = disp_name(c['name'])
    idx_of = {key_name(c['name']): i for i, c in enumerate(cars)}

    # 2) 지역별 지방비 v 배열(모델명 직접 매칭 — 구 국비 시퀀스 그리디 정렬 폐기) + 지역 메타
    by_region = {}
    for r in mrows:
        by_region.setdefault(_cd(r), []).append(r)
    reg_info = {}
    for r in s2[1:]:
        cd = _cd(r)
        if cd:
            reg_info[cd] = r
    if len(by_region) < 150:
        raise ValueError(f'지역 목록 이상: {len(by_region)}')

    # 전환지방비: 개편 엑셀 N열은 전 행 일률 '지방비 100%'로 구 실측(지역별 4~20%)·공단 계산기(전환 가산 0)와
    # 모순 → 채택 기각(I3). 마지막 검증값을 보존하고, 근거 없는 모델은 0(전환 서술 자동 억제).
    def old_v_resolved(cd):
        r = old_regions.get(cd) or {}
        if r.get('v'):
            return r['v']
        return (old_regions.get(r.get('ref')) or {}).get('v') or []

    regions_out = {}
    for cd, rows in by_region.items():
        old_v = old_v_resolved(cd)
        vals = [None] * len(cars)
        for r in rows:
            i = idx_of.get(key_name(r['G']))
            if i is not None:
                conv = old_v[i][1] if i < len(old_v) and old_v[i] else 0
                vals[i] = [_int(r.get('L')) or 0, conv]
        # 단종 모델(개편 데이터에 없음)은 마지막 관측값 보존 — 단종 차량 페이지 표시용
        for i, c in enumerate(cars):
            if c['disc'] and vals[i] is None and i < len(old_v):
                vals[i] = old_v[i]
        # 헤드라인 '최대'는 일반 구매 가능 모델 기준(WAV·미지원 제외) — title·산문·표 1위와 일원화
        tots = [_int(r.get('O')) for r in rows if _int(r.get('O')) is not None and _general_row(r)]
        stot = [_int(r.get('O')) for r in rows
                if _int(r.get('O')) is not None and _general_row(r)
                and ('경' in (r.get('F') or '') or '소형' in (r.get('F') or ''))]
        info = reg_info.get(cd, {})
        old = old_regions.get(cd, {})
        regions_out[cd] = {'name': _clean(info.get('D'), 100) or old.get('name', ''),
                           'sido': _clean(info.get('C'), 40) or old.get('sido', ''),
                           'dept': _clean(info.get('W'), 100) or old.get('dept', ''),
                           'tel': _clean(info.get('X'), 40) or old.get('tel', ''),
                           'maxP': max(tots) if tots else old.get('maxP'),
                           'maxS': max(stot) if stot else None,
                           'rep': False, 'v': vals}

    # 도 단위 대표값 압축 유지: 기존 ref 구조를 v가 대표와 동일할 때만 보존(다르면 자체 v 실체화)
    for cd, out in regions_out.items():
        old = old_regions.get(cd) or {}
        ref = old.get('ref')
        if old.get('rep') and ref in regions_out and out['v'] == regions_out[ref]['v']:
            regions_out[cd] = {k: v for k, v in out.items() if k != 'v'}
            regions_out[cd].update({'rep': True, 'ref': ref})

    # 4) 변경 감지 + 급변 보류
    # 신규 모델로 v 꼬리가 늘어나는 구조 변화는 급변이 아님 — 겹치는 구간의 값 변화만 집계.
    # 대신 마스터 급증(>10%)은 수집 오염 신호로 별도 보류.
    if old_cars and (len(cars) - len(old_cars)) > max(5, 0.1 * len(old_cars)):
        raise ValueError(f'모델 수 급증 {len(old_cars)}→{len(cars)} — 수집 오염 의심, full 중단')
    changed = 0
    for cd, r in regions_out.items():
        ov = old_regions.get(cd, {}).get('v')
        nv = r.get('v')
        if (ov is None) != (nv is None):
            changed += 1
        elif ov and nv and any(o != n for o, n in zip(ov, nv)):
            changed += 1
    nat_changed = sum(1 for c in cars if c['id'] < len(old_cars) and old_cars[c['id']]['nat'] != c['nat'])
    ratio = changed / max(1, len(regions_out))
    log(f'변경: 지자체 {changed}곳, 국비 {nat_changed}건 (변경률 {ratio:.0%}), 모델 {len(old_cars)}→{len(cars)}')
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
    # natMax: 일반 승용 국비 상한 — WAV·미지원 표기 모델은 제외(팩트체크: WAV는 최고액 서술 대상 아님)
    nat_pool = [c['nat'] for c in cars
                if not c['disc'] and c['nat'] and 'WAV' not in c['name'] and '미지원' not in c['name']]
    meta.update({'updated': today, 'source': '무공해차 통합누리집(ev.or.kr)',
                 'natMax': max(nat_pool), 'year': int(YEAR)})
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
    for f in ('cars.json', 'regions.json', 'status.json', 'meta.json', 'history.json'):
        p = os.path.join(DATA, f)
        if os.path.exists(p):
            shutil.copy2(p, p + '.bak')
    # 엑셀 1회 다운로드가 full·status 공용 소스. XLSX_PATH 지정 시 파일 재사용(테스트·재처리용, 네트워크 없음).
    xlsx_path = os.environ.get('XLSX_PATH')
    if xlsx_path:
        with open(xlsx_path, 'rb') as f:
            blob = f.read()
        log(f'XLSX_PATH 사용: {xlsx_path} ({len(blob)}B) — 다운로드 생략')
    else:
        with sync_playwright() as pw:
            browser, ctx, page = new_page(pw)
            try:
                blob = with_retry(lambda: download_workbook(ctx, page), '엑셀 다운로드')
            finally:
                browser.close()
    sheets = parse_workbook(blob)
    if a.full or a.once:
        update_full(sheets)
    if a.status or a.once:
        update_status(sheets)
        update_rounds(sheets)


if __name__ == '__main__':
    main()
