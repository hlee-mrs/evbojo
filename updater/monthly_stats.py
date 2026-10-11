#!/usr/bin/python3
"""월간 리포트용 실측 집계 — history.json(일별 잔여)·rounds.json(회차)·regions.json·status.json.

해설 글 '월간 리포트'(updater/content/articles/monthly-YYYY-MM.md)의 수치는 이 스크립트 출력에서 옮긴다.
- 점추정·예측 없음: 관측된 양끝(월초 직전 관측일 ↔ 월말 관측일)의 차이와 이벤트 건수만 센다(I3).
- stdlib 전용, 읽기 전용(어떤 파일도 쓰지 않음). launchd 무관 — 사람이 원고 쓸 때 수동 실행.

사용:  /usr/bin/python3 updater/monthly_stats.py            # 지난달
       /usr/bin/python3 updater/monthly_stats.py --month 2026-09
       /usr/bin/python3 updater/monthly_stats.py --month 2026-09 --md   # 원고에 붙일 Markdown 불릿
"""
import argparse
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'site', 'data')


def load(name):
    with open(os.path.join(DATA, name), encoding='utf-8') as f:
        return json.load(f)


def month_range(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    first = dt.date(y, m, 1)
    last = (dt.date(y + (m == 12), (m % 12) + 1, 1) - dt.timedelta(days=1))
    return first, last


def compute(ym):
    hist, rounds = load('history.json'), load('rounds.json').get('rounds') or {}
    regions = {k: v for k, v in load('regions.json').items() if k != '9999'}
    status = load('status.json')
    d0 = dt.date.fromisoformat(hist['d0'])
    days = hist['days']
    first, last = month_range(ym)

    def day(i):
        return d0 + dt.timedelta(days=i)

    def idx(date):                       # 해당 날짜 또는 그 직전 관측일의 인덱스(없으면 None)
        target = (date - d0).days
        cands = [i for i, d in enumerate(days) if d <= target]
        return cands[-1] if cands else None

    i1, i2 = idx(first), idx(last)
    out = {'month': ym, 'status_updated': status.get('updated'),
           'obs_start': day(days[i1]).isoformat() if i1 is not None else None,
           'obs_end': day(days[i2]).isoformat() if i2 is not None else None}
    if i1 is None or i2 is None or i1 == i2:
        out['error'] = '이 달의 양끝 관측일이 없습니다(이력 범위: %s ~ %s)' % (day(days[0]), day(days[-1]))
        return out
    tot1 = tot2 = zero1 = zero2 = n_with = 0
    deltas, resets = [], []
    reopen = sold = 0
    for cd, r in regions.items():
        e = hist['r'].get(cd)
        if not e:
            continue
        l1, l2 = e['l'][i1], e['l'][i2]
        if l1 is None or l2 is None:
            continue
        n_with += 1
        tot1 += l1
        tot2 += l2
        zero1 += (l1 == 0)
        zero2 += (l2 == 0)
        deltas.append((l2 - l1, r['name'], cd, l1, l2))
        for ev in (e.get('L') or {}).get('ev') or []:
            if ev[1] == 0 and first <= day(ev[0]) <= last:      # 타입 0 = 추가공고(리셋) 이벤트
                resets.append({'region': r['name'], 'cd': cd, 'date': day(ev[0]).isoformat(),
                               'before': ev[2], 'after': ev[3]})
        seq = [e['l'][i] for i in range(i1, i2 + 1) if e['l'][i] is not None]
        if any(a == 0 and b > 0 for a, b in zip(seq, seq[1:])):
            reopen += 1
        if any(a > 0 and b == 0 for a, b in zip(seq, seq[1:])):
            sold += 1
    deltas.sort()
    starts, ends, start_list = 0, 0, []
    pfx = ym
    for cd, lst in rounds.items():
        if cd == '9999' or cd not in regions:
            continue
        for x in lst:
            s, e = (x.get('s') or '')[:10], (x.get('e') or '')[:10]
            if s.startswith(pfx):
                starts += 1
                start_list.append({'region': regions[cd]['name'], 'round': x.get('k'), 'start': s})
            if e.startswith(pfx):
                ends += 1
    out.update({
        'regions_observed': n_with,
        'remaining_start': tot1, 'remaining_end': tot2, 'remaining_delta': tot2 - tot1,
        'zero_regions_start': zero1, 'zero_regions_end': zero2,
        'resets': len(resets), 'reset_regions': len({x['cd'] for x in resets}),
        'reset_examples': sorted(resets, key=lambda x: x['date'])[:8],
        'decreased': sum(1 for d, *_ in deltas if d < 0), 'increased': sum(1 for d, *_ in deltas if d > 0),
        'flat': sum(1 for d, *_ in deltas if d == 0),
        'top_decrease': [{'region': n, 'start': a, 'end': b, 'delta': d} for d, n, cd, a, b in deltas[:10]],
        'top_increase': [{'region': n, 'start': a, 'end': b, 'delta': d} for d, n, cd, a, b in deltas[-5:][::-1]],
        'rounds_started': starts, 'rounds_ended': ends,
        'rounds_started_examples': sorted(start_list, key=lambda x: x['start'])[:6],
        'reopened_regions': reopen, 'sold_out_regions': sold,
        'note': ('잔여 합계는 지역별 잔여(0 하한 클램프)의 합이라 전국 공고−출고와 다를 수 있다. '
                 '"0 도달"은 월중 한 번이라도 양수→0을 관측한 지역 수, "재개"는 0→양수 관측 지역 수.'),
    })
    return out


def as_md(o):
    if o.get('error'):
        return '- 집계 불가: %s' % o['error']
    f = lambda n: format(int(n), ',')
    L = ['- 관측 구간: %s → %s (지역 %d곳, 상태 기준 %s)' % (o['obs_start'], o['obs_end'], o['regions_observed'], o['status_updated']),
         '- 전국 잔여 합계: %s대 → %s대 (%+s대)' % (f(o['remaining_start']), f(o['remaining_end']), f(o['remaining_delta'])),
         '- 잔여 0 지역: %d곳 → %d곳 · 월중 0 도달 %d곳 · 재개(0→양수) %d곳' % (o['zero_regions_start'], o['zero_regions_end'], o['sold_out_regions'], o['reopened_regions']),
         '- 추가공고(리셋) 이벤트: %d건 / %d곳' % (o['resets'], o['reset_regions']),
         '- 회차 접수 시작 %d건 · 종료 %d건 (공단 등록 회차 기준)' % (o['rounds_started'], o['rounds_ended']),
         '- 지역 변화: 감소 %d · 증가 %d · 변화 없음 %d' % (o['decreased'], o['increased'], o['flat']),
         '- 감소 상위: ' + ', '.join('%s %s→%s' % (x['region'], f(x['start']), f(x['end'])) for x in o['top_decrease'][:5]),
         '- 증가 상위: ' + ', '.join('%s %s→%s' % (x['region'], f(x['start']), f(x['end'])) for x in o['top_increase'][:3])]
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser(description='월간 리포트 집계(읽기 전용)')
    today = dt.date.today()
    prev = (today.replace(day=1) - dt.timedelta(days=1)).strftime('%Y-%m')
    ap.add_argument('--month', default=prev, help='YYYY-MM (기본: 지난달)')
    ap.add_argument('--md', action='store_true', help='Markdown 불릿으로 출력')
    ap.add_argument('--json', action='store_true', help='JSON으로 출력')
    a = ap.parse_args()
    o = compute(a.month)
    if a.json:
        print(json.dumps(o, ensure_ascii=False, indent=1))
    elif a.md:
        print(as_md(o))
    else:
        print(as_md(o))
        print('\n[참고] ' + o.get('note', ''))
    return 1 if o.get('error') else 0


if __name__ == '__main__':
    sys.exit(main())
