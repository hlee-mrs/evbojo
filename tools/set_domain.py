#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""도메인 전환 도구 — sitemap.xml / robots.txt 를 지정 도메인 기준으로 재생성
사용:
  python3 tools/set_domain.py https://hlee-mrs.github.io/evbojo   (현재 Pages)
  python3 tools/set_domain.py https://evbojo.co.kr                 (도메인 연결 후)
"""
import json, os, sys

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'https://evbojo.co.kr').rstrip('/')
SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'site')

regions = json.load(open(f'{SITE}/data/regions.json', encoding='utf-8'))
cars = json.load(open(f'{SITE}/data/cars.json', encoding='utf-8'))

pages = ['', 'calc.html', 'check.html', 'guide.html', 'law.html', 'refund.html',
         'faq.html', 'compare.html', 'about.html', 'privacy.html', 'donate.html']
lines = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
for u in pages:
    lines.append(f'<url><loc>{BASE}/{u}</loc><changefreq>daily</changefreq></url>')
for cd in regions:
    if cd != '9999':
        lines.append(f'<url><loc>{BASE}/region.html?cd={cd}</loc><changefreq>daily</changefreq></url>')
for c in cars:
    if not c['disc']:
        lines.append(f'<url><loc>{BASE}/car.html?id={c["id"]}</loc><changefreq>weekly</changefreq></url>')
lines.append('</urlset>')
open(f'{SITE}/sitemap.xml', 'w', encoding='utf-8').write('\n'.join(lines))

open(f'{SITE}/robots.txt', 'w', encoding='utf-8').write(
    f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")

print(f'OK — sitemap({len(lines)-3} urls) + robots.txt → {BASE}')
if 'github.io' not in BASE:
    print('※ GitHub Pages에 커스텀 도메인을 쓰려면 site/CNAME 파일에 도메인을 넣고 push 하세요.')
