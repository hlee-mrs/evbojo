#!/usr/bin/env python3
"""애드센스 승인(광고 실제 게재) 감지 — 라이브 사이트를 헤드리스로 열어 광고 iframe을 확인.

원리: 미승인 상태에선 adsbygoogle.js가 광고를 채우지 못한다(TagError·unfilled).
승인되면 슬롯이 filled 되거나 자동광고 iframe(aswift_*)이 생긴다 → 그 순간을 잡는다.

종료 코드: 0 = 게재 감지(승인 신호) / 3 = 미게재(심사 중·정상) / 2 = 오류
출력: 한 줄 JSON (로그·디버깅용)
"""
import json
import sys

from playwright.sync_api import sync_playwright

URL = 'https://evbojo.co.kr/?adwatch=1'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

PROBE = """() => {
  const ins = [...document.querySelectorAll('ins.adsbygoogle')];
  const statuses = ins.map(i => i.getAttribute('data-ad-status'));
  const aswift = [...document.querySelectorAll('iframe[id^="aswift"]')]
    .filter(f => f.offsetWidth > 10 && f.offsetHeight > 10).length;
  const adFrames = [...document.querySelectorAll('iframe')]
    .filter(f => /googleads|doubleclick|googlesyndication/.test(f.src || '')).length;
  return { slots: ins.length, statuses, aswift, adFrames };
}"""


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        try:
            page = browser.new_page(user_agent=UA, viewport={'width': 1280, 'height': 900})
            page.goto(URL, wait_until='domcontentloaded', timeout=45000)
            # 광고 스크립트가 슬롯을 처리할 시간(app.js는 4초 뒤 미채움 슬롯을 숨김 → 이후 상태가 최종)
            page.wait_for_timeout(9000)
            r = page.evaluate(PROBE)
        finally:
            browser.close()
    filled = any(s == 'filled' for s in (r.get('statuses') or []))
    # adFrames(구글 도메인 src 프레임 수)는 미승인 상태에서도 4개가 뜨는 것을 실측 —
    # 유틸리티 프레임(sodar·esf 등)이라 승인 신호로 쓰면 오탐. 디버그 출력만 하고 판정엔 미사용.
    served = filled or r.get('aswift', 0) > 0
    r['served'] = served
    print(json.dumps(r, ensure_ascii=False))
    return 0 if served else 3


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:  # 네트워크·타임아웃 등 — 오류는 조용히 기록만(다음 시간에 재시도)
        print(json.dumps({'error': str(e)[:200]}, ensure_ascii=False))
        sys.exit(2)
