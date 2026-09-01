#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EV보조금 일간 브리핑 엔진 (stdlib 전용, /usr/bin/python3)

매일 아침 1회 실행 → site/brief/YYYY-MM-DD.html 생성.
입력: site/data/status.json(오늘), history.json(일별 잔여 시리즈), regions.json,
      전일 스냅샷 updater/.brief_prev.json(자체 보관 — 첫 실행은 history 폴백).

원칙(스펙·팩트체크 준수):
- 그날만의 실측 사실만 서술. 점추정·D-day·'실시간' 금지. 마감 판정은 prerender의
  detect_closed(완료형 선언만) 재사용. 잔여는 출고 시점 차감 지역 다수 — 단서 명기.
- 문장 풀 + 데이터 조건 분기 + md5 시드(pick/compose 재사용, 시드에 날짜 포함) —
  같은 입력이면 같은 출력(멱등), 날마다 변형이 자연 분산.
- 차트는 순수 파이썬 SVG 문자열(외부 요청 0, 시스템 폰트, var() 토큰 → 다크모드 대응).
- 발행 스킵: status.json 24h 이상 stale, 또는 전일 대비 변화 0(잔여 변동·이벤트 없음).
  스킵도 정상 종료(exit 0) — stdout 'brief SKIP: …'로 구분.
- 이미 존재하는 그날 파일은 덮어쓰지 않음(--force 시 재생성). 쓰기는 원자 교체.
"""
import argparse
import datetime
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import prerender as pr          # esc·fmt·pick·compose·render·detect_closed·atomic_write 재사용

ROOT = os.path.dirname(HERE)
KST, D0, BASE = pr.KST, pr.D0, pr.BASE
WD = ['월', '화', '수', '목', '금', '토', '일']
RESET_MIN, RESET_PCT = 10, 0.05          # update.py 리셋 판정과 동일 임계
STALE_HOURS = 24
# 금칙어(팩트체크): 점추정·과장·'실시간' — 발행 전 전체 텍스트 검사, 검출 시 빌드 실패
BANNED = ['실시간', '소진 예상', '예상 소진', '소진 예측', '소진일', 'D-', '곧 마감', '곧 소진']


def rj(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def note_crc(st):
    return zlib.crc32(((st or {}).get('note') or '').encode()) & 0xffffffff


def kdate(d):
    return '%d월 %d일(%s)' % (d.month, d.day, WD[d.weekday()])


# ── 전일 기준값 ──────────────────────────────────────────
def prev_basis(state, target_iso):
    """스냅샷에서 비교 기준을 고른다.
    state.date < 오늘 → state 자체가 전일 기준.
    state.date == 오늘(같은 날 --force 재실행) → state['prev']가 기준(멱등 유지)."""
    if not state or state.get('v') != 1:
        return None, None
    if state.get('date') == target_iso:
        p = state.get('prev')
        return (p.get('regions'), p) if p and p.get('regions') else (None, None)
    return state.get('regions'), state


def history_prev(hist, regions, before_day):
    """스냅샷이 없을 때 폴백: history l 시리즈에서 오늘(before_day) 이전 마지막 관측값."""
    if not hist or hist.get('v') != 1:
        return None
    days = hist.get('days') or []
    prevs = {}
    for cd, e in (hist.get('r') or {}).items():
        if cd not in regions:
            continue
        val = None
        for d, v in zip(days, e.get('l') or []):
            if d < before_day and v is not None:
                val = v
        if val is not None:
            prevs[cd] = {'left': val}
    return prevs or None


def recent_reset(hist, cd, target_day):
    """history 리셋 이벤트(type 0)가 어제~오늘 사이에 기록됐는지."""
    e = ((hist or {}).get('r') or {}).get(cd)
    if not e:
        return False
    for ev in ((e.get('L') or {}).get('ev')) or []:
        if len(ev) >= 2 and ev[1] == 0 and target_day - 1 <= ev[0] <= target_day:
            return True
    return False


# ── 전국 합계 시리즈 (지역별 ffill/bfill 후 합산 — 9999 제외) ──
def national_series(hist, regions, upto_day, window=28):
    if not hist or hist.get('v') != 1:
        return []
    days = hist.get('days') or []
    idx = [i for i, d in enumerate(days) if upto_day - (window - 1) <= d <= upto_day]
    if len(idx) < 2:
        return []
    filled = []
    for cd, e in (hist.get('r') or {}).items():
        if cd == '9999' or cd not in regions:
            continue
        arr = list(e.get('l') or [])
        last = None
        for i, v in enumerate(arr):
            if v is not None:
                last = v
            arr[i] = last
        nxt = None
        for i in range(len(arr) - 1, -1, -1):
            if arr[i] is None:
                arr[i] = nxt
            else:
                nxt = arr[i]
        filled.append(arr)
    out = []
    for i in idx:
        out.append((days[i], sum((a[i] or 0) for a in filled)))
    return out


# ── SVG (순수 문자열 — 외부 요청·폰트 임베드 없음, 토큰 색·viewBox 반응형) ──
def _yticks(lo, hi):
    rng = max(1, hi - lo)
    raw = rng / 3.0
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if raw <= m * mag)
    t = math.floor(lo / step) * step
    ticks = []
    while t <= hi + step * 1e-6:
        if t >= lo - step * 1e-6:
            ticks.append(int(round(t)))
        t += step
    return ticks


def svg_line(series, aria):
    """전국 잔여 합계 추이 라인차트 — 단일 파랑(--primary), 마지막 점 강조·값 라벨."""
    if len(series) < 2:
        return None
    W, H = 720, 250
    ml, mr, mt, mb = 64, 84, 16, 30
    xs = [d for d, _ in series]
    ys = [v for _, v in series]
    x0, x1 = xs[0], xs[-1]
    ylo, yhi = min(ys), max(ys)
    if ylo == yhi:
        ylo, yhi = ylo - 1, yhi + 1
    pad = (yhi - ylo) * 0.08
    lo2, hi2 = ylo - pad, yhi + pad
    X = lambda d: ml + (d - x0) / (x1 - x0) * (W - ml - mr)
    Y = lambda v: mt + (1 - (v - lo2) / (hi2 - lo2)) * (H - mt - mb)
    g = []
    for t in _yticks(ylo, yhi):
        y = Y(t)
        g.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="var(--line2)" stroke-width="1"/>' % (ml, W - mr, y, y))
        g.append('<text x="%d" y="%.1f" font-size="11" fill="var(--text3)" text-anchor="end">%s</text>' % (ml - 8, y + 4, pr.fmt(t)))
    for d in xs:
        if d != x0 and d != x1 and (d - x0) % 7 != 0:
            continue
        if d != x1 and x1 - d < 3:
            continue                          # 마지막 라벨과 겹침 방지
        dt = D0 + datetime.timedelta(days=d)
        g.append('<text x="%.1f" y="%d" font-size="11" fill="var(--text3)" text-anchor="middle">%d/%d</text>'
                 % (X(d), H - 8, dt.month, dt.day))
    path = 'M' + ' L'.join('%.1f,%.1f' % (X(d), Y(v)) for d, v in series)
    lx, ly = X(x1), Y(ys[-1])
    g.append('<path d="%s" fill="none" stroke="var(--primary)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>' % path)
    g.append('<circle cx="%.1f" cy="%.1f" r="3.5" fill="var(--primary)"/>' % (lx, ly))
    g.append('<text x="%.1f" y="%.1f" font-size="12" font-weight="700" fill="var(--text)">%s대</text>'
             % (lx + 8, ly + 4, pr.fmt(ys[-1])))
    return ('<svg viewBox="0 0 %d %d" style="width:100%%;height:auto" role="img" aria-label="%s" '
            'xmlns="http://www.w3.org/2000/svg">%s</svg>' % (W, H, pr.esc(aria), ''.join(g)))


def svg_bars(rows, aria):
    """전일 대비 감소 상위 가로 바차트 — 단일 초록(--money), 지역명·감소량 라벨."""
    if not rows:
        return None
    lw, mt, rh, W = 132, 8, 30, 720
    H = mt + rh * len(rows) + 8
    mx = max(d for _, d in rows)
    avail = W - lw - 92
    g = []
    for i, (name, drop) in enumerate(rows):
        y = mt + i * rh
        bw = max(2.0, drop / mx * avail)
        g.append('<text x="%d" y="%.1f" font-size="12" fill="var(--text2)" text-anchor="end">%s</text>'
                 % (lw - 10, y + 19.0, pr.esc(name)))
        g.append('<rect x="%d" y="%.1f" width="%.1f" height="14" rx="3" fill="var(--money)"/>' % (lw, y + 8.0, bw))
        g.append('<text x="%.1f" y="%.1f" font-size="12" font-weight="700" fill="var(--text)">−%s대</text>'
                 % (lw + bw + 8, y + 19.0, pr.fmt(drop)))
    return ('<svg viewBox="0 0 %d %d" style="width:100%%;height:auto" role="img" aria-label="%s" '
            'xmlns="http://www.w3.org/2000/svg">%s</svg>' % (W, H, pr.esc(aria), ''.join(g)))


# ── 본문 조립 ────────────────────────────────────────────
# ── 공고 변경 타임라인 ────────────────────────────────────
# 자체 1차 관측 데이터(rounds.json events = 공단 시스템 등록값 변경 기록)로 만드는 섹션.
# 외부 기사·타 사이트 콘텐츠를 일절 쓰지 않는다 — 시장 동향을 우리만 가진 데이터로 서술한다.
def _kmd(iso):
    """'2026-08-28' → '8월 28일'"""
    try:
        d = datetime.date.fromisoformat(iso[:10])
        return '%d월 %d일' % (d.month, d.day)
    except (TypeError, ValueError):
        return iso or ''


def _round_kind(item, before, after):
    """변경 유형 분류 → (라벨, 정렬 우선순위, 설명 조사용 동사)"""
    is_start = '접수시작' in (item or '')
    if not before:
        return ('신규 공고', 0, '새로 등록됐습니다')
    if not after:
        return ('등록 취소', 1, '등록이 내려갔습니다')
    try:
        b = datetime.date.fromisoformat(before[:10])
        a = datetime.date.fromisoformat(after[:10])
    except ValueError:
        return ('일정 변경', 3, '바뀌었습니다')
    if a < b:
        d = (b - a).days
        return (('개시 앞당김' if is_start else '마감 앞당김'), 1,
                '%d일 앞당겨졌습니다' % d)
    if a > b:
        d = (a - b).days
        return (('개시 미룸' if is_start else '마감 연장'), 2,
                '%d일 늦춰졌습니다' % d)
    return ('일정 변경', 3, '바뀌었습니다')


def round_changes(rounds, regions, since_iso, until_iso):
    """[since, until] 구간에 감지된 공고 변경 → [dict] (없으면 빈 리스트).
    공고 변경은 지자체 업무시간(주로 09~15시)에 발생하는데 브리핑은 아침에 생성되므로,
    당일만 보면 거의 항상 비게 된다 → 직전 브리핑 이후 구간을 함께 본다.
    같은 지역·항목이 구간 내 여러 번 바뀌면 순변화(첫 이전값 → 마지막 새값)로 합치고,
    번복으로 원위치한 건(순변화 0)은 실제로 바뀐 게 아니므로 제외 — 잡음 노출 방지."""
    groups = {}
    for cd, lst in ((rounds or {}).get('events') or {}).items():
        if cd not in regions:
            continue
        for row in lst:
            if not isinstance(row, list) or len(row) < 4:
                continue
            t, item, before, after = row[0], row[1], row[2], row[3]
            if not t or not (since_iso <= t[:10] <= until_iso):
                continue
            groups.setdefault((cd, item or ''), []).append((t, before, after))
    out = []
    for (cd, item), seq in groups.items():
        seq.sort(key=lambda x: x[0])
        before, after = seq[0][1], seq[-1][2]
        if (before or '') == (after or ''):
            continue                                  # 번복·원위치 — 순변화 없음
        label, rank, verb = _round_kind(item, before, after)
        out.append({'cd': cd, 'name': regions[cd]['name'], 'sido': regions[cd].get('sido', ''),
                    'time': seq[-1][0][5:16].replace('-', '/'), 'item': item,
                    'before': before, 'after': after,
                    'label': label, 'rank': rank, 'verb': verb,
                    'flips': len(seq) - 1})           # 중간 번복 횟수(0이면 단순 변경)
    out.sort(key=lambda e: (e['rank'], e['name'], e['item']))
    return out


def build_rounds_section(evs, since_iso, until_iso):
    """공고 변경 섹션 HTML. 이벤트 0건이면 '' (빈 섹션 생성 금지)"""
    if not evs:
        return '', ''
    span = ('%s 이후' % _kmd(since_iso)) if since_iso != until_iso else _kmd(until_iso)
    rows = []
    for e in evs[:14]:
        chg = ('<b>%s</b>' % pr.esc(e['after']) if not e['before']
               else '%s → <b>%s</b>' % (pr.esc(e['before']), pr.esc(e['after'])))
        if e.get('flips'):
            chg += ' <span class="small muted">(당일 %d회 정정)</span>' % e['flips']
        rows.append('<tr><td><a href="/region/%s.html" style="color:inherit;font-weight:700">%s</a>'
                    '<div class="small muted">%s</div></td>'
                    '<td class="small">%s</td><td class="small">%s</td>'
                    '<td class="small muted">%s</td></tr>'
                    % (e['cd'], pr.esc(e['name']), pr.esc(e['sido']),
                       pr.esc(e['item']), chg, e['time']))
    more = ('<p class="small muted mt8">이 밖에 %s건이 더 있습니다.</p>' % pr.fmt(len(evs) - 14)
            if len(evs) > 14 else '')
    # 한 줄 요약(집계 사실만 — 점추정·전망 금지)
    kinds = {}
    for e in evs:
        kinds[e['label']] = kinds.get(e['label'], 0) + 1
    kind_txt = ' · '.join('%s %s건' % (k, pr.fmt(v)) for k, v in
                          sorted(kinds.items(), key=lambda x: -x[1]))
    n_region = len({e['cd'] for e in evs})
    # 주의: %가 +보다 우선 결합하므로 헤더를 먼저 완성해 두고 이어붙인다(혼합하면 인자 수가 어긋남)
    head = ('<section class="card"><h2 class="mt0">📋 공고 일정 변경 '
            '<span class="sub">%s · %s개 지자체 · %s건</span></h2>'
            % (pr.esc(span), pr.fmt(n_region), pr.fmt(len(evs))))
    body = ('<p class="small muted" style="margin:0 0 10px">%s</p>'
            '<div class="tbl-wrap"><table class="tbl"><thead><tr>'
            '<th>지역</th><th>항목</th><th>변경</th><th>감지</th>'
            '</tr></thead><tbody>%s</tbody></table></div>%s'
            '<p class="small muted mt8">공고 일정은 지자체가 예고 없이 바꾸는 경우가 있어, '
            '이 표는 무공해차 통합누리집에 <b>등록된 값이 바뀐 시점</b>을 매시간 수집해 기록한 것입니다. '
            '공고문 원문과 다를 수 있으니 신청 전에는 해당 지자체 공고문을 확인하세요.</p></section>'
            % (pr.esc(kind_txt), ''.join(rows), more))
    html = head + body
    # 헤드라인에 얹을 문장(가장 큰 변화 1건)
    top = evs[0]
    lead = ('공고 일정도 움직였습니다 — %s의 %s이 %s(%s개 지자체에서 %s건 감지).'
            % (top['name'], top['item'], top['verb'], pr.fmt(n_region), pr.fmt(len(evs))))
    return html, lead


def build_page(target, status, rounds, regions, hist, meta, state, tpl_brief, tpl_page):
    """페이지 HTML과 발행 판정을 함께 반환. (html, movers_summary) — html이 None이면 스킵."""
    date_iso = target.isoformat()
    tday = (target - D0).days
    updated = status.get('updated', '')
    up_label = updated.replace('T', ' ')
    P = lambda slot, opts: pr.pick('%s:%s' % (date_iso, slot), opts)
    C = lambda slot, *parts: pr.compose(date_iso, slot, *parts)

    closed_map = {cd: pr.detect_closed((status['data'].get(cd) or {}).get('note')) for cd in regions}

    prev_regions, prev_meta = prev_basis(state, date_iso)
    basis = 'snapshot'
    if prev_regions is None:
        prev_regions = history_prev(hist, regions, tday)
        basis = 'history'
    if prev_regions is None:
        return None, 'SKIP 전일 기준값 없음(스냅샷·이력 모두 부재) — 다음 실행부터 비교 가능'

    # 비교 기준일 라벨 — 기준이 실제 '어제'가 아니면(수집 공백 뒤 복구 등) 날짜를 명시해 '전일' 오표기 방지
    basis_day = ((prev_meta or {}).get('updated') or (prev_meta or {}).get('date') or '')[:10]
    if basis_day == (target - datetime.timedelta(days=1)).isoformat():
        vs = '전일'
    elif basis_day:
        _bd = datetime.date.fromisoformat(basis_day)
        vs = '%d월 %d일' % (_bd.month, _bd.day)
    else:
        vs = '직전 관측'

    # ── 지역별 전일 대비 ──
    dup = {}
    for cd, r in regions.items():
        dup[r['name']] = dup.get(r['name'], 0) + 1
    movers, cur_total, paired_prev, paired_cur = [], 0, 0, 0
    for cd, r in regions.items():
        if cd == '9999':
            continue
        st = status['data'].get(cd) or {}
        cur = st.get('left')
        if cur is not None:
            cur_total += cur
        pl = (prev_regions.get(cd) or {}).get('left')
        delta = (cur - pl) if (cur is not None and pl is not None) else None
        if delta is not None:
            paired_prev += pl
            paired_cur += cur
        label = r['name'] if dup.get(r['name'], 0) <= 1 else '%s %s' % (r.get('sido', ''), r['name'])
        movers.append({'cd': cd, 'name': r['name'], 'label': label, 'sido': r.get('sido', ''),
                       'cur': cur, 'prev': pl, 'delta': delta, 'n': st.get('n'),
                       'closed': closed_map[cd]['closed'], 'cinfo': closed_map[cd],
                       'pclosed': (prev_regions.get(cd) or {}).get('c')})
    decreases = sorted((m for m in movers if m['delta'] is not None and m['delta'] < 0),
                       key=lambda m: (m['delta'], m['cd']))
    increases = sorted((m for m in movers if m['delta'] is not None and m['delta'] > 0),
                       key=lambda m: (-m['delta'], m['cd']))
    resets = [m for m in increases
              if m['delta'] >= max(RESET_MIN, math.ceil(RESET_PCT * (m['n'] or m['prev'] or 1)))
              or recent_reset(hist, m['cd'], tday)]
    newly_closed = [m for m in movers if m['closed'] and m['pclosed'] == 0]
    net = paired_cur - paired_prev
    total_drop = sum(-m['delta'] for m in decreases)
    total_gain = sum(m['delta'] for m in increases)
    changed = sum(1 for m in movers if m['delta'])
    open_cnt = sum(1 for m in movers if (m['cur'] or 0) > 0 and not m['closed'])

    # 공고 변경(자체 관측) — 잔여가 그대로여도 일정이 바뀌면 발행할 가치가 있다.
    # 창은 직전 브리핑 기준일~오늘(업무시간에 발생하는 변경을 놓치지 않도록), 최대 7일로 제한.
    _since = max(basis_day or '', (target - datetime.timedelta(days=7)).isoformat()) \
        or (target - datetime.timedelta(days=1)).isoformat()
    round_evs = round_changes(rounds, regions, _since, date_iso)
    rounds_html, rounds_lead = build_rounds_section(round_evs, _since, date_iso)

    if changed == 0 and not newly_closed and not resets and not round_evs:
        return None, 'SKIP 변화 없음(잔여 변동 0·이벤트 0·공고 변경 0)'

    quiet = total_drop <= max(30, cur_total // 1000) and not newly_closed and not resets
    series = national_series(hist, regions, tday)

    # ── 헤드라인 (3~5문장) ──
    kd = kdate(target)
    hs = []
    if net < 0:
        net_txt = ['%s 같은 시각 대비 %s대 줄었습니다.' % (vs, pr.fmt(-net)),
                   '%s 대비 %s대가 줄어든 수치입니다.' % (vs, pr.fmt(-net)),
                   '%s 수집분보다 %s대 감소했습니다.' % (vs, pr.fmt(-net))]
    elif net > 0:
        net_txt = ['%s 같은 시각 대비 %s대 늘었습니다(추가 공고·취소 환입 등).' % (vs, pr.fmt(net)),
                   '%s 대비 %s대가 늘어난 수치입니다(추가 공고·취소 환입 등).' % (vs, pr.fmt(net))]
    else:
        net_txt = ['%s 합계와 같은 수준이지만 지역별로는 증감이 엇갈렸습니다.' % vs,
                   '합계는 %s과 같아도 지역 단위로는 이동이 있었습니다.' % vs]
    hs.append(C('h-total',
                ['%s 아침 집계 기준, ' % kd, '%s 기준으로 보면, ' % kd, '%s 수집분 기준, ' % kd],
                ['전국 160개 지자체의 전기승용 잔여 물량 합계는 %s대입니다. ' % pr.fmt(cur_total),
                 '전국(160개 지자체) 전기승용 잔여 합계는 %s대로 집계됐습니다. ' % pr.fmt(cur_total),
                 '전기승용 잔여 물량은 전국을 합쳐 %s대입니다. ' % pr.fmt(cur_total)],
                net_txt))
    if decreases:
        t = decreases[0]
        hs.append(C('h-top',
                    ['하루 새 가장 많이 줄어든 곳은 ', '감소 폭이 가장 컸던 지역은 ', '가장 크게 움직인 곳은 '],
                    ['%s로, %s대에서 %s대로 %s대가 줄었습니다.'
                     % (pr.esc(t['label']), pr.fmt(t['prev']), pr.fmt(t['cur']), pr.fmt(-t['delta'])),
                     '%s입니다 — %s대 감소(%s대→%s대)였습니다.'
                     % (pr.esc(t['label']), pr.fmt(-t['delta']), pr.fmt(t['prev']), pr.fmt(t['cur']))]))
    elif increases:
        t = increases[0]
        hs.append('감소한 지역은 없었고, %s의 잔여가 %s대에서 %s대로 %s대 늘어난 변화가 가장 컸습니다.'
                  % (pr.esc(t['label']), pr.fmt(t['prev']), pr.fmt(t['cur']), pr.fmt(t['delta'])))
    if newly_closed:
        names = '·'.join(pr.esc(m['label']) for m in newly_closed[:3])
        more = ' 외 %s곳' % pr.fmt(len(newly_closed) - 3) if len(newly_closed) > 3 else ''
        hs.append(P('h-closed',
                    ['%s%s에서 새로 접수 마감 공지가 확인됐습니다.' % (names, more),
                     '새로 마감이 공지된 지역은 %s%s입니다.' % (names, more)]))
    if resets:
        names = '·'.join(pr.esc(m['label']) for m in resets[:3])
        more = ' 외 %s곳' % pr.fmt(len(resets) - 3) if len(resets) > 3 else ''
        hs.append(P('h-reset',
                    ['%s%s에서는 잔여가 크게 늘어 추가 공고·회차 갱신 가능성이 있습니다(공고문 확인 필요).' % (names, more),
                     '%s%s은(는) 잔여가 크게 늘었습니다 — 추가 공고 여부를 공고문으로 확인할 지역입니다.' % (names, more)]))
    hs.append(C('h-open',
                ['현재 ', '이 시점 기준 ', '오늘 집계에서 '],
                ['잔여가 남아 있고 마감 공지가 없는 지역은 %s곳입니다.' % pr.fmt(open_cnt),
                 '마감 공지 없이 잔여가 남은 지역 수는 %s곳으로 집계됩니다.' % pr.fmt(open_cnt)]))
    if rounds_lead:
        hs.append(rounds_lead)                      # 공고 일정 변화도 요약에 반영
    headline = '<p style="line-height:1.8;margin:10px 0">%s</p>' % ' '.join(hs[:6])

    # ── 차트 ──
    # 비교 기준 라벨은 stamp·바이라인과 동일한 것을 차트 부제에도 사용(폴백일 자기모순 방지)
    basis_label = ('%s 스냅샷(%s 수집) 대비' % (vs, (prev_meta or {}).get('updated', '').replace('T', ' ').strip())
                   if basis == 'snapshot' and (prev_meta or {}).get('updated')
                   else '%s 일별 이력(마지막 관측값) 대비' % vs)
    c1sub = c2sub = ''
    if series:
        span = series[-1][0] - series[0][0] + 1
        c1 = svg_line(series, '전국 잔여 합계 최근 %d일 추이, 최근 값 %s대' % (span, pr.fmt(series[-1][1])))
        c1sub = '최근 %d일 · 160개 지자체 합계 · %s 기준' % (span, up_label)
    else:
        c1 = None
    chart1 = c1 or '<p class="muted small">추이 이력이 아직 충분히 쌓이지 않아 차트를 생략합니다.</p>'
    top10 = decreases[:10]
    c2 = svg_bars([(m['label'], -m['delta']) for m in top10],
                  '%s 대비 잔여 감소 상위 %d개 지역 가로 막대 차트' % (vs, len(top10))) if top10 else None
    c2sub = '%s · %s 기준' % (basis_label, up_label)
    chart2 = c2 or '<p class="muted small">%s 대비 잔여가 줄어든 지역이 없었습니다.</p>' % vs

    # 감소 상위 표
    table = ''
    if top10:
        trs = ''.join('<tr><td><a href="/region/%s.html" style="color:inherit;font-weight:700">%s</a>'
                      '<span class="small muted"> %s</span></td>'
                      '<td class="num">%s</td><td class="num">%s</td>'
                      '<td class="num" style="font-weight:800;color:var(--money)">−%s</td></tr>'
                      % (m['cd'], pr.esc(m['name']), pr.esc(m['sido']),
                         pr.fmt(m['prev']), pr.fmt(m['cur']), pr.fmt(-m['delta']))
                      for m in top10)
        table = ('<div class="tbl-wrap"><table class="tbl">'
                 '<thead><tr><th>지역</th><th class="num">%s 잔여</th><th class="num">오늘 잔여</th>'
                 '<th class="num">감소</th></tr></thead><tbody>%s</tbody></table></div>'
                 '<p class="small muted mt8">잔여 감소는 대부분 출고 진행에 따른 차감입니다. '
                 '접수 가능 여부는 별개이니 각 지역 페이지의 공지를 확인하세요.</p>' % (vs, trs))

    # ── 이벤트 섹션 (신규 마감·물량 증가) ──
    ev_html = []
    if newly_closed:
        rows = ''.join('<a class="row" href="/region/%s.html"><div class="grow"><div class="tit">%s</div>'
                       '<div class="desc">공지상 접수 마감%s · 잔여 표기 %s대는 미출고분일 수 있음</div></div></a>'
                       % (m['cd'], pr.esc(m['label']),
                          ' (%s)' % pr.esc(m['cinfo'].get('closedDate')) if m['cinfo'].get('closedDate') else '',
                          pr.fmt(m['cur']))
                       for m in newly_closed[:8])
        ev_html.append('<section class="card"><h2 class="mt0">신규 마감 공지 <span class="sub">%s곳 · %s 스냅샷과 비교해 새로 감지</span></h2>'
                       '<div class="rowlist">%s</div></section>' % (pr.fmt(len(newly_closed)), vs, rows))
    if resets:
        rows = ''.join('<a class="row" href="/region/%s.html"><div class="grow"><div class="tit">%s</div>'
                       '<div class="desc">잔여 %s대 → %s대 (+%s대) · 추가 공고·회차 갱신 가능성 — 공고문 확인</div></div></a>'
                       % (m['cd'], pr.esc(m['label']), pr.fmt(m['prev']), pr.fmt(m['cur']), pr.fmt(m['delta']))
                       for m in resets[:8])
        ev_html.append('<section class="card"><h2 class="mt0">물량 증가 감지 <span class="sub">%s곳 · 잔여가 크게 늘어난 지역</span></h2>'
                       '<div class="rowlist">%s</div></section>' % (pr.fmt(len(resets)), rows))
    events = '\n'.join(ev_html)

    # ── 해설 2~3문단 (조건 분기 + 문장 풀) ──
    paras = []
    if quiet:
        paras.append(C('p1q',
            ['오늘은 전국적으로 변동 폭이 작은 조용한 하루였습니다. ',
             '전국 단위로 보면 오늘은 움직임이 잔잔한 편이었습니다. ',
             '수치만 보면 오늘은 큰 사건이 없는 하루였습니다. '],
            ['잔여가 줄어든 지역은 %s곳, 줄어든 대수를 모두 합해도 %s대입니다. '
             % (pr.fmt(len(decreases)), pr.fmt(total_drop)),
             '감소 지역 %s곳의 감소분 합계가 %s대에 그쳤습니다. '
             % (pr.fmt(len(decreases)), pr.fmt(total_drop))],
            ['이런 날은 순위 변동보다 내 지역 공고문·서류 준비를 점검하기 좋은 날입니다.',
             '변화가 작다고 접수 여건이 그대로라는 뜻은 아니니, 신청 직전에는 잔여를 다시 확인하세요.',
             '큰 변화가 없는 날에도 지자체 공지는 갱신될 수 있으니 내 지역 페이지를 한 번 확인해 두세요.']))
    else:
        top3 = '·'.join('%s(−%s대)' % (pr.esc(m['label']), pr.fmt(-m['delta'])) for m in decreases[:3])
        paras.append(C('p1',
            ['이번 집계에서 잔여가 줄어든 지역은 %s곳이고, 감소분 합계는 %s대입니다. '
             % (pr.fmt(len(decreases)), pr.fmt(total_drop)),
             '오늘 집계에서 감소가 확인된 지역은 %s곳, 합계 %s대가 줄었습니다. '
             % (pr.fmt(len(decreases)), pr.fmt(total_drop)),
             '%s 대비 감소 지역은 %s곳으로 집계됐고 합계 감소분은 %s대입니다. '
             % (vs, pr.fmt(len(decreases)), pr.fmt(total_drop))],
            (['감소 상위는 %s 순이었습니다. ' % top3,
              '많이 줄어든 곳부터 보면 %s입니다. ' % top3] if top3 else ['']),
            ['잔여 감소는 대부분 앞서 접수된 차량이 출고되며 차감되는 수치라, 오늘 줄어든 만큼 오늘 새 신청이 몰렸다는 뜻은 아닙니다.',
             '이 감소분의 다수는 이미 접수된 물량의 출고 차감이므로, 신규 신청 가능 물량과는 구분해 읽어야 합니다.',
             '감소분은 주로 출고 단계에서 차감된 것이어서, 접수 창구 상황은 지역 페이지의 공지로 따로 확인해야 합니다.']))
        if total_gain > 0 and not resets:
            paras.append(C('p1g',
                ['한편 잔여가 소폭 늘어난 지역도 %s곳(%s대) 있었습니다. ' % (pr.fmt(len(increases)), pr.fmt(total_gain)),
                 '반대로 %s곳에서는 잔여가 합계 %s대 늘었습니다. ' % (pr.fmt(len(increases)), pr.fmt(total_gain))],
                ['소폭 증가는 접수 취소분 환입이 흔한 원인이라, 추가 공고로 단정하기는 이릅니다.',
                 '이 정도 증가는 취소 환입일 가능성이 높아 추가 공고 신호로 확대해석하지 않는 편이 좋습니다.']))
    if newly_closed or resets:
        seg = []
        if newly_closed:
            seg.append(P('p2c', ['오늘 새로 마감이 공지된 %s곳은 공지 원문에 완료형 마감 선언이 있는 경우만 집계한 것입니다'
                                 % pr.fmt(len(newly_closed)),
                                 '신규 마감 %s곳은 "예산 소진 시 조기 마감" 같은 조건부 예고가 아니라 완료형 마감 공지가 확인된 지역만 담았습니다'
                                 % pr.fmt(len(newly_closed))]))
        if resets:
            seg.append(P('p2r', ['잔여가 크게 늘어난 %s곳은 추가 공고나 회차 갱신의 신호일 수 있으나, 확정은 지자체 공고문으로만 가능합니다'
                                 % pr.fmt(len(resets)),
                                 '물량 증가가 감지된 %s곳은 재공고 가능성이 있는 지역이지만 공고문 확인 전에는 단정하지 않습니다'
                                 % pr.fmt(len(resets))]))
        paras.append(C('p2',
            ['이벤트를 해석할 때 한 가지 기준이 있습니다. ', '마감·증가 신호는 보수적으로 읽습니다. '],
            ['. '.join(seg) + '. '],
            ['마감으로 표시돼도 일부 유형(우선순위·법인 등) 칸에는 물량이 남는 경우가 있고, 유형별 칸 합계가 전체와 다른 지역(회차 이월)도 있으니 원문 확인이 우선입니다.',
             '마감 공지가 있어도 유형별 칸에 물량이 남거나, 유형 합계와 전체가 다른 지역(회차 이월)이 있어 최종 판단은 공고 원문 기준입니다.']))
    if series and len(series) >= 2:
        s0, s1 = series[0], series[-1]
        obs = len(series)
        diff = s0[1] - s1[1]
        span = s1[0] - s0[0]
        if diff > 0 and span > 0:
            trend_tail = ['일평균 약 %s대꼴로 줄어든 과거 실측이며, 앞으로의 속도를 보장하는 수치는 아닙니다.' % pr.fmt(round(diff / span)),
                          '하루 평균으로 나누면 약 %s대씩 줄어든 셈인데, 이는 지나간 기간의 실측일 뿐 미래 예측이 아닙니다.' % pr.fmt(round(diff / span))]
            trend_mid = ['전국 잔여 합계는 %s대에서 %s대로 %s대 줄었습니다. ' % (pr.fmt(s0[1]), pr.fmt(s1[1]), pr.fmt(diff)),
                         '합계 기준 %s대였던 전국 잔여가 %s대까지 %s대 감소했습니다. ' % (pr.fmt(s0[1]), pr.fmt(s1[1]), pr.fmt(diff))]
        else:
            trend_mid = ['전국 잔여 합계는 %s대에서 %s대로 큰 감소 없이 유지됐습니다(추가 공고 반영 포함). ' % (pr.fmt(s0[1]), pr.fmt(s1[1]))]
            trend_tail = ['잔여가 유지되거나 늘어나는 구간은 추가 공고가 반영되는 시기라는 뜻이기도 합니다.',
                          '이 구간의 정체·증가는 추가 공고 물량이 더해진 영향일 수 있습니다.']
        paras.append(C('p3',
            ['조금 길게 보면, 최근 %s일 관측(%s개 시점)에서 ' % (pr.fmt(span + 1), pr.fmt(obs)),
             '최근 %s일(관측 %s회) 흐름으로는 ' % (pr.fmt(span + 1), pr.fmt(obs))],
            trend_mid, trend_tail))
    prose = ''.join('<p style="line-height:1.8;margin:10px 0">%s</p>' % p for p in paras[:3])

    # ── 공개·바이라인 ── (basis_label은 차트 섹션에서 계산)
    disclosure = (
        '<p style="line-height:1.8;margin:10px 0">이 페이지는 무공해차 통합누리집(ev.or.kr)에서 매시간 수집한 '
        '공고 데이터를 바탕으로 매일 1회(원칙적으로 아침) 발행하는 브리핑입니다. 수치 집계는 자동화 파이프라인이 수행하고, 집계 방법 설계와 문안 검수는 운영자(HyeongHun Lee)가 관리합니다. 외부 기사를 재작성하지 않으며, '
        '본문·차트의 수치는 전부 수집 시점의 실측값입니다. 변화가 없거나 데이터가 오래된 날에는 발행을 건너뜁니다.</p>'
        '<p style="line-height:1.8;margin:10px 0">집계 방법: 수치는 매시간 수집분 가운데 브리핑 생성 직전 값을 쓰고, '
        '증감은 직전 보관 스냅샷(수집 공백이 있으면 그 이전 마지막 관측값 — 본문에 기준일 명시)과 비교합니다. '
        '마감은 지자체 공지 원문에 완료형 마감 선언이 있을 때만 인정하고, "예산 소진 시 조기 마감" 같은 '
        '조건부 예고는 마감으로 세지 않습니다. 물량 증가는 공고 물량 대비 5%% 이상(최소 10대) 늘어난 경우에 감지합니다.</p>'
        '<p style="line-height:1.8;margin:10px 0">잔여 수치는 출고 시점에 차감하는 지역이 많아 실제 접수는 '
        '더 일찍 마감될 수 있고, 잔여가 남아 있어도 유형·요건에 따라 신청이 어려울 수 있습니다. '
        '신청 전에는 반드시 관할 지자체 공고문을 확인하세요.</p>'
        '<p class="stamp">데이터·생성: EV보조금 자동 브리핑 · 편집 책임: HyeongHun Lee · 기준시각 %s · 비교 기준: %s</p>'
        % (pr.esc(up_label), pr.esc(basis_label)))
    related = (
        '<a class="chip" href="status.html">🗺 전국 현황판</a>'
        '<a class="chip" href="brief/">📅 지난 브리핑 목록</a>'
        '<a class="chip" href="quota-reading.html">📖 잔여 대수 읽는 법</a>'
        '<a class="chip" href="articles.html">📚 읽을거리 전체</a>')

    # ── 렌더 ──
    mapping = {
        'H1': '%s <span class="hl">보조금 브리핑</span>' % kd,
        'SUB': '전국 잔여 %s대 · %s 대비 %s%s대 · 실측 데이터 브리핑'
               % (pr.fmt(cur_total), vs, '+' if net > 0 else ('−' if net < 0 else '±'), pr.fmt(abs(net))),
        'STAMP': '기준시각 %s · %s · 출처 무공해차 통합누리집(ev.or.kr)' % (pr.esc(up_label), pr.esc(basis_label)),
        'HEADLINE': headline,
        'C1SUB': pr.esc(c1sub), 'CHART1': chart1,
        'C2SUB': pr.esc(c2sub), 'CHART2': chart2,
        'TABLE': table, 'EVENTS': events, 'ROUNDS': rounds_html, 'PROSE': prose,
        'DISCLOSURE': disclosure, 'RELATED': related, 'AD1': '',
    }
    gate = len(pr.strip_tags(re.sub(r'<svg.*?</svg>', ' ', pr.render(tpl_brief, mapping), flags=re.S)))
    # 브리핑은 noindex 자동 집계 페이지 — 광고 슬롯 미생성(I4·'자동 생성 콘텐츠에 광고' 정책 회피)
    mapping['AD1'] = pr.ad_slot('brief-1', gate, True)
    main = pr.render(tpl_brief, mapping)

    canonical = '%s/brief/%s.html' % (BASE, date_iso)
    desc = ('%s 전기차 보조금 브리핑: 전국 잔여 %s대(%s 대비 %s%s대)%s%s%s. ev.or.kr 실측 데이터 기준.'
            % (kd, pr.fmt(cur_total), vs, '+' if net > 0 else '−' if net < 0 else '±', pr.fmt(abs(net)),
               ', 최대 감소 %s −%s대' % (decreases[0]['label'], pr.fmt(-decreases[0]['delta'])) if decreases else '',
               ', 신규 마감 %s곳' % pr.fmt(len(newly_closed)) if newly_closed else '',
               ', 물량 증가 %s곳' % pr.fmt(len(resets)) if resets else ''))
    title = '전기차 보조금 일일 브리핑 %s — 전국 잔여 %s대 | EV보조금' % (date_iso, pr.fmt(cur_total))
    ld = [{'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': '홈', 'item': BASE + '/'},
        {'@type': 'ListItem', 'position': 2, 'name': '일일 브리핑', 'item': BASE + '/brief/'},
        {'@type': 'ListItem', 'position': 3, 'name': '%s 브리핑' % kd, 'item': canonical}]},
        {'@context': 'https://schema.org', '@type': 'Article',
         'headline': '전기차 보조금 일일 브리핑 %s' % date_iso,
         'datePublished': date_iso, 'dateModified': date_iso, 'inLanguage': 'ko',
         'author': {'@type': 'Person', 'name': 'HyeongHun Lee', 'url': BASE + '/about.html#operator'},
         'publisher': {'@type': 'Organization', 'name': 'EV보조금'},
         'mainEntityOfPage': canonical,
         'description': '무공해차 통합누리집(ev.or.kr) 수집 데이터 기반 일일 브리핑 — 집계 자동화·검수 운영자'}]
    page = pr.render(tpl_page, {
        'TITLE': pr.esc(title),
        'DESC': pr.esc(desc),
        # 자동 집계 페이지 — 색인 제외(발행·홈 배너 노출은 유지). 심사·검색 표면에는 편집 콘텐츠만 올린다.
        'ROBOTS': '\n<meta name="robots" content="noindex">',
        'CANONICAL': canonical,
        'JSONLD': pr.jsonld_script(ld),
        'BREADCRUMB': '<a href="/">홈</a> › <a href="/brief/">일일 브리핑</a> › <b>%s</b>' % date_iso,
        'MAIN': main,
        'META_UPDATED': pr.esc(meta['updated']),
    })

    # ── 품질 가드 (발행 전 자체 검증 — 실패 시 예외로 빌드 중단) ──
    text = pr.strip_tags(re.sub(r'<svg.*?</svg>', ' ', main, flags=re.S))
    if len(text) < 1200:
        raise RuntimeError('정적 텍스트 %d자 < 1,200자' % len(text))
    n_sent = len(re.findall(r'다\.', text))
    if n_sent < 12:
        raise RuntimeError('완전한 문장 %d개 < 12개' % n_sent)
    for w in BANNED:
        if w in text:
            raise RuntimeError('금칙어 검출: %r' % w)
    for p in re.findall(r'<p[^>]*>(.*?)</p>', main, flags=re.S):
        if pr.strip_tags(p).count('전기차 보조금') > 1:
            raise RuntimeError("'전기차 보조금' 문단 내 2회 이상")
    for svg in re.findall(r'<svg.*?</svg>', main, flags=re.S):
        ET.fromstring(svg)                       # SVG 유효성(XML 파서)
        if 'http://' in svg.replace('http://www.w3.org/2000/svg', '') or 'https://' in svg:
            raise RuntimeError('SVG에 외부 URL 포함')

    # 이력 폴백일에는 전일 마감 상태(c)가 없어 신규마감 감지가 불가 — 0이 아니라 N/A로 정직하게 표기
    nc_txt = 'N/A(이력 폴백 — 비교 불가)' if basis == 'history' else pr.fmt(len(newly_closed))
    summary = ('OK 전국 %s대(전일 %+d) · 감소 %s곳(−%s) · 신규마감 %s · 리셋 %s · %s'
               % (pr.fmt(cur_total), net, pr.fmt(len(decreases)), pr.fmt(total_drop),
                  nc_txt, pr.fmt(len(resets)), basis))
    return page, summary


def make_state(target_iso, status, regions, old_state):
    """오늘 관측값으로 스냅샷 회전. 같은 날 재실행이면 prev를 보존해 멱등 유지."""
    snap = {}
    for cd in regions:
        if cd == '9999':
            continue
        st = status['data'].get(cd) or {}
        snap[cd] = {'left': st.get('left'), 'nh': note_crc(st),
                    'c': 1 if pr.detect_closed(st.get('note')).get('closed') else 0}
    if old_state and old_state.get('v') == 1 and old_state.get('date') == target_iso:
        prev = old_state.get('prev')             # 같은 날 재실행: 전일분 유지
    elif old_state and old_state.get('v') == 1:
        prev = {'date': old_state.get('date'), 'updated': old_state.get('updated'),
                'regions': old_state.get('regions')}
    else:
        prev = None
    return {'v': 1, 'date': target_iso, 'updated': status.get('updated'),
            'regions': snap, 'prev': prev}


def write_json(path, obj):
    tmp = path + '.tmp~'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description='EV보조금 일간 브리핑 생성')
    ap.add_argument('--force', action='store_true', help='이미 존재해도 재생성')
    ap.add_argument('--date', help='대상 날짜 YYYY-MM-DD (기본: KST 오늘)')
    ap.add_argument('--data-dir', default=os.path.join(ROOT, 'site', 'data'))
    ap.add_argument('--out-dir', default=os.path.join(ROOT, 'site', 'brief'))
    ap.add_argument('--state-file', default=os.path.join(HERE, '.brief_prev.json'))
    a = ap.parse_args()

    target = (datetime.date.fromisoformat(a.date) if a.date
              else datetime.datetime.now(KST).date())
    date_iso = target.isoformat()
    out_path = os.path.join(a.out_dir, date_iso + '.html')

    status = rj(os.path.join(a.data_dir, 'status.json'))
    regions = rj(os.path.join(a.data_dir, 'regions.json'))
    meta = rj(os.path.join(a.data_dir, 'meta.json'))
    try:
        hist = rj(os.path.join(a.data_dir, 'history.json'))
    except Exception:
        hist = None
    try:
        rounds = rj(os.path.join(a.data_dir, 'rounds.json'))   # 공고 차수·변경이력(없어도 발행)
    except Exception:
        rounds = None

    # stale 가드: 수집 시각이 24시간 이상 지났으면 발행하지 않음(스냅샷도 회전 안 함)
    try:
        up = datetime.datetime.fromisoformat(status.get('updated', ''))
        age_h = (datetime.datetime.now(KST) - up).total_seconds() / 3600
    except ValueError:
        print('brief SKIP: status.json updated 파싱 실패(%r)' % status.get('updated'))
        return 0
    if age_h >= STALE_HOURS:
        print('brief SKIP: status.json stale (%.1fh 경과, 기준 %dh)' % (age_h, STALE_HOURS))
        return 0

    if os.path.exists(out_path) and not a.force:
        print('brief SKIP: 이미 존재 %s (--force로 재생성)' % out_path)
        return 0

    try:
        state = rj(a.state_file)
    except Exception:
        state = None

    tpl_brief = pr.load_tpl('brief.tpl')
    tpl_page = pr.load_tpl('page.tpl')
    page, summary = build_page(target, status, rounds, regions, hist, meta, state, tpl_brief, tpl_page)
    if page is None:
        write_json(a.state_file, make_state(date_iso, status, regions, state))   # 스킵도 스냅샷 회전
        print('brief SKIP: %s' % summary[5:] if summary.startswith('SKIP ') else 'brief SKIP: %s' % summary)
        return 0

    pr.atomic_write(out_path, page)
    write_json(a.state_file, make_state(date_iso, status, regions, state))
    print('brief %s → %s' % (summary, out_path))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print('brief FAIL: %s — 기존 파일 유지' % e, file=sys.stderr)
        sys.exit(1)
