#!/usr/bin/env python3
"""AdSense API OAuth 1회 설정 — 루프백 리다이렉트로 동의 코드 수신 → refresh token 저장.

사전 준비: updater/secrets/adsense-oauth.json 에 {client_id, client_secret}가 있어야 함
           (GCP 콘솔 > 사용자 인증 정보 > OAuth 클라이언트 ID, '데스크톱 앱' 유형).
실행하면 인증 URL을 출력하고 127.0.0.1:8712 에서 리다이렉트를 기다린다.
브라우저에서 그 URL을 열어 동의(스코프: adsense.readonly, 읽기 전용)하면 자동 완료.
"""
import http.server
import json
import pathlib
import sys
import threading
import urllib.parse
import urllib.request

DIR = pathlib.Path(__file__).resolve().parent
SECRETS = DIR / 'secrets' / 'adsense-oauth.json'
PORT = 8712
REDIRECT = f'http://127.0.0.1:{PORT}'
SCOPE = 'https://www.googleapis.com/auth/adsense.readonly'

sec = json.loads(SECRETS.read_text())
auth_url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode({
    'client_id': sec['client_id'], 'redirect_uri': REDIRECT, 'response_type': 'code',
    'scope': SCOPE, 'access_type': 'offline', 'prompt': 'consent',
})
print('AUTH_URL=' + auth_url, flush=True)

code_holder = {}
done = threading.Event()


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        if 'code' in q:
            code_holder['code'] = q['code'][0]
            self.wfile.write('<h2>완료 — 이 창은 닫아도 됩니다.</h2>'.encode())
            done.set()
        else:
            self.wfile.write('<h2>코드 없음 — 다시 시도하세요.</h2>'.encode())

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(('127.0.0.1', PORT), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
if not done.wait(timeout=3600):
    print('TIMEOUT: 1시간 내 동의가 완료되지 않음', flush=True)
    sys.exit(1)
srv.shutdown()

req = urllib.request.Request('https://oauth2.googleapis.com/token')
req.data = urllib.parse.urlencode({
    'client_id': sec['client_id'], 'client_secret': sec['client_secret'],
    'code': code_holder['code'], 'grant_type': 'authorization_code', 'redirect_uri': REDIRECT,
}).encode()
with urllib.request.urlopen(req, timeout=30) as r:
    tok = json.loads(r.read().decode())
if 'refresh_token' not in tok:
    print('ERROR: refresh_token 미포함 — ' + json.dumps(tok)[:200], flush=True)
    sys.exit(1)
sec['refresh_token'] = tok['refresh_token']
SECRETS.write_text(json.dumps(sec, ensure_ascii=False, indent=1))
SECRETS.chmod(0o600)
print('SAVED: refresh_token 저장 완료', flush=True)
