#!/usr/bin/env python3
"""애드센스 사이트 심사 상태 폴링 — AdSense Management API v2 (양방향: 승인/반려 모두 감지).

인증: updater/secrets/adsense-oauth.json {client_id, client_secret, refresh_token[, account]}
      (읽기 전용 스코프 adsense.readonly의 refresh token — setup_adsense_oauth.py로 1회 발급)
상태: REQUIRES_REVIEW / GETTING_READY(심사 중) / READY(승인) / NEEDS_ATTENTION(조치 필요·반려류)
동작: 이전 상태(updater/.adsense_api_state)와 비교, 변할 때만 macOS 알림. 첫 실행은 기록만.
종료 코드: 0 = 정상 조회 / 2 = 오류(호출측이 게재 감지 방식으로 폴백)
"""
import json
import pathlib
import subprocess
import sys
import urllib.parse
import urllib.request

DIR = pathlib.Path(__file__).resolve().parent
SECRETS = DIR / 'secrets' / 'adsense-oauth.json'
STATE = DIR / '.adsense_api_state'
DOMAIN = 'evbojo.co.kr'


def notify(title, msg):
    try:
        subprocess.run(['osascript', '-e',
                        f'display notification "{msg}" with title "{title}" sound name "Glass"'],
                       capture_output=True, timeout=10)
    except Exception:
        pass


def http_json(url, data=None, token=None):
    req = urllib.request.Request(url)
    if data is not None:
        req.data = urllib.parse.urlencode(data).encode()
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    sec = json.loads(SECRETS.read_text())
    tok = http_json('https://oauth2.googleapis.com/token', data={
        'client_id': sec['client_id'], 'client_secret': sec['client_secret'],
        'refresh_token': sec['refresh_token'], 'grant_type': 'refresh_token',
    })['access_token']

    account = sec.get('account')
    if not account:
        accounts = http_json('https://adsense.googleapis.com/v2/accounts', token=tok).get('accounts', [])
        if not accounts:
            raise RuntimeError('adsense accounts empty')
        account = accounts[0]['name']                       # 예: accounts/pub-7688026325140831
        sec['account'] = account
        SECRETS.write_text(json.dumps(sec, ensure_ascii=False, indent=1))

    sites = http_json(f'https://adsense.googleapis.com/v2/{account}/sites?pageSize=50',
                      token=tok).get('sites', [])
    site = next((s for s in sites if DOMAIN in s.get('domain', '')), None)
    if not site:
        raise RuntimeError(f'{DOMAIN} not in sites: ' + json.dumps(sites)[:200])
    cur = site.get('state', 'UNKNOWN')

    prev = STATE.read_text().strip() if STATE.exists() else None
    STATE.write_text(cur)
    changed = prev is not None and prev != cur
    if changed:
        if cur == 'READY':
            notify('🎉 애드센스 승인', f'{DOMAIN} 심사 통과(READY) — 광고 게재가 시작됩니다.')
            (DIR / '.adsense_state').write_text('approved')   # 게재 감지 폴백도 무장 해제
        elif cur == 'NEEDS_ATTENTION':
            notify('⚠️ 애드센스 조치 필요', f'{DOMAIN} 상태가 NEEDS_ATTENTION — 콘솔에서 사유 확인(반려 가능성).')
        else:
            notify('애드센스 상태 변경', f'{DOMAIN}: {prev} → {cur}')
    print(json.dumps({'state': cur, 'prev': prev, 'notified': changed}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(json.dumps({'error': str(e)[:300]}, ensure_ascii=False))
        sys.exit(2)
