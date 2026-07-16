#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""history.json 콜드스타트 시딩 (1회·멱등)
git에 커밋된 과거 site/data/status.json 스냅샷들을 시간순으로 재생해
updater와 동일한 update_history() 로직으로 이력을 복원한다.
- 각 스냅샷의 시각은 파일 내부 updated(KST) 기준 (커밋 시각 아님)
- 같은 날 여러 스냅샷 = 일 버킷 덮어쓰기(마지막 관측 승리) — updater와 동일
- history.json이 이미 있으면 스킵 (--force로 재생성)
사용: python3 tools/backfill_history.py [--force]
"""
import json, os, subprocess, sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'updater'))
from update import update_history, DATA  # noqa: E402  (updater 로직 재사용 — 단일 구현 원칙)

HIST = os.path.join(DATA, 'history.json')
REL = 'site/data/status.json'


def main():
    force = '--force' in sys.argv
    if os.path.exists(HIST) and not force:
        print('history.json 이미 존재 — 스킵 (--force로 재생성)')
        return
    if force and os.path.exists(HIST):
        os.remove(HIST)

    shas = subprocess.run(['git', 'log', '--reverse', '--format=%H', '--', REL],
                          cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    print(f'status.json 커밋 {len(shas)}개 재생 중…')
    seen_days = set()
    for sha in shas:
        raw = subprocess.run(['git', 'show', f'{sha}:{REL}'],
                             cwd=ROOT, capture_output=True, text=True)
        if raw.returncode != 0:
            continue
        try:
            snap = json.loads(raw.stdout)
            ts = datetime.fromisoformat(snap['updated'])
        except Exception as e:
            print(f'  {sha[:8]} 파싱 실패({e}) — 건너뜀')
            continue
        update_history(snap['data'], ts)
        seen_days.add(ts.date().isoformat())
        print(f'  {sha[:8]} → {ts.isoformat()} 반영')

    h = json.load(open(HIST, encoding='utf-8'))
    print(f'완료: 관측일 {len(h["days"])}일({sorted(seen_days)}), 지역 {len(h["r"])}곳, '
          f'{os.path.getsize(HIST):,}B')


if __name__ == '__main__':
    main()
