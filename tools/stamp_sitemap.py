#!/usr/bin/env python3
"""site/sitemap.xml의 모든 <url>에 <lastmod>를 오늘 날짜로 추가/갱신.

데이터가 갱신되는 배포 전에 실행하면 검색엔진 재크롤 우선순위가 올라간다.
사용: python3 tools/stamp_sitemap.py [YYYY-MM-DD]
"""
import datetime
import pathlib
import re
import sys

path = pathlib.Path(__file__).resolve().parent.parent / 'site' / 'sitemap.xml'
day = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
xml = path.read_text(encoding='utf-8')
xml = re.sub(r'<lastmod>[^<]*</lastmod>', f'<lastmod>{day}</lastmod>', xml)
xml = re.sub(r'(<loc>[^<]+</loc>)(?!<lastmod>)', rf'\g<1><lastmod>{day}</lastmod>', xml)
path.write_text(xml, encoding='utf-8')
print(f'lastmod={day}: {xml.count("<lastmod>")}개 URL 스탬프 완료')
