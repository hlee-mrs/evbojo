#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""EV보조금 산출물 회귀 자동 검사기 (stdlib 전용, /usr/bin/python3)

목적
  프리렌더·브리핑이 만들어 낸 site/ 산출물을 **매 회차 자동으로** 훑어,
  단위 검증은 통과하지만 라이브에서 자기모순으로 드러나는 회귀 클래스를 잡는다.
  (2026-08-31 50-에이전트 더블체크에서 실제로 나온 회귀 유형을 그대로 검사 항목화)

검사 항목
  1  상태 정합    공단 st='마감/접수예정'·등록 회차 종료 지역에 초록/임박 뱃지
  2  유형 잔여 상한 유형별 잔여 > 전체 잔여, '전체 잔여(N대)' 표기 불일치
  3  산문 ↔ 표    산문의 1위 모델/금액 ≠ 차종 표 첫 행
  4  광고 게이트   noindex 또는 <main> 1,200자 미만 페이지의 ad-slot (I4)
  5  색인 정합    sitemap ↔ 실제 파일 / noindex / self-canonical (I9)
  6  금칙어       이하·초과 오용 · '실시간' · '환경부' 단독 · 지방 전환지원금 금액단정
                 · D-day/소진 예측 · WAV 금액을 최고액으로 서술
  7  자기모순 수치 지역 maxP/maxS · 차종 국비 vs '국비 최고액' 서술
  8  링크 무결성   깨진 내부 링크 · sitemap 등재 고아 페이지
  9  템플릿 누수   산출물에 '{{' 잔존
  10 구조         site-header/site-footer/main/h1 중복·누락

사용
  /usr/bin/python3 updater/selfcheck.py              위반 0 → exit 0, 있으면 exit 1
  /usr/bin/python3 updater/selfcheck.py --warn-only  위반이 있어도 exit 0 (배포 차단 안 함)
  옵션: --site DIR  --data DIR  --max N(항목당 예시 수, 기본 5)  --quiet

설계 원칙
  - stdlib 전용·네트워크 금지(I7과 동일 기준). 정규식 기반 — 파서 의존성 없음.
  - **검사기가 서비스를 멈추면 안 된다**(I2 정신): run_auto.sh/run_brief.sh에는
    --warn-only로 물려 로그만 남기고, 배포는 데이터 fail-safe 논리에 맡긴다.
  - 데이터 없음·판단 불가는 위반이 아니다(보수적 판정). 확정 가능한 모순만 센다.
"""

import datetime
import glob
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE = os.path.join(ROOT, 'site')
DATA = os.path.join(SITE, 'data')

BASE_URL = 'https://evbojo.co.kr'
AD_MIN = 1200                 # prerender.AD_MIN과 동일 기준(I4)
MAX_SHOW = 5                  # 항목당 출력 예시 상한(출력 폭주 방지)

# ── 공용 정규식 (모듈 상수로 컴파일 — 350여 페이지 × 수십 패턴이라 재컴파일 금지) ──
RX_SCRIPT = re.compile(r'<script\b.*?</script>|<style\b.*?</style>', re.S | re.I)
RX_MAIN = re.compile(r'<main\b[^>]*>(.*?)</main>', re.S | re.I)
RX_ACC = re.compile(r'<div class="acc-body".*?</div>', re.S)   # 지자체 공고 원문 인용 블록
RX_P = re.compile(r'<p\b[^>]*>(.*?)</p>', re.S | re.I)
RX_TAG = re.compile(r'<[^>]+>')
RX_WS = re.compile(r'\s+')
RX_NOINDEX = re.compile(r'<meta\s+name="robots"\s+content="[^"]*noindex', re.I)
RX_CANON = re.compile(r'<link\s+rel="canonical"\s+href="([^"]+)"', re.I)
RX_HREF = re.compile(r'href="([^"]+)"')
RX_LOC = re.compile(r'<loc>([^<]+)</loc>')
RX_TR = re.compile(r'<tr\b[^>]*>.*?</tr>', re.S | re.I)
RX_BADGE_OPEN = re.compile(r'class="badge badge-(?:open|low)"')
RX_EXT = re.compile(r'^(?:https?:|//|mailto:|tel:|javascript:|data:|#)')

ENT = (('&#39;', "'"), ('&quot;', '"'), ('&lt;', '<'), ('&gt;', '>'),
       ('&nbsp;', ' '), ('&amp;', '&'))


def text_of(html):
    """태그 제거 + 엔티티 복원 + 공백 정규화 (본문 문장 검사용)."""
    s = RX_TAG.sub(' ', html)
    for a, b in ENT:
        s = s.replace(a, b)
    return RX_WS.sub(' ', s).strip()


def num(s):
    return int(s.replace(',', ''))


def kst_today():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime('%Y-%m-%d')


# ── 페이지 로딩 (파일 1회 읽기 → 파생 텍스트 캐시) ──────────────
class Page(object):
    __slots__ = ('path', 'rel', 'raw', 'body', 'main', 'main_txt', 'clean_txt',
                 'prose', 'noindex', 'canonical', 'kind', 'key')

    def __init__(self, path, site):
        self.path = path
        self.rel = os.path.relpath(path, site).replace(os.sep, '/')
        with open(path, encoding='utf-8') as fh:
            self.raw = fh.read()
        self.body = RX_SCRIPT.sub(' ', self.raw)      # 스크립트·스타일 제외본
        m = RX_MAIN.search(self.body)
        self.main = m.group(1) if m else ''
        self.main_txt = text_of(self.main)            # 본문 전체 텍스트(광고 게이트 자수 기준)
        quoted = RX_ACC.sub(' ', self.main)           # 지자체 공고 원문 인용 제외본
        self.clean_txt = text_of(quoted)              # 금칙어·수치 검사용(인용문 제외)
        self.prose = ' '.join(text_of(x) for x in RX_P.findall(quoted))
        self.noindex = bool(RX_NOINDEX.search(self.raw))
        mc = RX_CANON.search(self.raw)
        self.canonical = mc.group(1) if mc else None
        # kind/key: region/car/sido/model/brief/root
        parts = self.rel.split('/')
        if len(parts) == 2 and parts[0] in ('region', 'car', 'sido', 'model', 'brief'):
            self.kind = parts[0]
            self.key = parts[1][:-5]
        else:
            self.kind = 'root'
            self.key = self.rel[:-5]


def load_pages(site):
    pages = []
    for p in sorted(glob.glob(os.path.join(site, '**', '*.html'), recursive=True)):
        pages.append(Page(p, site))
    return pages


def load_json(data, name):
    p = os.path.join(data, name)
    try:
        with open(p, encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return None


# ── 1. 상태 정합 ────────────────────────────────────────────
def closed_signal_codes(status, rounds, today):
    """공단 공식 신호상 '초록·임박 뱃지를 주면 안 되는' 지역 코드 집합.

    - status.st 가 '마감'·'접수예정'
    - rounds.json 최신 회차 접수종료일이 모두 오늘 이전(등록 회차 접수기간 종료)
    판단 불가(데이터 없음)는 넣지 않는다 — 보수적 판정."""
    out = set()
    data = (status or {}).get('data') or {}
    for cd, v in data.items():
        if (v.get('st') or '').strip() in ('마감', '접수예정'):
            out.add(cd)
    rr = (rounds or {}).get('rounds') or {}
    for cd, lst in rr.items():
        ends = [e for e in ((x.get('e') or '')[:10] for x in (lst or []))
                if re.fullmatch(r'\d{4}-\d{2}-\d{2}', e)]
        if ends and max(ends) < today:
            out.add(cd)
    return out


def check_status_badge(pages, ctx):
    """마감·접수예정 지역에 badge-open/badge-low(초록·임박)가 붙으면 위반."""
    bad = ctx['closed_codes']
    if not bad:
        return []
    out = []
    for pg in pages:
        if pg.kind == 'region':
            cd = pg.key
            m = re.search(r'data-live="badge" data-cd="%s"\s*>(.*?)</span></span>'
                          % re.escape(cd), pg.body, re.S)
            seg = m.group(1) if m else ''
            if seg and RX_BADGE_OPEN.search(seg) and cd in bad:
                out.append('%s — 자기 지역(%s) 상태 %s인데 초록/임박 뱃지'
                           % (pg.rel, cd, ctx['st_of'](cd)))
        if pg.kind in ('sido', 'model', 'region', 'root'):
            for row in RX_TR.findall(pg.body):
                if not RX_BADGE_OPEN.search(row):
                    continue
                m = re.search(r'data-cd="(\d+)"', row) or re.search(r'/region/(\d+)\.html', row)
                if m and m.group(1) in bad:
                    out.append('%s — 행 %s 상태 %s인데 초록/임박 뱃지'
                               % (pg.rel, m.group(1), ctx['st_of'](m.group(1))))
    return out


# ── 2. 유형별 잔여 상한 ─────────────────────────────────────
RX_TYPELIST = re.compile(
    r'(?:(?:우선순위|법인·기관|택시|일반) [\d,]+대)(?: · (?:우선순위|법인·기관|택시|일반) [\d,]+대)+')
RX_TYPEITEM = re.compile(r'(우선순위|법인·기관|택시|일반) ([\d,]+)대')
RX_TOTALLEFT = re.compile(r'전체 잔여\(([\d,]+)대\)')


def check_type_left(pages, ctx):
    """유형별 잔여가 전체 잔여를 넘으면 위반 + '전체 잔여(N대)' 표기 불일치."""
    sdata = ctx['status_data']
    out = []
    for pg in pages:
        if pg.kind != 'region':
            continue
        st = sdata.get(pg.key) or {}
        left = st.get('left')
        if not isinstance(left, int) or isinstance(left, bool) or left < 0:
            continue
        for sent in re.split(r'(?<=다\.)\s+', pg.prose):
            prev = 0
            for m in RX_TYPELIST.finditer(sent):
                # 목록 바로 앞 16자만 본다(문장 경계 '.' 이후로 자름) — 배정(공고 물량)
                # 목록과 잔여 목록을 구분하는 최소 문맥. 넓히면 앞 문장의 '잔여'에 오염된다.
                seg = sent[max(prev, m.start() - 16):m.start()]
                if '.' in seg:
                    seg = seg.rsplit('.', 1)[-1]
                prev = m.end()
                if '잔여' not in seg and '남은 물량' not in seg:
                    continue                       # 배정(공고 물량) 목록 — 상한 대상 아님
                for lab, val in RX_TYPEITEM.findall(m.group(0)):
                    if num(val) > left:
                        out.append('%s — 유형 잔여 %s %s대 > 전체 잔여 %d대'
                                   % (pg.rel, lab, val, left))
        for m in RX_TOTALLEFT.finditer(pg.prose):
            if num(m.group(1)) != left:
                out.append('%s — 산문 "전체 잔여(%s대)" ≠ status 잔여 %d대'
                           % (pg.rel, m.group(1), left))
    return out


# ── 3. 산문 ↔ 표 일치 ───────────────────────────────────────
RX_BESTNAME = (
    re.compile(r'합계 보조금이 가장 큰 모델은 (.{1,70}?)로, '),
    re.compile(r'합계 최고액은 (.{1,70}?) 몫으로, '),
    re.compile(r'1위 모델은 (.{1,70}?)이며, '),
    re.compile(r'가장 많이 받는 차는 (.{1,70}?)로, '),
)
RX_BESTAMT = (
    re.compile(r'국비 ([\d,]+)만원을 포함해 ([\d,]+)만원입니다'),
    re.compile(r'국비 ([\d,]+)만원에 지방비를 더한 ([\d,]+)만원입니다'),
)
RX_BESTAMT2 = re.compile(r'합계 ([\d,]+)만원\(국비 ([\d,]+)만원\)입니다')
RX_BESTAMT3 = re.compile(r'합계로 ([\d,]+)만원을 받습니다')
RX_FULLTABLE = re.compile(
    r'data-live="fulltable" data-kind="region"[^>]*>(.*?)</table>', re.S)
RX_CARLINK = re.compile(r'<a href="/car/(\d+)\.html"[^>]*>(.*?)</a>', re.S)
RX_NUMCELL = re.compile(r'<td class="num"[^>]*>([\d,]+)</td>')


def _first_table_row(pg):
    m = RX_FULLTABLE.search(pg.body)
    if not m:
        return None
    for row in RX_TR.findall(m.group(1)):
        a = RX_CARLINK.search(row)
        if a:
            nums = [num(x) for x in RX_NUMCELL.findall(row)]
            return (text_of(a.group(2)), nums)
    return None


def check_prose_table(pages, ctx):
    """산문이 지목한 1위 모델·금액이 차종 표 첫 행과 어긋나면 위반."""
    out = []
    for pg in pages:
        if pg.kind != 'region':
            continue
        first = _first_table_row(pg)
        if not first:
            continue
        name, nums = first
        claim = None
        for rx in RX_BESTNAME:
            m = rx.search(pg.prose)
            if m:
                claim = m.group(1).strip()
                break
        if claim is None:
            continue
        if claim != name:
            out.append('%s — 산문 1위 "%s" ≠ 표 첫 행 "%s"' % (pg.rel, claim, name))
            continue
        # 이름이 같으면 금액도 대조 (국비/합계)
        nat = nums[0] if len(nums) >= 1 else None
        tot = nums[2] if len(nums) >= 3 else None
        got_nat = got_tot = None
        for rx in RX_BESTAMT:
            m = rx.search(pg.prose)
            if m:
                got_nat, got_tot = num(m.group(1)), num(m.group(2))
                break
        if got_tot is None:
            m = RX_BESTAMT2.search(pg.prose)
            if m:
                got_tot, got_nat = num(m.group(1)), num(m.group(2))
        if got_tot is None:
            m = RX_BESTAMT3.search(pg.prose)
            if m:
                got_tot = num(m.group(1))
        if got_tot is not None and tot is not None and got_tot != tot:
            out.append('%s — 산문 1위 합계 %d만원 ≠ 표 첫 행 %d만원' % (pg.rel, got_tot, tot))
        if got_nat is not None and nat is not None and got_nat != nat:
            out.append('%s — 산문 1위 국비 %d만원 ≠ 표 첫 행 %d만원' % (pg.rel, got_nat, nat))
    return out


# ── 4. 광고 게이트 (I4) ─────────────────────────────────────
def check_ad_gate(pages, ctx):
    """noindex 페이지·본문 1,200자 미만 페이지에 ad-slot이 있으면 위반."""
    out = []
    for pg in pages:
        if 'class="ad-slot"' not in pg.body:
            continue
        if pg.noindex:
            out.append('%s — noindex 페이지에 광고 슬롯' % pg.rel)
            continue
        n = len(pg.main_txt)
        if n < AD_MIN:
            out.append('%s — 본문 %d자(<%d)인데 광고 슬롯' % (pg.rel, n, AD_MIN))
    return out


# ── 5. 색인 정합 (I9) ───────────────────────────────────────
def sitemap_targets(site):
    p = os.path.join(site, 'sitemap.xml')
    if not os.path.isfile(p):
        return None
    with open(p, encoding='utf-8') as fh:
        return RX_LOC.findall(fh.read())


def url_to_relpath(url):
    if not url.startswith(BASE_URL):
        return None
    path = url[len(BASE_URL):] or '/'
    path = path.split('#')[0].split('?')[0]
    if path.endswith('/'):
        path += 'index.html'
    return path.lstrip('/')


def check_sitemap(pages, ctx):
    out = []
    locs = ctx['sitemap']
    if locs is None:
        return ['sitemap.xml 없음 — 색인 정합 검사 불가']
    by_rel = ctx['by_rel']
    for url in locs:
        rel = url_to_relpath(url)
        if rel is None:
            out.append('sitemap — 외부/비정상 URL %s' % url)
            continue
        pg = by_rel.get(rel)
        if pg is None:
            out.append('sitemap — 실제 파일 없음 %s (→ site/%s)' % (url, rel))
            continue
        if pg.noindex:
            out.append('sitemap — noindex 페이지 등재 %s' % url)
        if pg.canonical and pg.canonical != url:
            out.append('sitemap — canonical 불일치 %s (canonical=%s)' % (url, pg.canonical))
        elif not pg.canonical:
            out.append('sitemap — canonical 없음 %s' % url)
    return out


# ── 6. 금칙어·팩트체크 ──────────────────────────────────────
RX_BANNED = (
    ('가격구간 이하/초과 오용',
     re.compile(r'(?:5,?300|8,?500)\s*만원\s*(?:이하|초과)')),
    ("'실시간' 표현",
     re.compile(r'실시간(?!.{0,25}(?:아니|아님|않))')),
    ("'환경부' 단독 표기(→ 기후에너지환경부)",
     re.compile(r"(?<!기후에너지)(?<!['‘\"“])환경부(?!['’\"”])")),
    ('지방 전환지원금 금액 단정',
     re.compile(r'지방비[^.。]{0,20}전환[^.。]{0,20}?[0-9][0-9,]*\s*만원'
                r'|전환지원금[^.。]{0,12}지방비[^.。]{0,12}[0-9][0-9,]*\s*만원')),
    ('D-day·소진 예측',
     re.compile(r'D[-−]\s?\d|소진\s*예상|예상\s*소진|소진될 것|며칠\s*(?:내|안)에\s*마감')),
)
# WAV·특수차량 금액을 사이트 최고액으로 서술 — 같은 문맥에 WAV/휠체어 설명이 있으면 정상
RX_WAVMAX = re.compile(
    r'(?:최고액|최대|가장 (?:큰|많)|많게는)[^.。]{0,30}?(?:842|1,872|648)\s*만원'
    r'|(?:842|1,872|648)\s*만원[^.。]{0,20}(?:최고액|최대)')


def check_banned(pages, ctx):
    out = []
    for pg in pages:
        if not pg.main:
            continue
        for label, rx in RX_BANNED:
            for m in rx.finditer(pg.clean_txt):
                s = pg.clean_txt[max(0, m.start() - 30):m.end() + 20]
                out.append('%s — %s: …%s…' % (pg.rel, label, s))
                break                       # 페이지·항목당 1건만(출력 폭주 방지)
        for m in RX_WAVMAX.finditer(pg.prose):
            ctxs = pg.prose[max(0, m.start() - 120):m.end() + 120]
            if 'WAV' in ctxs or '휠체어' in ctxs:
                continue                    # 특수차량임을 같은 문맥에서 밝힌 서술 — 정상
            out.append('%s — WAV 금액을 최고액으로 서술: …%s…'
                       % (pg.rel, pg.prose[max(0, m.start() - 30):m.end() + 20]))
            break
    return out


# ── 7. 자기모순 수치 ────────────────────────────────────────
RX_R_MAXP = re.compile(r'많게는 ([\d,]+)만원에 이릅니다')
RX_R_SUB = re.compile(r'승용 최대 ([\d,]+)만원 · 경·소형 최대 ([\d,]+)만원')
RX_C_NAT = re.compile(r'2026년 국비 ([\d,]+)만원')
RX_C_EQMAX = (
    re.compile(r'국비 최고액\(([\d,]+)만원\)에 해당'),
    re.compile(r'국비 상한\(([\d,]+)만원\)을 꽉 채운'),
    re.compile(r'국비 상한 ([\d,]+)만원을 그대로 받는'),
)
RX_C_PCT = (
    re.compile(r'국비 최고액\(([\d,]+)만원\)과 견주면 약 (\d+)%'),
    re.compile(r'국비 상한\(([\d,]+)만원\)의 약 (\d+)%'),
    re.compile(r'국비 상한 ([\d,]+)만원 대비 약 (\d+)%'),
)


def check_selfcontradiction(pages, ctx):
    """같은 페이지 안에서 서술한 수치가 정본 데이터·서로와 어긋나면 위반."""
    regions = ctx['regions'] or {}
    cars = ctx['cars'] or {}
    natmax = (ctx['meta'] or {}).get('natMax')
    out = []
    for pg in pages:
        if pg.kind == 'region':
            r = regions.get(pg.key) or {}
            mp, ms = r.get('maxP'), r.get('maxS')
            m = RX_R_MAXP.search(pg.clean_txt)
            if m and mp is not None and num(m.group(1)) != mp:
                out.append('%s — 산문 최대 %s만원 ≠ 데이터 maxP %s만원'
                           % (pg.rel, m.group(1), mp))
            m = RX_R_SUB.search(pg.clean_txt)
            if m:
                if mp is not None and num(m.group(1)) != mp:
                    out.append('%s — 부제 승용 최대 %s만원 ≠ maxP %s만원'
                               % (pg.rel, m.group(1), mp))
                if ms is not None and num(m.group(2)) != ms:
                    out.append('%s — 부제 경·소형 최대 %s만원 ≠ maxS %s만원'
                               % (pg.rel, m.group(2), ms))
        elif pg.kind == 'car':
            try:
                cid = int(pg.key)
            except ValueError:
                continue
            c = cars.get(cid) or {}
            nat = c.get('nat')
            m = RX_C_NAT.search(pg.clean_txt)
            if m and nat is not None and num(m.group(1)) != nat:
                out.append('%s — 페이지 국비 %s만원 ≠ 데이터 국비 %s만원'
                           % (pg.rel, m.group(1), nat))
            for rx in RX_C_EQMAX:
                m = rx.search(pg.clean_txt)
                if not m:
                    continue
                claimed = num(m.group(1))
                if natmax and claimed != natmax:
                    out.append('%s — 국비 최고액 %d만원 서술 ≠ meta natMax %s만원'
                               % (pg.rel, claimed, natmax))
                if nat is not None and nat != claimed:
                    out.append('%s — 국비 %s만원인데 "최고액(%d만원)에 해당" 서술(산술 모순)'
                               % (pg.rel, nat, claimed))
                break
            for rx in RX_C_PCT:
                m = rx.search(pg.clean_txt)
                if not m:
                    continue
                claimed, pct = num(m.group(1)), int(m.group(2))
                if natmax and claimed != natmax:
                    out.append('%s — 국비 상한 %d만원 서술 ≠ meta natMax %s만원'
                               % (pg.rel, claimed, natmax))
                if nat is not None and claimed and round(nat / claimed * 100) != pct:
                    out.append('%s — 국비 %s만원/상한 %d만원인데 "약 %d%%" 서술'
                               % (pg.rel, nat, claimed, pct))
                break
    return out


# ── 8. 링크 무결성 ──────────────────────────────────────────
def check_links(pages, ctx):
    site = ctx['site']
    out = []
    inbound = {}
    for pg in pages:
        hasbase = '<base href="/">' in pg.raw
        here = os.path.dirname(pg.path)
        for href in sorted(set(RX_HREF.findall(pg.body))):
            if RX_EXT.match(href):
                continue
            p = href.split('#')[0].split('?')[0]
            if not p:
                continue
            base = site if (hasbase or p.startswith('/')) else here
            tgt = os.path.normpath(os.path.join(base, p.lstrip('/')))
            cands = [tgt]
            if p.endswith('/') or not os.path.splitext(tgt)[1]:
                cands.append(os.path.join(tgt, 'index.html'))
            hit = None
            for c in cands:
                if os.path.isfile(c):
                    hit = os.path.normpath(c)
                    break
            if hit is None:
                out.append('%s — 깨진 내부 링크 %s' % (pg.rel, href))
            elif hit != pg.path:                 # 자기 링크는 인바운드로 세지 않음
                inbound[hit] = inbound.get(hit, 0) + 1
    ctx['inbound'] = inbound
    return out


def check_orphans(pages, ctx):
    """sitemap 등재인데 사이트 내부 인바운드 링크가 0인 페이지(고아)."""
    locs = ctx['sitemap']
    if locs is None:
        return []
    inbound = ctx.get('inbound') or {}
    site = ctx['site']
    out = []
    for url in locs:
        rel = url_to_relpath(url)
        if not rel:
            continue
        path = os.path.normpath(os.path.join(site, rel))
        if not os.path.isfile(path):
            continue                              # 5번 항목에서 이미 보고
        if inbound.get(path, 0) == 0:
            out.append('%s — sitemap 등재이나 내부 인바운드 링크 0(고아)' % url)
    return out


# ── 9·10. 템플릿 누수 / 구조 ────────────────────────────────
def check_template_leak(pages, ctx):
    out = []
    for pg in pages:
        if '{{' in pg.body:
            i = pg.body.index('{{')
            out.append('%s — 템플릿 플레이스홀더 잔존: %s'
                       % (pg.rel, pg.body[i:i + 40].replace('\n', ' ')))
    return out


CONTENT_KINDS = ('region', 'car', 'sido', 'model', 'brief')


def check_structure(pages, ctx):
    out = []
    for pg in pages:
        counts = (
            ('site-header', pg.raw.count('id="site-header"')),
            ('site-footer', pg.raw.count('id="site-footer"')),
            ('main', len(re.findall(r'<main\b', pg.raw))),
            ('h1', len(re.findall(r'<h1\b', pg.raw))),
        )
        for name, n in counts:
            if n > 1:
                out.append('%s — %s %d개(중복)' % (pg.rel, name, n))
            elif n == 0 and pg.kind in CONTENT_KINDS:
                out.append('%s — %s 없음' % (pg.rel, name))
    return out


# ── 실행부 ──────────────────────────────────────────────────
# ── 11·12. 크롤 신호·내부 링크 구조 ─────────────────────────
RX_LASTMOD = re.compile(r'<url>\s*<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>', re.S)
CHURN_MAX = 0.30            # sitemap 전체 중 lastmod가 '오늘'인 비율 상한 — 매일 전 URL이 오늘이면 구글이 lastmod를 무시한다
REL_MIN_LINKS = 3           # 색인 대상 지역 페이지의 '함께 읽으면 좋은 해설' 최소 링크 수


def check_lastmod_churn(pages, ctx):
    """sitemap lastmod 당일 비율 — 실변경만 갱신한다는 원칙이 무너졌는지(칩·뱃지 표기 변형 등 잡음)."""
    p = os.path.join(ctx['site'], 'sitemap.xml')
    if not os.path.isfile(p):
        return []
    with open(p, encoding='utf-8') as fh:
        rows = RX_LASTMOD.findall(fh.read())
    if not rows:
        return []
    today = ctx['today']
    n_today = sum(1 for _, d in rows if d.startswith(today))
    share = n_today / float(len(rows))
    if share > CHURN_MAX:
        by = {}
        for u, d in rows:
            if d.startswith(today):
                seg = u.replace(BASE_URL, '').strip('/').split('/')[0]
                seg = 'root' if (not seg or seg.endswith('.html')) else seg
                by[seg] = by.get(seg, 0) + 1
        return ['lastmod 당일 비율 %d%% (%d/%d, 상한 %d%%) — %s'
                % (round(share * 100), n_today, len(rows), CHURN_MAX * 100,
                   ', '.join('%s %d' % kv for kv in sorted(by.items(), key=lambda kv: -kv[1])))]
    return []


def check_region_related(pages, ctx):
    """색인 대상 지역 페이지마다 해설 링크 섹션이 있고(≥3), 링크 대상이 실제 존재하는지."""
    out = []
    site = ctx['site']
    for p in pages:
        if p.kind != 'region' or p.noindex:
            continue
        m = re.search(r'<ul class="rel-list">(.*?)</ul>', p.main, re.S)
        if not m:
            out.append('%s — 함께 읽으면 좋은 해설 섹션 없음' % p.rel)
            continue
        hrefs = re.findall(r'<a href="([^"]+)"', m.group(1))
        if len(hrefs) < REL_MIN_LINKS:
            out.append('%s — 해설 링크 %d개(최소 %d)' % (p.rel, len(hrefs), REL_MIN_LINKS))
        for h in hrefs:
            if not os.path.isfile(os.path.join(site, h.lstrip('/'))):
                out.append('%s — 해설 링크 대상 없음: %s' % (p.rel, h))
    return out


CHECKS = (
    ('1 상태 정합(마감·접수예정 지역의 초록/임박 뱃지)', check_status_badge),
    ('2 유형별 잔여 상한(전체 잔여 초과)', check_type_left),
    ('3 산문 ↔ 표 일치(1위 모델·금액)', check_prose_table),
    ('4 광고 게이트 I4(noindex·1,200자 미만)', check_ad_gate),
    ('5 색인 정합 I9(sitemap ↔ noindex·파일·canonical)', check_sitemap),
    ('6 금칙어·팩트체크', check_banned),
    ('7 자기모순 수치(최고액·국비)', check_selfcontradiction),
    ('8 링크 무결성(깨진 내부 링크)', check_links),
    ('8b 고아 페이지(sitemap 등재·인바운드 0)', check_orphans),
    ('9 템플릿 누수({{ 잔존)', check_template_leak),
    ('10 구조(site-header/footer/main/h1)', check_structure),
    ('11 크롤 신호(sitemap lastmod 당일 비율)', check_lastmod_churn),
    ('12 지역→해설 내부 링크(함께 읽으면 좋은 해설)', check_region_related),
)


def run(site, data, max_show=MAX_SHOW, quiet=False):
    t0 = time.time()
    pages = load_pages(site)
    status = load_json(data, 'status.json') or {}
    rounds = load_json(data, 'rounds.json') or {}
    regions = load_json(data, 'regions.json') or {}
    cars_raw = load_json(data, 'cars.json') or []
    meta = load_json(data, 'meta.json') or {}
    sdata = (status or {}).get('data') or {}
    today = kst_today()
    ctx = {
        'site': site,
        'status_data': sdata,
        'regions': regions,
        'cars': {c['id']: c for c in cars_raw if isinstance(c, dict) and 'id' in c},
        'meta': meta,
        'today': today,
        'closed_codes': closed_signal_codes(status, rounds, today),
        'sitemap': sitemap_targets(site),
        'by_rel': dict((p.rel, p) for p in pages),
        'st_of': lambda cd: (sdata.get(cd, {}).get('st') or '회차종료'),
    }
    lines = []
    total = 0
    for label, fn in CHECKS:
        try:
            hits = fn(pages, ctx)
        except Exception as exc:                  # 검사기 자체 오류가 배포를 막지 않게
            hits = ['검사기 오류: %s: %s' % (type(exc).__name__, exc)]
        total += len(hits)
        if hits:
            lines.append('[FAIL] %s — %d건' % (label, len(hits)))
            for h in hits[:max_show]:
                lines.append('       · %s' % h)
            if len(hits) > max_show:
                lines.append('       · … 외 %d건' % (len(hits) - max_show))
        elif not quiet:
            lines.append('[ OK ] %s' % label)
    elapsed = time.time() - t0
    head = ('selfcheck: 페이지 %d개 · 데이터 %s · %.2fs — 위반 %d건'
            % (len(pages), status.get('updated', '?'), elapsed, total))
    return total, head, lines


def main(argv):
    warn_only = '--warn-only' in argv
    quiet = '--quiet' in argv
    site, data, max_show = SITE, DATA, MAX_SHOW
    for i, a in enumerate(argv):
        if a == '--site' and i + 1 < len(argv):
            site = os.path.abspath(argv[i + 1])
            data = os.path.join(site, 'data')
        if a == '--data' and i + 1 < len(argv):
            data = os.path.abspath(argv[i + 1])
        if a == '--max' and i + 1 < len(argv):
            try:
                max_show = max(1, int(argv[i + 1]))
            except ValueError:
                pass
    if not os.path.isdir(site):
        print('selfcheck FAIL: site 디렉터리 없음 — %s' % site)
        return 0 if warn_only else 1
    total, head, lines = run(site, data, max_show, quiet)
    print(head)
    for ln in lines:
        print(ln)
    if total == 0:
        print('selfcheck OK: 위반 0건')
        return 0
    print('selfcheck FAIL: 위반 %d건%s' % (total, ' (--warn-only — 배포는 계속)' if warn_only else ''))
    return 0 if warn_only else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
