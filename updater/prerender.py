#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EV보조금 정적 프리렌더 엔진 (stdlib 전용, /usr/bin/python3)

site/data/*.json + updater/templates/*.tpl (+ updater/content/{sido,model}/*.md) →
  site/region/{cd}.html × 161 (9999 한국환경공단 + region_noindex.json 롱테일 지역은 noindex)
  site/car/{id}.html   × 117 (단종 disc=true 는 noindex)
  site/sido/{slug}.html × 17
  site/model/{slug}.html (모델 시리즈 — md의 publish가 KST 오늘 이하인 편만) + site/model/index.html (허브)
  site/sitemap.xml      (noindex·미발행 페이지 제외, lastmod=내용이 실제로 바뀐 날)
  updater/.page_lastmod.json (lastmod 산정용 빌드 캐시 — 커밋 대상 아님)

원칙:
- 전량 재생성·멱등. 모든 페이지를 메모리에서 완성한 뒤에만 파일에 씀(임시파일 → os.replace 원자 교체).
  중간 오류 시 exit≠0 + 기존 파일 완전 보존(부분 파일 없음).
- 산문은 데이터에서 도출한 사실만. 점추정 예측 금지, WAV·'미지원' 차종은 최고액 서술에서 제외,
  데이터 모순(전체 잔여 0 + 유형 잔여 >0 등)은 단정 문장 생략. '전기차 보조금' 키워드 문단당 1회 이하.
- 마감 감지는 site/assets/js/app.js detectClosed의 보수 포팅(완료형 선언만 마감, 조건부는 절대 마감 아님).
- 광고 게이팅: 정적 산문+공지 합계 1,200자 미만 또는 noindex 페이지엔 광고 슬롯 자체를 만들지 않음.
- sitemap lastmod는 내용 해시(<main> 구간, 수치 마스킹) 기준. 잔여 대수만 바뀐 날은 lastmod 불변
  → 크롤 스케줄러가 "매일 전 URL 변경"으로 오인하지 않게 한다.
"""
import datetime
import hashlib
import json
import os
import re
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE = os.path.join(ROOT, 'site')
DATA = os.path.join(SITE, 'data')
TPL_DIR = os.path.join(HERE, 'templates')
SIDO_MD_DIR = os.path.join(HERE, 'content', 'sido')
MODEL_MD_DIR = os.path.join(HERE, 'content', 'model')
LASTMOD_STORE = os.path.join(HERE, '.page_lastmod.json')   # 페이지별 내용 해시·최종 변경일(빌드 캐시)
REGION_NOINDEX = os.path.join(DATA, 'region_noindex.json')   # 롱테일 지역 noindex 목록(cd 배열)
BASE = 'https://evbojo.co.kr'
KST = datetime.timezone(datetime.timedelta(hours=9))   # 발행 게이트는 서버 로컬이 아니라 KST 기준
AD_MIN = 1200          # 광고 게이팅: 정적 산문+공지 합계 최소 자수
D0 = datetime.date(2026, 1, 1)   # history.json d0

# ── 시도 슬러그 (스펙 고정 17) ──
SIDO_SLUG = {
    '서울': 'seoul', '부산': 'busan', '대구': 'daegu', '인천': 'incheon',
    '광주': 'gwangju', '대전': 'daejeon', '울산': 'ulsan', '세종': 'sejong',
    '경기': 'gyeonggi', '강원': 'gangwon', '충북': 'chungbuk', '충남': 'chungnam',
    '전북': 'jeonbuk', '전남': 'jeonnam', '경북': 'gyeongbuk', '경남': 'gyeongnam',
    '제주': 'jeju',
}
SIDO_FULL = {
    '서울': '서울특별시', '부산': '부산광역시', '대구': '대구광역시', '인천': '인천광역시',
    '광주': '광주광역시', '대전': '대전광역시', '울산': '울산광역시', '세종': '세종특별자치시',
    '경기': '경기도', '강원': '강원특별자치도', '충북': '충청북도', '충남': '충청남도',
    '전북': '전북특별자치도', '전남': '전라남도', '경북': '경상북도', '경남': '경상남도',
    '제주': '제주특별자치도',
}
MAKER_SHORT = {'현대자동차': '현대', '테슬라코리아': '테슬라', '메르세데스벤츠코리아': '벤츠',
               '볼보자동차코리아': '볼보', '케이지모빌리티': 'KGM', '폭스바겐그룹코리아': '폭스바겐그룹',
               '비와이디코리아': 'BYD'}

# ── 모델 시리즈 (slug 고정 8 — model_group 라벨과 1:1, 슬러그는 ^[a-z0-9-]+$만) ──
MODEL_SERIES = {
    'ioniq5': '아이오닉5', 'ioniq6': '아이오닉6', 'ev6': 'EV6', 'ev3': 'EV3',
    'model-y': '모델Y', 'casper': '캐스퍼 일렉트릭', 'kona': '코나 일렉트릭', 'ray': '레이 EV',
}

# 정적 핵심 페이지(30) — sitemap 상단. (region.html/car.html 레거시·파라미터 URL은 신규 경로로 대체돼 제외)
CORE_PAGES = [
    ('/', 'daily'), ('/status.html', 'hourly'), ('/calc.html', 'daily'), ('/check.html', 'daily'),
    ('/guide.html', 'daily'), ('/law.html', 'daily'), ('/refund.html', 'daily'), ('/faq.html', 'daily'),
    ('/compare.html', 'daily'), ('/about.html', 'weekly'), ('/privacy.html', 'weekly'),
    ('/donate.html', 'weekly'), ('/report.html', 'weekly'), ('/articles.html', 'weekly'),
    ('/price-tiers.html', 'weekly'), ('/myths.html', 'weekly'), ('/timeline-traps.html', 'weekly'),
    ('/residency.html', 'weekly'), ('/refund-rules.html', 'weekly'), ('/quota-reading.html', 'weekly'),
    ('/second-round.html', 'weekly'), ('/buyer-types.html', 'weekly'), ('/conversion-grant.html', 'weekly'),
    ('/extra-support.html', 'weekly'), ('/winter-range.html', 'weekly'), ('/changes-2026-2027.html', 'weekly'),
    ('/sold-out.html', 'weekly'), ('/region-ranking.html', 'weekly'),
    ('/winter-range-ranking.html', 'weekly'), ('/yearend-guide.html', 'weekly'),
]


# ── 공용 유틸 ──────────────────────────────────────────────
def esc(s):
    """HTML 이스케이프 + 템플릿 토큰 무해화.
    데이터 유래 문자열(공지 note·선정방식 m 등)에 '{{'가 섞여 있어도
    render()의 플레이스홀더로 오인되지 않도록 '{{'를 '&#123;{'로 치환한다(렌더 결과는 동일)."""
    return (str('' if s is None else s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#39;')
            .replace('{{', '&#123;{'))


def fmt(n):
    return '-' if n is None else format(int(n), ',')


def pick(seed, options):
    """결정적 문장 풀 선택 — 같은 데이터면 같은 문장(멱등), 페이지마다 다른 변형.
    주의: crc32는 XOR-선형이라 시드가 접미사 한 글자만 다르면 인덱스가 상관돼
    조합 풀이 무너진다 → md5로 확산(디퓨전) 확보(결정적이므로 멱등 유지)."""
    h = int.from_bytes(hashlib.md5(seed.encode('utf-8')).digest()[:4], 'big')
    return options[h % len(options)]


def compose(seed, slot, *parts):
    """세그먼트 조합 문장 생성 — 각 세그먼트(리스트)를 독립 시드로 선택해
    조합 가짓수를 곱으로 늘린다(풀 4×4×4=64형). 문자열 세그먼트는 그대로 이어붙임.
    같은 데이터·같은 시드면 항상 같은 문장(멱등)."""
    out = []
    for i, p in enumerate(parts):
        out.append(p if isinstance(p, str) else pick('%s:%s#%d' % (seed, slot, i), p))
    return ''.join(out)


_KN = {0: '영', 1: '한', 2: '두', 3: '세', 4: '네', 5: '다섯',
       6: '여섯', 7: '일곱', 8: '여덟', 9: '아홉', 10: '열'}
_KDAY = {1: '하루', 2: '이틀', 3: '사흘', 4: '나흘', 5: '닷새', 6: '엿새', 7: '이레'}


def kn(n):
    """작은 수 관형사(한/두/세…) — 10 초과는 숫자 표기."""
    return _KN.get(n, fmt(n))


def knu(n, unit):
    """수 관형사+단위 — 고유어 수사는 띄어쓰기('다섯 개'), 숫자는 붙임('12개')."""
    return ('%s %s' % (_KN[n], unit)) if n in _KN else ('%s%s' % (fmt(n), unit))


def kday(n):
    """일수 고유어(하루/이틀/사흘…) — 7일 초과는 'N일'."""
    return _KDAY.get(n, '%s일' % fmt(n))


def josa(word, with_batchim, without):
    """은/는·이/가·을/를 — 비한글 끝이면 병기."""
    ch = word.strip()[-1:]
    if ch and '가' <= ch <= '힣':
        return with_batchim if (ord(ch) - 0xAC00) % 28 else without
    return '%s(%s)' % (with_batchim, without)


def strip_tags(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


# ── 마감 감지 (app.js detectClosed 보수 포팅) ──────────────
# 원칙: 완료형 마감 선언만 신뢰. "예산 소진 시 조기 마감" 같은 조건부·미래형은 절대 마감 아님.
# 최악의 오류는 열린 지역을 마감으로 오판 — 애매하면 closed=False.
_COND_PRE = re.compile(r'(소진\s?시(?!점|각|간)|초과\s?시(?!점|각|간)|될\s?수|경우|한\s?때|시\s?조기\s?$)')
# 조건부·미래형 마감 문구 선제 제거: "예산 소진 시 … 마감", "물량 초과시 … 접수 마감" 류는
# 마감 선언이 아니라 예고이므로, 완료형 패턴 매칭 전에 해당 구간을 통째로 지운다(길이 보존 → 날짜 창 무영향).
_COND_KILL = re.compile(r'(?:소진|초과)\s?시(?!점|각|간)[^.!?★☆※]{0,60}?(?:마감|종료|중단)')
_SENT_BREAK = '.!?★☆※'


def _sent_start(t, idx):
    """idx 직전 문장 경계(마침표·구분 기호) 다음 위치 — 조건부 가드를 문장 단위로 적용하기 위함."""
    s = 0
    for ch in _SENT_BREAK:
        p = t.rfind(ch, 0, idx)
        if p + 1 > s:
            s = p + 1
    return s
_ALLOC = re.compile(r'(우선\s?순위|우선순위|우선\s?배정|택시|택배|이륜|어린이|버스|승합|수소)')
_OPEN_SIG = re.compile(r'(접수\s?중|접수중|신청\s?가능|접수\s?시작|접수시작|접수\s?재개|접수\s?가능|선정\s?가능|추진\s?중)')
_PATTERNS = [re.compile(p) for p in [
    r'(마감|종료|소진)\s?(되었|됐|하였|했)',
    r'마감\s?[(（][^()（）]{0,26}[)）]\s?(되었|됐)',
    r'(마감|종료)\s?(입니다|임을|합니다|함)',
    r'(전량|모두|전체\s?물량|물량\s?모두|전\s?물량)\s?(마감|소진)',
    r'(대상자\s?)?선정[이은는]?\s?(모두\s?)?(마감|완료|끝났)',
    r'추진\s?완료',
    r'접수\s?종료',
    r'(더\s?이상|현재)\s?접수\s?불가',
    r'(본예산|예산|국비)\s?(조기\s?)?소진(되어|으로)',
]]
_BARE = re.compile(r'마감')
_DATE1 = re.compile(r"(?:(20\d{2})|['’`]?(\d{2}))\s?[.년]\s?(\d{1,2})\s?[.월/]\s?(\d{1,2})[일.]?"
                    r"(?:\s?\([월화수목금토일]\))?(?:\s?기준)?(?:\s?(\d{1,2}:\d{2}))?")
_DATE2 = re.compile(r"()(?:^|[^\d.])(\d{1,2})()\s?[./]\s?(\d{1,2})\.?(?:\s?\([월화수목금토일]\))?(?:\s?(\d{1,2}:\d{2}))?")
_NEXT = re.compile(r'(추경|추가\s?공고|다음\s?공고|[3-9]\s?차\s?(?:공고|접수|사업|보급)|하반기\s?공고|추가\s?모집)'
                   r'[^.★☆※]{0,36}(예정|예상|계획|가능)')
# 날짜형 재개 안내: "3차 접수 8/20 10시", "3차 신청 및 접수 기간 2026.8.20." 류 —
# '예정/예상' 없이 날짜·기간으로 새 회차를 알리는 공지도 nextRound로 잡는다.
# 마감·종료·소진이 사이에 끼면 재개 안내가 아니므로 배제(tempered pattern).
_NEXT_DATE = re.compile(r'[2-9]\s?차\s?(?:(?!마감|종료|소진)[^.!?★☆※]){0,20}?(?:공고|접수|신청|모집|보급)'
                        r'\s?(?:(?!마감|종료|소진)[^.!?★☆※]){0,30}?'
                        r'(?:\d{1,2}\s?[./월]\s?\d{1,2}|기간|개시|재개|시작|진행)')


def detect_closed(note):
    res = {'closed': False, 'partial': False, 'closedDate': None, 'nextRound': None}
    if not note:
        return res
    t = re.sub(r'\s+', ' ', str(note))
    t = _COND_KILL.sub(lambda m: ' ' * len(m.group(0)), t)   # 조건부 마감 예고 선제 제거(길이 보존)
    hits = []

    def consider(idx, ln):
        pre = t[_sent_start(t, idx):idx]                     # 문장 단위 문맥(직전 문장 경계까지)
        post = t[idx + ln:idx + ln + 8]
        if _COND_PRE.search(pre):                       # ① 조건부 문맥
            return
        if re.match(r'^\s?안\s?되|^\s?되지\s?않', post):  # ② 부정형
            return
        if _ALLOC.search(pre) and not re.search(r'(승용|화물|전체|전량|모두|사업|민간)', pre):
            return                                       # ③ 특수물량만의 마감
        if '상반기' in pre and _OPEN_SIG.search(t):       # ④ 과거 회차 + 새 회차 열림
            return
        fr = re.search(r'([2-9])\s?차[^.]{0,10}(신청|접수)\s?기간', t[idx + ln:idx + ln + 60])
        if fr:                                           # ⑤ "1차 마감" 직후 더 높은 회차 안내
            pr = re.search(r'([1-9])\s?차(?![가-힣])', pre)
            if pr and int(fr.group(1)) > int(pr.group(1)):
                return
        hits.append({'idx': idx, 'len': ln, 'pass': '승용' in pre, 'truck': '화물' in pre,
                     'global': not ('승용' in pre or '화물' in pre)})

    for rex in _PATTERNS:
        for m in rex.finditer(t):
            consider(m.start(), len(m.group(0)))
    for m in _BARE.finditer(t):                          # 맨몸 "마감" — 강한 가드 하에서만
        idx = m.start()
        nxt = t[idx + 2:idx + 8]
        if re.match(r'^(되|될|돼|됐|하|함|입|임|안)', nxt):
            continue
        if re.match(r'^\s?(예정|임박|시|또는|여부|대수|일|기한|이후|전|후)', nxt):
            continue
        if not re.search(r'(접수|공고|물량|사업|승용|화물|기간|신청|모집)', t[max(0, idx - 12):idx]):
            continue
        consider(idx, 2)
    if not hits:
        return res
    hits.sort(key=lambda h: h['idx'])
    res['closed'] = True
    any_global = any(h['global'] for h in hits)
    has_pass = any(h['pass'] for h in hits)
    has_truck = any(h['truck'] for h in hits)
    res['partial'] = (not any_global and has_pass != has_truck) or bool(_OPEN_SIG.search(t))
    # 날짜 창은 승용 문장 우선 → 전역 문장 → 첫 매치 순: "화물 8.7 마감 ★ 승용 8.12 마감"에서 8/7 오집기 방지.
    # 창 시작은 해당 문장 경계로 제한 — 앞 문장(화물 등)의 날짜가 창에 섞이지 않게.
    h0 = next((h for h in hits if h['pass']),
              next((h for h in hits if h['global']), hits[0]))
    win = t[max(_sent_start(t, h0['idx']), h0['idx'] - 40):min(len(t), h0['idx'] + h0['len'] + 40)]
    dm = _DATE1.search(win) or _DATE2.search(win)
    if dm:
        if dm.re is _DATE1:
            y = dm.group(1) or ('20' + dm.group(2) if dm.group(2) else '2026')
            mo, dd = dm.group(3), dm.group(4)
        else:                       # "7.16" "6/30" 형태 — 연도 없음
            y, mo, dd = '2026', dm.group(2), dm.group(4)
        try:
            mo_i, dd_i = int(mo), int(dd)
            if 1 <= mo_i <= 12 and 1 <= dd_i <= 31:
                res['closedDate'] = '%s-%02d-%02d' % (y, mo_i, dd_i) + (' ' + dm.group(5) if dm.group(5) else '')
        except (TypeError, ValueError):
            pass
    nr = _NEXT.search(t) or _NEXT_DATE.search(t)
    if nr:
        res['nextRound'] = nr.group(0).strip()[:60]
    return res


# ── 상태 뱃지 (app.js statusBadge의 정적 축약 — stale 분기는 생성 시점 데이터라 불필요) ──
def badge_of(st, closed):
    if not st or st.get('left') is None:
        return ('badge-closed', '물량 정보 없음')
    left = st['left']
    if left <= 0:
        return ('badge-closed', '잔여 소진(추가공고 확인)')
    if closed and closed['closed']:
        if closed['partial']:
            return ('badge-shut', '공지상 마감 안내 · 유형별 확인 필요')
        cdte = closed.get('closedDate')
        md = ' (%d/%d)' % (int(cdte[5:7]), int(cdte[8:10])) if cdte else ''
        return ('badge-shut', '공지상 접수 마감%s · 잔여 %s대는 미출고분일 수 있음' % (md, fmt(left)))
    n = st.get('n')
    ratio = left / n if n else 1
    if left < 30 or ratio < 0.06:
        return ('badge-low', '마감 임박 · 잔여 %s대' % fmt(left))
    return ('badge-open', '접수 중 · 잔여 %s대' % fmt(left))


# ── history 추이 (실측 산출 — 점추정 예측 금지, 과거 사실만 문장화) ──
def _biz_days(d1, d2, hol):
    b = 0
    for d in range(d1 + 1, d2 + 1):
        dt = D0 + datetime.timedelta(days=d)
        if dt.weekday() < 5 and dt.isoformat() not in hol:
            b += 1
    return b


def trend_of(hist, cd, asof_day):
    """최근 4주 잔여 감소 실측. 반환: None(이력 없음) 또는 dict."""
    if not hist or hist.get('v') != 1:
        return None
    e = hist.get('r', {}).get(cd)
    if not e or not e.get('l'):
        return None
    days = hist.get('days', [])
    pts = [(d, v) for d, v in zip(days, e['l']) if v is not None]
    rd = (e.get('L') or {}).get('rd')
    if rd:
        pts = [p for p in pts if p[0] >= rd['t']]
    if not pts:
        return None
    hol = set(hist.get('holidays') or [])
    win = [p for p in pts if p[0] >= asof_day - 28]
    reset7 = any(v[1] == 0 and asof_day - v[0] <= 7 for v in (e.get('L') or {}).get('ev') or [])
    if len(win) < 2 or win[-1][0] - win[0][0] < 4:
        return {'insufficient': True, 'obs': len(pts), 'reset7': reset7}
    drop = win[0][1] - win[-1][1]
    span = win[-1][0] - win[0][0]
    bdays = _biz_days(win[0][0], win[-1][0], hol)
    # 최근 정체 일수: 창 끝값과 같은 값이 이어진 기간(실측 — 해석은 문장 쪽에서 보수적으로)
    i = len(win) - 1
    while i > 0 and win[i - 1][1] == win[-1][1]:
        i -= 1
    flat_recent = win[-1][0] - win[i][0]
    return {'insufficient': False, 'obs': len(pts), 'reset7': reset7, 'drop': max(0, drop),
            'span': span, 'bdays': bdays, 'from': win[0][1], 'to': win[-1][1],
            'flat_recent': flat_recent}


# ── 템플릿 ──────────────────────────────────────────────
def load_tpl(name):
    with open(os.path.join(TPL_DIR, name), encoding='utf-8') as f:
        return f.read()


def render(tpl, mapping):
    """단일 패스 치환 — 템플릿(원본)의 키 집합을 mapping과 사전 대조하고,
    치환된 값 영역은 다시 스캔하지 않는다(데이터 유래 '{{…}}'가 빌드를 오염·중단시키지 않음)."""
    need = set(re.findall(r'\{\{([A-Z][A-Z0-9_]*)\}\}', tpl))
    missing = need - set(mapping)
    if missing:
        raise RuntimeError('치환 안 된 플레이스홀더: ' + ','.join(sorted(missing)))
    return re.sub(r'\{\{([A-Z][A-Z0-9_]*)\}\}', lambda m: mapping[m.group(1)], tpl)


def ad_slot(slot_name, gate_chars, noindex):
    """광고 게이팅 — 저가치·noindex 페이지에는 슬롯 자체를 만들지 않음. 라벨은 '광고'."""
    if noindex or gate_chars < AD_MIN:
        return ''
    return ('<div class="ad-slot" data-slot="%s"><div class="ad-label">광고</div>'
            '<div class="ad-box"></div></div>' % slot_name)


def jsonld_script(objs):
    return '\n'.join('<script type="application/ld+json">%s</script>'
                     % json.dumps(o, ensure_ascii=False, separators=(',', ':')) for o in objs)


# ── sitemap lastmod 신뢰 회복: 내용 해시 ────────────────────
_MAIN_RE = re.compile(r'<main\b[^>]*>(.*?)</main>', re.S | re.I)
_NUM_RE = re.compile(r'[0-9][0-9,.:]*')
# 고유어 수사(kn/knu/kday 산출물)도 수치 표현이라 함께 마스킹 — 평탄 일수처럼 매일 증가하는
# 값이 '사흘→나흘'로 바뀌는 것만으로 lastmod가 갱신되는 것을 막는다. 단위가 붙은 형태만 대상.
_KNUM_RE = re.compile(r'하루|이틀|사흘|나흘|닷새|엿새|이레'
                      r'|(?:영|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)(?=\s?(?:개|곳|가지|번째))')


def content_hash(html):
    """페이지 본문(<main> 구간)에서 수치 표현을 마스킹한 md5.

    잔여 대수 100→99, 갱신 시각 같은 '숫자만' 바뀐 날은 해시가 같고,
    문장 분기·마감 상태·공지 원문·공고 차수처럼 실질 텍스트가 바뀐 날만 달라진다.
    <main>이 없으면(비정형 정적 파일) 문서 전체를 대상으로 한다. 빈 입력은 ''(→ 폴백)."""
    if not html:
        return ''
    m = _MAIN_RE.search(html)
    body = m.group(1) if m else html
    return hashlib.md5(_KNUM_RE.sub('#', _NUM_RE.sub('#', body)).encode('utf-8')).hexdigest()


def load_lastmod_store():
    """{'<사이트 상대경로>': {'h': 해시, 'd': 'YYYY-MM-DD'}} — 없거나 깨졌으면 빈 dict.
    빈 dict면 이번 회차 lastmod는 전부 오늘로 폴백된다(종전 동작). 빌드는 절대 실패시키지 않음."""
    try:
        with open(LASTMOD_STORE, encoding='utf-8') as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {}
    except Exception:
        return {}
    out = {}
    for k, v in raw.items():
        if (isinstance(k, str) and isinstance(v, dict) and isinstance(v.get('h'), str) and v['h']
                and isinstance(v.get('d'), str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', v['d'])):
            out[k] = {'h': v['h'], 'd': v['d']}
    return out


def save_lastmod_store(store):
    """캐시 저장(원자 교체). 실패해도 빌드는 성공 — 다음 회차가 오늘 날짜로 폴백될 뿐."""
    try:
        atomic_write(LASTMOD_STORE,
                     json.dumps(store, ensure_ascii=False, sort_keys=True, indent=0) + '\n')
    except Exception as e:
        print('경고: lastmod 캐시 저장 실패(%s) — 다음 회차는 오늘 날짜로 폴백' % e, file=sys.stderr)


def load_region_noindex():
    """색인 표면 축소 대상 지역 cd 집합(군 단위 롱테일 = 검색 노출 0).
    파일이 없거나 파싱 실패면 빈 집합으로 강등해 빌드는 그대로 성공시킨다."""
    try:
        with open(REGION_NOINDEX, encoding='utf-8') as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            return set()
        return {str(x) for x in raw if re.fullmatch(r'[0-9]{4,5}', str(x))}
    except Exception:
        return set()


# ── 데이터 로드 ──────────────────────────────────────────
def load_data():
    def rj(name):
        with open(os.path.join(DATA, name), encoding='utf-8') as f:
            return json.load(f)
    cars = rj('cars.json')
    for c in cars:                                   # 표시명(사양코드 제거) 우선 — 원문 name은 수집 매칭용
        if c.get('disp'):
            c['name'] = c['disp']
    regions = rj('regions.json')
    for r in regions.values():                       # 도 공통 단가 ref → 원본 v 연결
        if r.get('ref') and regions.get(r['ref']):
            r['v'] = regions[r['ref']]['v']
    meta = rj('meta.json')
    status = rj('status.json')
    try:
        hist = rj('history.json')
    except Exception:
        hist = None                                   # 이력은 없어도 빌드 성공(무소음 강등)
    try:
        rounds = rj('rounds.json')                    # 공고 차수·공단 변경이력 — 없어도 빌드 성공
    except Exception:
        rounds = None
    return cars, regions, meta, status, hist, rounds


def car_v(r, cid):
    v = r.get('v') or []
    return v[cid] if cid < len(v) and v[cid] else None


# ══════════════════════════════════════════════════════════
#  region 페이지
# ══════════════════════════════════════════════════════════
def build_region(cd, r, cars, regions, meta, status, hist, ctx):
    st = status['data'].get(cd) or {}
    updated = status.get('updated', '')
    asof = updated[:10]
    name = r['name']
    sido = r.get('sido', '')
    slug = SIDO_SLUG.get(sido)
    # noindex: 9999(한국환경공단) + 롱테일 지역(region_noindex.json — 검색 노출 0인 군 단위).
    # 페이지·형제 칩 링크는 그대로 유지(탐색용)하고 색인 표면에서만 뺀다. 광고 슬롯은 ad_slot이 제거.
    noindex = (cd == '9999') or (cd in ctx.get('region_noindex', ()))
    closed = ctx['closed_map'][cd]
    cls, label = badge_of(st, closed)
    # 데이터 모순 가드: 전체 잔여 0인데 유형 잔여가 남음 → 단정 문장 생략 대상
    d = st.get('d') or {}
    contradiction = (st.get('left') is not None and st['left'] <= 0
                     and any((x or 0) > 0 for x in (d.get('left') or [])))

    # 순위·시도 통계 (9999 제외 160개 기준)
    all_r = [(k, v) for k, v in regions.items() if k != '9999']
    rank = sum(1 for _, v in all_r if (v.get('maxP') or 0) > (r.get('maxP') or 0)) + 1
    pct = max(1, round(rank / len(all_r) * 100))
    sibs = [(k, v) for k, v in all_r if v.get('sido') == sido]
    sib_max = max((v.get('maxP') or 0) for _, v in sibs) if sibs else 0
    sib_min = min((v.get('maxP') or 0) for _, v in sibs) if sibs else 0
    sido_rank = sum(1 for _, v in sibs if (v.get('maxP') or 0) > (r.get('maxP') or 0)) + 1

    # 모델·최고액 (WAV·'미지원' 차종은 최고액 서술에서 제외 — 일반 구매와 조건이 다름)
    models = [(c, car_v(r, c['id'])) for c in cars if not c['disc'] and car_v(r, c['id'])]
    best = None
    conv_max = 0
    for c, v in models:
        conv_max = max(conv_max, v[1] or 0)
        if 'WAV' in c['name'] or '미지원' in c['name']:
            continue
        tot = c['nat'] + v[0]
        if not best or tot > best[1]:
            best = (c, tot)

    avg_maxp = round(sum((v.get('maxP') or 0) for _, v in all_r) / len(all_r))
    prose = region_prose(cd, r, st, closed, contradiction, rank, pct, len(all_r),
                         sido, sido_rank, len(sibs), sib_max, sib_min, best, conv_max,
                         trend_of(hist, cd, ctx['asof_day']), meta, asof, updated, avg_maxp,
                         sibs=sibs, status=status, ctx=ctx, models=models)
    prose_html = ''.join('<p style="line-height:1.75;margin:10px 0">%s</p>' % p for p in prose)

    # 공고 차수·변경이력 데이터 (연혁 섹션에서 사용)
    rd = ctx.get('rounds') or {}
    r_rounds = (rd.get('rounds') or {}).get(cd) or []
    r_events = (rd.get('events') or {}).get(cd) or []

    # 공지 원문 섹션 (페이지별 완전 고유 텍스트 — 이스케이프 필수)
    note = (st.get('note') or '').strip()
    note_sec = ''
    if note:
        head = ''
        if closed['closed']:
            cdte = closed.get('closedDate')
            head = ('<div class="callout callout-danger small" style="margin:0 0 10px">🚫 공지상 접수 마감%s%s%s</div>'
                    % (' (%s)' % esc(cdte) if cdte else '',
                       ' · 일부 차종·유형은 접수 가능할 수 있어요' if closed['partial'] else '',
                       ' · 🔜 %s' % esc(closed['nextRound']) if closed.get('nextRound') else ''))
        body = ('<p class="small" style="line-height:1.7;white-space:pre-line">%s</p>' % esc(note)
                if len(note) <= 180 else
                '<details class="acc"><summary>공고 전문 펼쳐 보기 (%s자)</summary>'
                '<div class="acc-body" style="line-height:1.7;white-space:pre-line">%s</div></details>'
                % (fmt(len(note)), esc(note)))
        note_sec = ('<section class="card"><h2 class="mt0">📢 지자체 공지 원문</h2>%s%s'
                    '<p class="stamp">출처: 무공해차 통합누리집(ev.or.kr) 지자체 공고 · 수집 %s</p></section>'
                    % (head, body, esc(updated.replace('T', ' '))))

    # 공고 차수·공식 변경이력 — 이 지역에서만 참인 1차 데이터(차수 구성·일정·공단 등록 변경 기록)
    if r_rounds:
        rtr = []
        for x in r_rounds:
            period = ('%s ~ %s' % (esc(x.get('s') or '?'), esc(x.get('e') or '?'))
                      if x.get('s') or x.get('e') else '—')
            rtr.append('<tr><td style="font-weight:700">%s</td><td class="small">%s</td>'
                       '<td class="small">%s</td><td class="small">%s</td></tr>'
                       % (esc(x.get('k') or '?'), esc(x.get('post') or '—'), period, esc(x.get('d') or '—')))
        ev_html = ''
        if r_events:
            evs = []
            for t, item, before, after in r_events[:8]:
                chg = ('%s → %s' % (esc(before), esc(after))) if before else esc(after)
                evs.append('<li class="small" style="margin:4px 0"><span class="muted">%s</span> · %s: %s</li>'
                           % (esc((t or '')[:16].replace('-', '.')), esc(item or ''), chg))
            ev_html = ('<h3 class="small" style="margin:14px 0 4px">공단 등록 변경 이력 (최근 90일 · %d건)</h3>'
                       '<ul style="list-style:none;padding:0;margin:0">%s</ul>' % (len(r_events), ''.join(evs)))
        note_sec += ('<section class="card"><h2 class="mt0">📅 %s 공고 차수·일정</h2>'
                     '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>차수</th><th>게시일</th>'
                     '<th>접수기간</th><th>신청마감</th></tr></thead><tbody>%s</tbody></table></div>%s'
                     '<p class="stamp">출처: 무공해차 통합누리집(ev.or.kr) 보조금관리시스템 등록 정보 · 수집 %s</p></section>'
                     % (esc(name), ''.join(rtr), ev_html, esc(updated.replace('T', ' '))))

    # 차종 표 (상위 25 정적 — 전체는 detail.js 확장)
    # WAV·미지원 모델은 일반 구매와 조건이 달라 본표에서 분리 — 헤드라인 최고액(maxP)과 표 1위가 일치하도록
    all_rows = sorted(((c, v[0], c['nat'] + v[0]) for c, v in models), key=lambda x: (-x[2], x[0]['name']))
    special = [x for x in all_rows if 'WAV' in x[0]['name'] or '미지원' in x[0]['name']]
    rows = [x for x in all_rows if x not in special]

    def tr_of(c, loc, tot):
        return ('<tr><td><a href="/car/%d.html" style="color:inherit;font-weight:700">%s</a>'
                '<div class="small muted">%s%s</div></td>'
                '<td class="num">%s</td><td class="num">%s</td>'
                '<td class="num" style="font-weight:800;color:var(--money)">%s</td>'
                '<td><button class="btn-s btn btn-ghost" data-cmp="%d">비교</button></td></tr>'
                % (c['id'], esc(c.get('disp') or c['name']), esc(MAKER_SHORT.get(c['maker'], c['maker'])),
                   ' · %skm' % c['range'] if c.get('range') else '',
                   fmt(c['nat']), fmt(loc), fmt(tot), c['id']))
    trs = [tr_of(c, loc, tot) for c, loc, tot in rows[:25]]
    if special:
        trs.append('<tr><td colspan="5" class="small muted" style="padding-top:12px">'
                   '♿ 복지·특수목적 차량 — 일반 구매와 지원 조건이 다릅니다 (아래 금액은 해당 요건 충족 시)</td></tr>')
        trs += [tr_of(c, loc, tot) for c, loc, tot in special]

    # 형제 지역: 접수 가능(open→low→나머지) 우선 최대 8개 + 시도 허브 링크
    def sib_key(item):
        k, v = item
        scls, _ = badge_of(status['data'].get(k) or {}, ctx['closed_map'][k])
        order = {'badge-open': 0, 'badge-low': 1, 'badge-shut': 2, 'badge-closed': 3}[scls]
        return (order, -(v.get('maxP') or 0))
    sib_html = []
    for k, v in sorted(((k, v) for k, v in sibs if k != cd), key=sib_key)[:8]:
        scls, _ = badge_of(status['data'].get(k) or {}, ctx['closed_map'][k])
        col = {'badge-open': 'var(--badge-open)', 'badge-low': 'var(--badge-low)'}.get(scls, 'var(--badge-closed)')
        sib_html.append('<a class="chip" href="/region/%s.html"><i class="chip-dot" style="background:%s"></i>%s %s만원</a>'
                        % (k, col, esc(v['name']), fmt(v.get('maxP'))))
    if slug:
        sib_html.append('<a class="chip" href="/sido/%s.html"><b>%s 전체 %d곳 보기 →</b></a>'
                        % (slug, esc(SIDO_FULL[sido]), len(sibs)))
    sibs_html = ''.join(sib_html) or '<span class="muted small">단일 지역이에요</span>'

    # 진행률 스택바 (region.html progHTML 이식)
    prog = ''
    if all(st.get(k) is not None for k in ('n', 'a', 'r', 'left')) and st['n'] > 0:
        out, wait, lf = st['r'], max(0, st['a'] - st['r']), max(0, st['left'])
        denom = max(st['n'], out + lf, st['a'], out + wait + lf)
        if denom > 0:
            w = lambda x: '%.1f%%' % (x / denom * 100)
            prog = ('<div class="prog"><div class="stack"><i class="seg-r" style="width:%s"></i>'
                    '<i class="seg-w" style="width:%s"></i><i class="seg-l" style="width:%s"></i></div>'
                    '<div class="legend"><span><i style="background:var(--text3)"></i>출고 %s</span>'
                    '<span><i style="background:var(--warn)"></i>접수대기 %s</span>'
                    '<span><i style="background:var(--money)"></i>잔여 %s</span><span>공고 %s대</span></div></div>'
                    % (w(out), w(wait), w(lf), fmt(out), fmt(wait), fmt(lf), fmt(st['n'])))

    status_lines = []
    if st.get('m'):
        status_lines.append('<p class="small muted mt8">선정 방식: %s</p>' % esc(st['m']))
    # 공단 공식 접수상태·최종 신청마감 병기 — 공지 원문 해석(뱃지)과 다를 수 있어 두 신호를 모두 제공
    if st.get('st'):
        official = '공단 등록 접수상태: <b>%s</b>' % esc(st['st'])
        if st.get('dl'):
            official += ' · 최종 신청마감 %s' % esc(st['dl'])
        status_lines.append('<p class="small muted mt8">%s <span class="muted">(공지 원문과 다르면 최근 변경이 반영 중일 수 있어요)</span></p>' % official)
    if r.get('rep'):
        status_lines.append('<p class="small muted mt8">ℹ️ 차종별 단가: 도(道) 공통 단가 기준 — 시·군 자체 추가 지원 여부는 공고문 확인</p>')

    tel = r.get('tel') or ''
    if not tel or re.search(r'0000-?0000', tel):
        tel_btn = ('<a class="btn btn-ghost" href="https://ev.or.kr/nportal/buySupprt/initPsLocalInquiriesAction.do"'
                   ' target="_blank" rel="noopener">📞 %s — 문의처 확인 ↗</a>' % esc(r.get('dept') or '담당부서'))
    else:
        tel_btn = '<a class="btn btn-ghost" href="tel:%s">📞 %s (%s)</a>' % (
            re.sub(r'[^0-9]', '', tel), esc(r.get('dept') or '담당부서'), esc(tel))

    canonical = '%s/region/%s.html' % (BASE, cd)
    crumb_mid = ('<a href="/sido/%s.html">%s</a>' % (slug, esc(SIDO_FULL[sido]))) if slug else esc(name)
    breadcrumb = '<a href="/">홈</a> › %s › <b>%s</b>' % (crumb_mid, esc(name))
    bc_items = [{'@type': 'ListItem', 'position': 1, 'name': '홈', 'item': BASE + '/'}]
    if slug:
        bc_items.append({'@type': 'ListItem', 'position': 2, 'name': '%s 전기차 보조금' % SIDO_FULL[sido],
                         'item': '%s/sido/%s.html' % (BASE, slug)})
    bc_items.append({'@type': 'ListItem', 'position': len(bc_items) + 1, 'name': name, 'item': canonical})
    ld = [{'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': bc_items},
          {'@context': 'https://schema.org', '@type': 'Dataset',
           'name': '%s 전기차 보조금 현황 (2026)' % name,
           'description': '%s의 2026년 전기승용 구매보조금 차종별 단가(국비+지방비)와 접수 잔여 현황. 무공해차 통합누리집(ev.or.kr) 공고 데이터를 매시간 수집해 게시.' % name,
           'url': canonical, 'inLanguage': 'ko', 'dateModified': asof,
           'creator': {'@type': 'Person', 'name': 'HyeongHun Lee', 'url': BASE + '/about.html#operator'},
           'isBasedOn': 'https://ev.or.kr'}]

    mapping = {
        'NAME': esc(name), 'CD': cd,
        'SUB': '2026년 전기승용 기준 · 승용 최대 %s만원 · 경·소형 최대 %s만원' % (fmt(r.get('maxP')), fmt(r.get('maxS'))),
        'BADGE_CLS': cls, 'BADGE_LABEL': esc(label),
        'HEAD_NUMS': ('<span class="muted small">공고 %s대 · 접수 %s · 출고 %s</span>'
                      % (fmt(st['n']), fmt(st['a']), fmt(st['r']))) if st.get('n') is not None else '',
        'PROG': prog,
        'STATUS_LINES': ''.join(status_lines),
        'TEL_BTN': tel_btn,
        'STAMP': '잔여현황 기준 %s · 단가 기준일 %s · 출처 ev.or.kr' % (esc(updated.replace('T', ' ')), esc(meta['updated'])),
        'PROSE': prose_html,
        'NOTE_SECTION': note_sec,
        'AD1': '', 'AD2': '',
        'TABLE_SUB': '보조금 상위 %d개 / 전체 %d개 모델' % (min(25, len(rows)), len(all_rows)),
        'TABLE_ROWS': ''.join(trs),
        'MODEL_COUNT': str(len(all_rows)),
        'SIDO_LABEL': esc(SIDO_FULL.get(sido, sido or '지역')),
        'SIBLINGS': sibs_html,
    }
    # 광고 게이트: app.js renderAds와 동일하게 정적 <main> 전체 텍스트 기준(1,200자)
    gate = len(strip_tags(render(ctx['tpl_region'], mapping)))
    mapping['AD1'] = ad_slot('region-1', gate, noindex)
    mapping['AD2'] = ad_slot('region-2', gate, noindex)
    main = render(ctx['tpl_region'], mapping)
    page = render(ctx['tpl_page'], {
        'TITLE': esc('%s 전기차 보조금 2026 — 최대 %s만원·잔여 현황 | EV보조금' % (name, fmt(r.get('maxP')))),
        'DESC': esc('%s 2026년 전기차 보조금: 승용 최대 %s만원(국비+지방비), 잔여 %s대 · %s. 차종별 단가표%s, 담당부서 연락처까지. %s 기준.'
                    % (name, fmt(r.get('maxP')), fmt(st.get('left')), label.split(' · ')[0],
                       ', 지자체 공지 원문' if note else '', asof)),
        'ROBOTS': '\n<meta name="robots" content="noindex">' if noindex else '',
        'CANONICAL': canonical,
        'JSONLD': jsonld_script(ld),
        'BREADCRUMB': breadcrumb,
        'MAIN': main,
        'META_UPDATED': esc(meta['updated']),
    })
    return page, gate


def region_prose(cd, r, st, closed, contradiction, rank, pct, n_all, sido, sido_rank,
                 n_sibs, sib_max, sib_min, best, conv_max, tr, meta, asof, updated, avg_maxp,
                 sibs=None, status=None, ctx=None, models=None):
    """산문 5~6문단 — 데이터 조건 분기(순위·소진율·추이·마감 상태·단가 구조별로 서술 자체가
    달라짐) × 세그먼트 조합 풀(슬롯당 12~64형) × 문단 순서 시드 가변.
    사실은 전부 데이터 실측. 점추정 예측·조건부 마감의 마감 단정 금지, WAV·미지원 차종 제외."""
    name = r['name']
    P = lambda slot, opts: pick('%s:%s' % (cd, slot), opts)
    CC = lambda slot, *parts: compose(cd, slot, *parts)
    maxP = fmt(r.get('maxP'))
    left, n, a, out = st.get('left'), st.get('n'), st.get('a'), st.get('r')
    sido_full = SIDO_FULL.get(sido, sido or '해당 지역')

    # ══ 파생 실측값 ══
    rate = round(out / n * 100) if (n and out is not None and n > 0) else None
    my_p = r.get('maxP') or 0
    others = [(k, v) for k, v in (sibs or []) if k != cd]
    ties = sorted(v['name'] for _, v in others if (v.get('maxP') or 0) == my_p)
    above = min(((v.get('maxP') or 0, v['name']) for _, v in others
                 if (v.get('maxP') or 0) > my_p), default=None)
    below = max(((v.get('maxP') or 0, v['name']) for _, v in others
                 if (v.get('maxP') or 0) < my_p), default=None)
    open_sib = None                     # 마감 공지 없이 잔여 최다인 도내 이웃(실측·보수 기준)
    if ctx and status:
        cands = []
        for k, v in others:
            s2 = status['data'].get(k) or {}
            c2 = (ctx.get('closed_map') or {}).get(k)
            if (s2.get('left') or 0) > 0 and c2 is not None and not c2['closed']:
                cands.append(((s2.get('left') or 0), v['name']))
        if cands:
            open_sib = max(cands)
    tops = []                           # 비WAV·비미지원 상위 차종(실명 비교용)
    for c, v in (models or []):
        if 'WAV' in c['name'] or '미지원' in c['name']:
            continue
        tops.append((c['nat'] + v[0], c['name'], c['nat']))
    tops.sort(key=lambda x: (-x[0], x[1]))

    # ── A 현황 ──
    pA = []
    pA.append(CC('intro',
        ['', '요점부터 말하면 ', '숫자부터 확인하면 ', '결론부터 적으면 ',
         '금액 기준으로 보면 ', '핵심만 추리면 ', '올해 조건을 정리하면 ', '지금 시점 기준으로 '],
        ['%s의 2026년 전기차 보조금(전기승용)은 국비와 지방비를 합해 ' % name,
         '2026년 %s에서 전기승용을 구매할 때 전기차 보조금은 국비+지방비 합계로 ' % name,
         '%s 전기차 보조금은 2026년 전기승용 기준 국비·지방비를 더해 ' % name,
         '전기승용 기준으로 %s%s 올해 국비와 지방비를 합쳐 ' % (name, josa(name, '은', '는')),
         '%s의 올해 전기승용 지원액은 국비·지방비 합산으로 ' % name,
         '%s에서 올해 전기승용 한 대를 사면 받을 수 있는 보조금은 합계 ' % name,
         '%s 관내 등록 기준, 2026년 전기승용 구매보조금은 국비·지방비를 더해 ' % name,
         '2026년 공고 기준 %s의 전기승용 지원 상한은 ' % name],
        ['최대 %s만원입니다.' % maxP,
         '많게는 %s만원에 이릅니다.' % maxP,
         '%s만원이 상한입니다.' % maxP,
         '최대 %s만원으로 잡혀 있습니다.' % maxP,
         '차종에 따라 최대 %s만원까지입니다.' % maxP,
         '%s만원을 상한으로 차종별로 달라집니다.' % maxP]))
    # 순위 백분위 표기: 하위권에서 '상위 93%' 같은 혼란 표현을 피하고 자연어로
    pct_txt = ('상위 %d%%' % pct) if pct <= 50 else ('하위 %d%%' % (100 - pct))
    rk_head = ['전국 %d개 지자체 가운데 %d위(%s)로, ' % (n_all, rank, pct_txt),
               '이 상한은 전국 %d곳 중 %d번째(%s)에 해당해 ' % (n_all, rank, pct_txt),
               '전국 순위로는 %d곳 중 %d위(%s)라 ' % (n_all, rank, pct_txt),
               '%d개 지자체를 통틀어 %d위(%s)에 놓여 ' % (n_all, rank, pct_txt)]
    if pct <= 30:
        pA.append(CC('rank-hi', rk_head,
            ['지원 규모가 큰 지역군에 속합니다.',
             '금액 면에서 전국 상위권입니다.',
             '상한액 자체가 유리한 지역입니다.',
             '전국에서도 높은 축에 듭니다.']))
    elif pct <= 70:
        pA.append(CC('rank-mid', rk_head,
            ['중간 수준의 상한입니다.',
             '전국 평균 상한(%s만원) 언저리의 범위입니다.' % fmt(avg_maxp),
             '많지도 적지도 않은 중위권입니다.',
             '순위보다는 물량·마감 시점이 더 중요한 구간입니다.']))
    else:
        pA.append(CC('rank-lo', rk_head,
            ['금액 자체는 낮은 편입니다.',
             '상한액보다는 접수 가능 여부가 관건인 지역입니다.',
             '하위권 상한이지만 국비 몫은 전국 동일합니다.',
             '전국 평균 상한(%s만원)과 견줘볼 만한 수준입니다.' % fmt(avg_maxp)]))
    if n is not None and a is not None and out is not None and left is not None:
        pA.append(CC('nums',
            ['올해 공고 물량은 전체 %s대로, ' % fmt(n),
             '물량부터 보면 공고 %s대에 ' % fmt(n),
             '공고 %s대 기준으로 ' % fmt(n),
             '전체 공고는 %s대이며 ' % fmt(n),
             '규모로는 공고 %s대 사업인데 ' % fmt(n)],
            ['지금까지 접수 %s건·출고 %s대가 진행돼 ' % (fmt(a), fmt(out)),
             '접수가 %s건 들어오고 %s대가 출고를 마쳐 ' % (fmt(a), fmt(out)),
             '접수 누계 %s건과 출고 %s대를 지나 ' % (fmt(a), fmt(out)),
             '현재 접수 %s건, 출고 %s대가 집계돼 ' % (fmt(a), fmt(out))],
            ['잔여는 %s대입니다.' % fmt(left),
             '남은 물량 수치는 %s대입니다.' % fmt(left),
             '잔여 칸에는 %s대가 찍혀 있습니다.' % fmt(left)]))
        if n > 0 and a > n:
            pA.append(CC('over',
                ['', '주의할 대목: ', '단서가 하나 있는데, '],
                ['접수가 공고 물량을 이미 %s건 넘어선 상태여서 ' % fmt(a - n),
                 '이미 공고분보다 %s건 초과 접수돼 ' % fmt(a - n),
                 '접수 초과분이 %s건 쌓여 있어 ' % fmt(a - n),
                 '공고 대비 %s건이 더 접수된 상황이라 ' % fmt(a - n)],
                ['신규 신청은 앞선 접수의 취소·미배정분을 기다리는 성격이 됩니다.',
                 '지금 신청하면 선순위 이탈이 있어야 차례가 옵니다.',
                 '신규 접수는 사실상 대기 줄에 서는 셈입니다.',
                 '새로 넣는 신청은 취소분이 나와야 배정을 받는 구조입니다.']))
        elif n > 0 and rate is not None:
            rt_head = ['출고 기준 소진율은 약 %d%%로 ' % rate,
                       '공고 물량의 약 %d%%가 출고를 마쳐 ' % rate,
                       '출고분을 공고분으로 나누면 약 %d%%가 소진돼 ' % rate,
                       '소진율(출고/공고)이 약 %d%%라 ' % rate]
            if rate >= 95:
                rt_tail = ['막바지 물량만 남은 계산입니다.', '열에 아홉 이상이 이미 차를 받았습니다.',
                           '사실상 마무리 단계의 흐름입니다.', '공고분 대부분이 출고를 마친 셈입니다.']
            elif rate >= 85:
                rt_tail = ['후반부에 들어선 흐름입니다.', '열에 여덟을 넘긴 진행률입니다.',
                           '소진이 상당히 진행된 편입니다.', '남은 비중이 크지 않은 단계입니다.']
            elif rate >= 60:
                rt_tail = ['절반을 훌쩍 넘긴 진행률입니다.', '중후반 구간에 들어섰습니다.',
                           '과반이 출고를 마친 정도입니다.', '출고가 꾸준히 이어져 온 흐름입니다.']
            elif rate >= 30:
                rt_tail = ['아직 중반 이전의 진행률입니다.', '절반 이상이 출고 전 단계입니다.',
                           '소진이 본격화되기 전의 수준입니다.', '출고 여지가 크게 남은 구간입니다.']
            else:
                rt_tail = ['출고는 아직 초반 단계입니다.', '소진이 이제 시작된 수준입니다.',
                           '대부분 물량이 출고 전입니다.', '진행 초입의 수치입니다.']
            pA.append(CC('rate', rt_head, rt_tail))
    # 상태 문장 — 마감/모순/임박/접수중 분기 (조건부 '소진 시 조기 마감'은 마감으로 취급하지 않음)
    if closed['closed'] and not closed['partial']:
        cdte = closed.get('closedDate')
        dtxt = '(%s)' % cdte if cdte else ''
        pA.append(CC('closed',
            ['', '중요한 단서로, ', '읽는 법이 하나 있는데, '],
            ['지자체 공지 기준으로 이번 회차 접수는 마감이 안내된 상태%s라 ' % dtxt,
             '공지문상 접수 마감%s이 안내돼 있어 ' % dtxt,
             '지자체 공지가 이번 회차 마감%s을 알리고 있어 ' % dtxt,
             '공지에는 접수 마감%s이 명시돼 있어 ' % dtxt],
            ['잔여로 표시되는 수치는 아직 출고되지 않은 물량일 수 있습니다.',
             '남은 대수를 접수 가능 물량으로 읽으면 안 됩니다.',
             '표시되는 잔여는 미출고분일 가능성이 큽니다.',
             '잔여 숫자와 접수 가능 여부는 별개로 봐야 합니다.']))
    elif closed['closed']:
        pA.append(CC('partial',
            ['', '다만 ', '한 가지 조건이 있는데, '],
            ['지자체 공지에 마감 관련 안내가 있으나 일부 차종·유형은 접수가 가능할 수 있어 ',
             '공지문에 마감 안내와 접수 안내가 함께 있는 지역이라 ',
             '마감 문구가 공지에 섞여 있지만 유형에 따라 창구가 열려 있을 수 있어 '],
            ['신청 전 유형별 확인이 필요합니다.',
             '내 유형·차종 기준으로 확인해야 합니다.',
             '전체 마감으로 단정하지 않는 편이 좋습니다.']))
    elif contradiction:
        pA.append(CC('contra',
            ['', '집계를 그대로 읽기 어려운 지역인데, ', '수치 해석에 주의가 필요한데, '],
            ['전체 잔여는 0으로 잡히지만 신청 유형별 수치가 일부 남아 있어 ',
             '전체 수치와 유형별 수치가 서로 다르게 남아 있어(회차 이월 가능성) ',
             '전체 잔여 0과 유형별 잔여가 공존하는 상태라 '],
            ['실제 접수 가능 여부는 지자체 확인이 필요합니다.',
             '단정 대신 공고·전화 확인이 안전합니다.',
             '회차 이월분일 수 있으니 공고문을 확인하세요.']))
    elif left is not None and left <= 0:
        pA.append(CC('soldout',
            ['', '현재로서는 ', '시점상 '],
            ['잔여가 0대로 집계돼 이번 공고 물량은 소진된 것으로 보이며 ',
             '남은 물량이 0으로 잡혀 있어 ',
             '이번 회차 물량은 다 나간 것으로 집계되며 '],
            ['추가 공고 여부를 확인해야 하는 단계입니다.',
             '지금은 추경·추가 공고를 기다릴 시점입니다.',
             '잔여가 다시 늘면 추가 공고 신호로 읽으면 됩니다.',
             '하반기 추가 공고가 나오는 지역도 많으니 공지를 지켜보세요.']))
    elif left is not None and left < 30:
        pA.append(CC('low',
            ['', '상황을 요약하면 ', '시점상으로는 '],
            ['잔여가 %s대에 불과해 마감이 임박한 국면이라 ' % fmt(left),
             '남은 물량이 %s대뿐이어서 ' % fmt(left),
             '잔여 %s대는 임박 신호로 봐야 하니 ' % fmt(left)],
            ['신청 전 잔여를 다시 확인하는 편이 안전합니다.',
             '곧 마감될 수 있음을 전제로 움직여야 합니다.',
             '접수 직전에 잔여를 한 번 더 확인하세요.',
             '계약·서류 준비를 서두르는 쪽이 낫습니다.']))
    elif left is not None:
        pA.append(CC('open',
            ['현재는 ', '현시점 기준으로는 ', '집계상으로는 ', '수치상 '],
            ['접수가 진행 중인 상태로 ', '신청 가능한 물량이 남아 있어 ',
             '접수 여력이 남아 있어 ', '창구가 열려 있는 것으로 집계돼 '],
            ['잔여 추이를 함께 보며 움직이면 됩니다.',
             '공고문 요건 확인만 마치면 신청으로 이어갈 수 있습니다.',
             '평상 절차대로 진행하면 되는 시점입니다.',
             '통상적인 준비 순서로 접근하면 됩니다.']))
    if closed['closed'] and closed.get('nextRound'):
        pA.append(CC('nextround',
            ["공지에는 '%s' 안내도 함께 있어 " % closed['nextRound'],
             "다만 '%s'라는 후속 안내가 있어 " % closed['nextRound'],
             "'%s' 문구가 공지에 있으므로 " % closed['nextRound']],
            ['다음 회차를 노린다면 원문을 확인해 둘 만합니다.',
             '재개 일정은 공지 원문에서 확인하세요.',
             '접수가 다시 열릴 여지가 있습니다.']))

    # ── B 추이 (history 실측 — 과거 사실만, 소진 시점 점추정 금지) ──
    pB = []
    if tr is None:
        pB.append(CC('nohist',
            ['이 지역의 잔여 감소 추이는 아직 관측 기록이 없어 ',
             '잔여 이력이 아직 축적 전이라 ',
             '추이 통계가 지금은 비어 있어 '],
            ['매시간 기록이 쌓이는 대로 ', '수집이 계속 돌고 있으므로 ', '기록이 며칠 쌓이면 '],
            ['이 자리에서 감소 속도를 안내합니다.',
             '추이를 함께 보여드릴 예정입니다.',
             '속도 해석을 덧붙이겠습니다.']))
    elif tr.get('reset7'):
        pB.append(CC('reset',
            ['최근 일주일 사이 추가 공고로 물량이 늘어난 기록이 있는데 ',
             '일주일 내 잔여가 다시 늘어난 리셋 기록이 잡혔는데(추가 공고 신호) ',
             '추가 공고로 잔여가 늘어난 지 일주일이 지나지 않은 지역이라 '],
            ['재공고 물량은 소진이 빠른 편이니 공지를 바로 확인하는 게 좋습니다.',
             '이런 시기엔 속도 통계보다 공고문 확인이 우선입니다.',
             '신청 계획이 있다면 지자체 공지부터 여는 편이 낫습니다.']))
    elif tr['insufficient']:
        pB.append(CC('short',
            ['잔여 추이는 관측 %d일째로 아직 축적 중이라 ' % tr['obs'],
             '이 지역 잔여 이력은 %d일치뿐이어서 ' % tr['obs'],
             '관측 %d일째라 추세라 부를 데이터가 아직 없어 ' % tr['obs']],
            ['짧은 표본의 속도 해석은 오차가 커 계산하지 않습니다.',
             '감소 속도 단정은 미루고 축적을 기다리는 중입니다.',
             '수치가 더 쌓이면 안내에 반영합니다.']))
    elif tr['drop'] <= 0:
        pB.append(CC('flat',
            ['', '추이 쪽을 보면 ', '이력상으로는 '],
            ['최근 %d일(관측 창) 동안 잔여 감소가 관측되지 않았는데 ' % tr['span'],
             '지난 %d일간 잔여 수치에 변화가 없었는데 ' % tr['span'],
             '%d일째 잔여가 움직이지 않고 있는데 ' % tr['span']],
            ['접수 소강이거나 집계 정체일 수 있어 여유로 읽기는 어렵습니다.',
             '출고 집계의 정체일 수 있으므로 접수 가능 여부는 공고로 확인하세요.',
             '조용해 보여도 집계 특성일 수 있으니 공지 확인이 필요합니다.']))
    else:
        per = tr['drop'] / tr['bdays'] if tr['bdays'] else 0
        pB.append(CC('trend',
            ['', '흐름을 보면 ', '기록을 되짚으면 '],
            ['실측 추이를 보면 ', '이 사이트 기록상 ', '관측 창 기준으로 ', '이력 데이터에서는 '],
            ['최근 %d일간 잔여가 %s대에서 %s대로 %s대 줄었습니다.'
             % (tr['span'], fmt(tr['from']), fmt(tr['to']), fmt(tr['drop'])),
             '지난 %d일 사이 잔여는 %s대→%s대로 %s대 감소했습니다.'
             % (tr['span'], fmt(tr['from']), fmt(tr['to']), fmt(tr['drop'])),
             '최근 %d일 동안 %s대였던 잔여가 %s대가 되어 %s대 빠졌습니다.'
             % (tr['span'], fmt(tr['from']), fmt(tr['to']), fmt(tr['drop'])),
             '%d일에 걸쳐 잔여가 %s대에서 %s대까지 %s대 내려왔습니다.'
             % (tr['span'], fmt(tr['from']), fmt(tr['to']), fmt(tr['drop']))]))
        if per >= 1:
            spd = '영업일 하루 평균 약 %d대꼴' % round(per)
            word = '가파른' if per >= 20 else ('빠른' if per >= 5 else '꾸준한')
        else:
            spd = '영업일 %s에 1대꼴' % kday(round(1 / max(per, 1e-9)))
            word = '더딘'
        pB.append(CC('speed',
            ['속도로 치면 ', '환산하면 ', '감소 페이스는 '],
            ['%s로, ' % spd, '%s이며, ' % spd, '%s인데, ' % spd],
            ['%s 흐름입니다.' % word, '%s 편의 소진세입니다.' % word, '%s 축에 드는 속도입니다.' % word]))
        if tr.get('flat_recent', 0) >= 3:
            kd = kday(tr['flat_recent'])
            pB.append(CC('stall',
                ['다만 최근 %s%s ' % (kd, josa(kd, '은', '는')),
                 '특이점으로 마지막 %s간 ' % kd,
                 '한편 최근 %s 동안은 ' % kd,
                 '끝자락 %s%s ' % (kd, josa(kd, '은', '는'))],
                ['잔여가 그대로였는데, ', '수치 변동이 없었는데, ',
                 '감소가 멈춰 있었는데, ', '숫자가 제자리였는데, '],
                ['집계 공백일 수 있어 확대 해석은 금물입니다.',
                 '출고 집계 특성일 수 있는 구간입니다.',
                 '여유 신호로 읽기는 어렵습니다.',
                 '출고 일정이 몰리면 다시 움직일 수 있는 수치입니다.']))
        pB.append(CC('trendcaveat',
            ['', '참고로 ', '덧붙이면 '],
            ['다만 잔여는 신청 시점이 아니라 차량 출고 시점에 줄어드는 지역이 많아 ',
             '잔여가 출고돼야 줄어드는 집계라는 점 때문에 ',
             '이 수치는 출고 기준으로 움직이므로 '],
            ['실제 접수는 수치보다 먼저 마감될 수 있습니다.',
             '접수 창구는 잔여가 남아 있어도 먼저 닫힐 수 있습니다.',
             '접수 경쟁은 그보다 앞서 벌어질 수 있습니다.',
             '마감은 숫자보다 한발 앞서 올 수 있습니다.']))

    # ── C1 단가 구조 (도 공통 여부·도내 격차·이웃 실명 비교) ──
    pC1 = []
    if r.get('rep'):
        pC1.append(CC('rep',
            ['', '단가 구조부터 보면 ', '금액표의 성격을 짚어 두면 '],
            ['%s의 차종별 단가는 %s가 정한 도 공통 단가라 ' % (name, sido_full),
             '이 지역 금액표는 %s 공통 단가를 그대로 쓰는 구조라 ' % sido_full,
             '차종별 단가는 도 공통형이어서 금액이 %s 안에서 동일하고 ' % sido_full],
            ['지역별 변수는 결국 물량과 마감 시점입니다.',
             '시·군 자체 추가 지원 여부만 공고로 확인하면 됩니다.',
             '표 금액 자체는 도내 다른 시·군과 같습니다.',
             '차이는 접수 상황에서 납니다.']))
    elif n_sibs > 1:
        pC1.append(CC('ownrate',
            ['', '한편 ', '단가 쪽을 보면 '],
            ['%s%s 자체 단가를 운영하는 지역이라 ' % (name, josa(name, '은', '는')),
             '차종별 지방비 단가는 %s%s 자체적으로 정한 금액이라 ' % (name, josa(name, '이', '가')),
             '이곳은 도 공통 단가가 아니라 자체 단가표를 쓰기 때문에 '],
            ['인접 시·군과 금액이 다를 수 있습니다.',
             '같은 도라도 표가 지역마다 갈립니다.',
             '이웃 지역과의 비교가 의미 있습니다.']))
    if n_sibs > 1 and sib_max != sib_min:
        rng = '%s만~%s만원' % (fmt(sib_min), fmt(sib_max))
        gp_pre = ['', '도내 격차도 참고할 만한데, ', '이사·전입 변수까지 본다면, ']
        gp_head = ['같은 %s 안에서 시·군별 최대 지원액은 %s에 걸쳐 있는데, ' % (sido_full, rng),
                   '%s %d개 시·군의 상한 분포(%s) 안에서 ' % (sido_full, n_sibs, rng),
                   '도내 상한이 %s로 갈리는 가운데 ' % rng,
                   '시·군별 상한이 %s 범위로 벌어져 있는 %s에서 ' % (rng, sido_full)]
        if sido_rank == 1:
            pC1.append(CC('gap-top', gp_pre, gp_head,
                ['%s%s 가장 높은 자리에 있습니다.' % (name, josa(name, '이', '가')),
                 '이 지역이 도내 1위입니다.',
                 '%s%s 맨 윗줄입니다.' % (name, josa(name, '은', '는')),
                 '이곳이 정점입니다.']))
        elif sido_rank <= 3:
            pC1.append(CC('gap-hi', gp_pre, gp_head,
                ['이 지역은 %s 번째로 높은 상위권입니다.' % kn(sido_rank),
                 '도내 %d위의 상위권에 해당합니다.' % sido_rank,
                 '%s%s 위에서 %s 번째입니다.' % (name, josa(name, '은', '는'), kn(sido_rank)),
                 '이곳은 %s 번째 자리를 차지합니다.' % kn(sido_rank)]))
        elif sido_rank <= (n_sibs + 1) // 2:
            pC1.append(CC('gap-mid', gp_pre, gp_head,
                ['이 지역의 도내 순위는 %d위로 상위 절반에 듭니다.' % sido_rank,
                 '%s%s %d위, 중상위권입니다.' % (name, josa(name, '은', '는'), sido_rank),
                 '순위로는 도내 %d위에 해당합니다.' % sido_rank,
                 '이곳의 자리는 %d위, 위쪽 절반입니다.' % sido_rank]))
        else:
            pC1.append(CC('gap-lo', gp_pre, gp_head,
                ['이 지역의 도내 순위는 %d위로 아래쪽입니다.' % sido_rank,
                 '%s%s %d위라 금액보다 접수 상황이 더 중요한 편입니다.' % (name, josa(name, '은', '는'), sido_rank),
                 '순위 자체는 도내 %d위로 낮은 축입니다.' % sido_rank,
                 '이곳은 %d위로 하위권에 놓입니다.' % sido_rank]))
    # 도내 잔여 규모 순위 (실측 — 마감 여부와 무관한 수치 비교)
    if n_sibs > 2 and left is not None and status:
        lefts = sorted(((status['data'].get(k) or {}).get('left') or 0)
                       for k, _ in (sibs or [])) if sibs else []
        if lefts:
            l_rank = sum(1 for x in lefts if x > (left or 0)) + 1
            lw = ('큰 축' if l_rank <= max(1, n_sibs // 4) else
                  '중상위' if l_rank <= n_sibs // 2 else
                  '중하위' if l_rank <= n_sibs * 3 // 4 else '작은 축')
            pC1.append(CC('leftrank',
                ['', '잔여 숫자만 놓고 보면 ', '수치 비교를 하나 더 하면 '],
                ['도내 %d개 시·군 가운데 잔여 규모는 %d번째로 ' % (n_sibs, l_rank),
                 '잔여 수치의 도내 서열은 %d위(%d곳 중)로 ' % (l_rank, n_sibs),
                 '남은 수치 기준 도내 %d위여서 ' % l_rank],
                ['%s에 속합니다(마감 공지 여부와는 별개).' % lw,
                 '%s의 물량 규모입니다(접수 가능 여부는 공지 기준).' % lw,
                 '%s입니다 — 실제 접수 가능성은 공지로 확인해야 합니다.' % lw]))
    if n_sibs > 1:
        if ties:
            tie_txt = '·'.join(ties[:3]) + (' 등' if len(ties) > 3 else '')
            pC1.append(CC('tie',
                ['같은 상한(%s만원)을 쓰는 시·군이 도내에 %s 더 있는데(%s), ' % (maxP, knu(len(ties), '곳'), tie_txt),
                 '도내 %s(%s)이 같은 %s만원 상한을 공유하는데, ' % (knu(len(ties), '곳'), tie_txt, maxP),
                 '%s도 같은 %s만원 상한을 쓰는 이웃이라 ' % (tie_txt, maxP),
                 ],
                ['이들과는 금액이 아니라 물량·마감 상황으로 갈립니다.',
                 '차이는 접수 상황에서 나는 셈입니다.',
                 '표만 보면 구분이 없지만 잔여 흐름은 제각각입니다.']))
        elif above and below:
            pC1.append(CC('nbr',
                ['도내에서 바로 위 상한은 %s(%s만원), 바로 아래는 %s(%s만원)로 '
                 % (above[1], fmt(above[0]), below[1], fmt(below[0])),
                 '상한 순서상 이웃은 위로 %s(%s만원), 아래로 %s(%s만원)이며 '
                 % (above[1], fmt(above[0]), below[1], fmt(below[0])),
                 '%s(%s만원)와 %s(%s만원) 사이에 놓인 상한이라 '
                 % (above[1], fmt(above[0]), below[1], fmt(below[0]))],
                ['각각 %s만원·%s만원 차이입니다.' % (fmt(above[0] - my_p), fmt(my_p - below[0])),
                 '위와는 %s만원, 아래와는 %s만원 벌어져 있습니다.' % (fmt(above[0] - my_p), fmt(my_p - below[0])),
                 '위아래 격차는 %s만원과 %s만원입니다.' % (fmt(above[0] - my_p), fmt(my_p - below[0]))]))
        elif below:
            pC1.append(CC('nbr-top',
                ['도내에서 %s보다 상한이 높은 곳은 없고, ' % name,
                 '%s 상한으로는 %s%s 도내 최고이고, ' % (maxP + '만원', name, josa(name, '이', '가')),
                 '이보다 높은 상한은 도내에 없으며, '],
                ['다음인 %s(%s만원)와 %s만원 차이입니다.' % (below[1], fmt(below[0]), fmt(my_p - below[0])),
                 '2위 %s(%s만원)를 %s만원 앞섭니다.' % (below[1], fmt(below[0]), fmt(my_p - below[0])),
                 '바로 아래 %s(%s만원)와의 격차는 %s만원입니다.' % (below[1], fmt(below[0]), fmt(my_p - below[0]))]))
        elif above:
            pC1.append(CC('nbr-bot',
                ['도내에서 이보다 낮은 상한은 없으며, ',
                 '상한으로는 도내에서 가장 낮은 쪽이고, ',
                 '%s%s 도내 최하위 상한이라 ' % (name, josa(name, '은', '는'))],
                ['바로 위 %s(%s만원)와는 %s만원 차이입니다.' % (above[1], fmt(above[0]), fmt(above[0] - my_p)),
                 '한 계단 위 %s(%s만원)보다 %s만원 적습니다.' % (above[1], fmt(above[0]), fmt(above[0] - my_p)),
                 '%s(%s만원)와의 격차가 %s만원입니다.' % (above[1], fmt(above[0]), fmt(above[0] - my_p))]))
        if open_sib:
            pC1.append(CC('opensib',
                ['', '도내로 눈을 넓히면, ', '이 지역과 별개로, ', '주변까지 살피면, '],
                ['%s에서 마감 공지 없이 잔여가 가장 많이 남은 곳은 ' % sido_full,
                 '같은 도 안에서 공지상 마감 없이 잔여 최다인 지역은 ',
                 '%s 기준 마감 공지가 확인되지 않으면서 잔여가 가장 많은 곳은 ' % sido_full,
                 '마감 공지 없이 잔여를 가장 많이 쥔 도내 지역은 '],
                ['%s(%s대)입니다.' % (open_sib[1], fmt(open_sib[0])),
                 '%s로 %s대가 남아 있습니다.' % (open_sib[1], fmt(open_sib[0])),
                 '%s(잔여 %s대)입니다.' % (open_sib[1], fmt(open_sib[0])),
                 '%s인데 %s대가 남은 것으로 집계됩니다.' % (open_sib[1], fmt(open_sib[0]))]))

    # ── C2 차종·전환 (WAV·미지원 차종은 최고액·비교 서술에서 제외) ──
    pC2 = []
    if best:
        c, tot = best
        pC2.append(CC('best',
            ['', '차종 단위로 내려가면 ', '모델별로는 '],
            ['이 지역에서 합계 보조금이 가장 큰 모델은 %s로, ' % c['name'],
             '합계 최고액은 %s 몫으로, ' % c['name'],
             '1위 모델은 %s이며, ' % c['name'],
             '가장 많이 받는 차는 %s로, ' % c['name']],
            ['국비 %s만원을 포함해 %s만원입니다.' % (fmt(c['nat']), fmt(tot)),
             '국비 %s만원에 지방비를 더한 %s만원입니다.' % (fmt(c['nat']), fmt(tot)),
             '합계 %s만원(국비 %s만원)입니다.' % (fmt(tot), fmt(c['nat'])),
             '합계로 %s만원을 받습니다.' % fmt(tot)]))
    if len(tops) >= 2:
        t1, t2 = tops[0], tops[1]
        g = t1[0] - t2[0]
        if g == 0:
            eq_n = sum(1 for tt, _, _ in tops if tt == t1[0])
            pC2.append(CC('top-tie',
                ['', '차종 간 우열을 따지면, ', '표의 윗줄을 보면, '],
                ['최상위는 %s를 포함한 %s 모델이 %s만원 동률이라 ' % (t1[1], knu(eq_n, '개'), fmt(t1[0])),
                 '%s 등 %s 모델이 같은 %s만원으로 맨 위를 나눠 가져 ' % (t1[1], knu(eq_n, '개'), fmt(t1[0])),
                 '1위 금액(%s만원)을 %s 모델이 공유해 ' % (fmt(t1[0]), knu(eq_n, '개')),
                 '꼭대기 금액 %s만원에 %s 모델이 나란히 있어 ' % (fmt(t1[0]), knu(eq_n, '개'))],
                ['금액만으로는 우열이 없습니다.',
                 '선택은 제원·출고 시점 몫입니다.',
                 '표에서 조건을 비교해 고르면 됩니다.',
                 '고르는 기준은 금액 밖에서 찾아야 합니다.']))
        elif g <= 30:
            pC2.append(CC('top-near',
                ['', '순위표를 보면 ', '경합 구도인데, '],
                ['2위 %s(%s만원)와의 격차는 %s만원에 그쳐 ' % (t2[1], fmt(t2[0]), fmt(g)),
                 '다음 순위 %s(%s만원)와 %s만원 차이뿐이라 ' % (t2[1], fmt(t2[0]), fmt(g)),
                 '%s(%s만원)가 %s만원 차로 바짝 붙어 ' % (t2[1], fmt(t2[0]), fmt(g)),
                 '%s(%s만원)와 근소한 %s만원 차라 ' % (t2[1], fmt(t2[0]), fmt(g))],
                ['사실상 최상위권이 몰려 있습니다.',
                 '상위 모델 간 금액 차이는 크지 않습니다.',
                 '어느 쪽을 골라도 금액 차는 작습니다.',
                 '금액보다 제원·출고 시점이 결정 변수입니다.']))
        else:
            pC2.append(CC('top-far',
                ['', '순위표를 보면 ', '격차 구도인데, '],
                ['2위 %s(%s만원)보다 %s만원 앞서 ' % (t2[1], fmt(t2[0]), fmt(g)),
                 '다음 순위 %s(%s만원)와 %s만원 벌어져 ' % (t2[1], fmt(t2[0]), fmt(g)),
                 '%s(%s만원)와의 격차가 %s만원이라 ' % (t2[1], fmt(t2[0]), fmt(g)),
                 '%s(%s만원)를 %s만원 차로 따돌려 ' % (t2[1], fmt(t2[0]), fmt(g))],
                ['1위 모델의 이점이 뚜렷합니다.',
                 '차종 선택이 금액에 크게 작용합니다.',
                 '격차가 분명한 분포입니다.',
                 '어떤 차를 고르느냐가 수령액을 좌우합니다.']))
        if len(tops) >= 3 and pick('%s:top3' % cd, [0, 1]) == 0:
            t3 = tops[2]
            pC2.append(CC('top3',
                ['상위 3개를 나열하면 ', '금액 순 상위 3개 모델은 ', '상위권을 늘어놓으면 '],
                ['%s(%s만원)·%s(%s만원)·%s(%s만원)'
                 % (t1[1], fmt(t1[0]), t2[1], fmt(t2[0]), t3[1], fmt(t3[0]))],
                [' 순입니다.', ' 순서입니다.', ' 차례입니다.']))
    pC2.append(CC('maxs',
        ['', '차급 변수도 있는데, ', '한 가지 예외로 ', '급이 다르면 상한도 달라서 '],
        ['경·소형 전기승용은 별도 상한이 적용돼 ',
         '차급이 경·소형이면 상한이 따로 잡혀 ',
         '경형·소형 모델 기준으로는 ',
         '경·소형 승용을 본다면 '],
        ['최대 %s만원까지입니다.' % fmt(r.get('maxS')),
         '%s만원이 한도입니다.' % fmt(r.get('maxS')),
         '상한 %s만원으로 계산해야 합니다.' % fmt(r.get('maxS')),
         '%s만원 상한이 적용됩니다.' % fmt(r.get('maxS'))]))
    cn = fmt(meta.get('convNatMax', 100))
    if conv_max > 0:
        pC2.append(CC('conv',
            ['기존 내연기관차를 폐차·처분하고 전환하는 경우 ',
             '내연차를 정리하고 넘어오는 구매라면 ',
             '폐차·처분을 동반한 전환 구매에는 ',
             '내연기관차 처분 후 전환 조건이면 '],
            ['국비 최대 %s만원의 전환지원금이 추가되고 ' % cn,
             '전환지원금이 국비 최대 %s만원 따로 붙고 ' % cn,
             '별도의 전환지원금(국비 최대 %s만원)이 있고 ' % cn],
            ['이 지역 지방비 몫은 차종에 따라 최대 %s만원입니다.' % fmt(conv_max),
             '지방비 전환지원금은 차종별 최대 %s만원까지 더해집니다.' % fmt(conv_max),
             '지방비 쪽은 최대 %s만원(차종별 상이)입니다.' % fmt(conv_max)]))
    else:
        pC2.append(CC('noconv',
            ['내연기관차 폐차·처분 후 전환 시에는 ',
             '내연차에서 갈아타는 경우라면 ',
             '전환 구매 조건이라면 '],
            ['국비 전환지원금(최대 %s만원)이 별도로 있으며 ' % cn,
             '국비 몫 전환지원금 최대 %s만원이 따로 있으며 ' % cn,
             '전환지원금 국비 최대 %s만원을 챙길 수 있으며 ' % cn],
            ['이 지역 지방비 전환 지원 여부는 공고문으로 확인해야 합니다.',
             '지방비 쪽 전환 지원은 데이터에 잡히지 않아 공고 확인이 필요합니다.',
             '지방비 전환 지원은 공고문 기준입니다.']))

    # ── E 유형별 배정 (실데이터 분해 + 해석) ──
    pE = []
    dn = (st.get('d') or {}).get('n')
    dl = (st.get('d') or {}).get('left')
    if dn and dl:
        lab = ['우선순위', '법인·기관', '택시', '일반']
        alloc = ' · '.join('%s %s대' % (lab[i], fmt(dn[i])) for i in range(4) if dn[i] is not None)
        remain = ' · '.join('%s %s대' % (lab[i], fmt(dl[i])) for i in range(4) if dl[i] is not None)
        pE.append(CC('alloc',
            ['', '유형별 현황도 봐 두세요: ', '물량 배정표를 펼치면 ', '칸을 나눠 보면 '],
            ['신청 유형별 배정은 %s이고 ' % alloc,
             '물량은 유형별로 나뉘어 %s로 배정돼 있고 ' % alloc,
             '유형 구분으로는 %s가 공고 물량이며 ' % alloc,
             '공고 기준 %s로 배정됐고 ' % alloc],
            ['유형별 잔여는 %s입니다.' % remain,
             '남은 물량은 %s로 집계됩니다.' % remain,
             '현재 잔여 분포는 %s입니다.' % remain,
             '잔여 쪽은 %s로 잡힙니다.' % remain]))
        pairs = [((dn[i] or 0), lab[i], i) for i in range(4) if dn[i] is not None]
        total_dn = sum(x for x, _, _ in pairs)
        if pairs and total_dn > 0:
            bx = max(pairs)
            share = bx[0] / total_dn
            stxt = ('전체의 3분의 2 이상' if share >= 0.66 else
                    '전체의 절반 이상' if share >= 0.5 else '가장 큰 비중')
            pE.append(CC('alloc-shape',
                ['', '이 가운데 ', '참고로 '],
                ['배정 구도상 ', '구성으로는 ', '몫을 따지면 ', '나눠 보면 '],
                ['%s 유형이 %s을 차지합니다.' % (bx[1], stxt),
                 '%s 물량이 %s을 가져갑니다.' % (bx[1], stxt),
                 '%s 쪽이 %s입니다.' % (bx[1], stxt),
                 '%s 칸이 %s으로 제일 큽니다.' % (bx[1], stxt)]))
        if dl[3] is not None:
            if (dl[3] or 0) > 0 and not (closed['closed'] and not closed['partial']):
                pE.append(CC('gen-left',
                    ['개인 일반 구매자 기준으로 보면 ', '일반 유형 칸에는 ',
                     '개인이라면 일반 물량 기준 ', '일반 물량 쪽에는 '],
                    ['잔여 %s대가 남아 있고 ' % fmt(dl[3]),
                     '%s대가 남은 것으로 잡히고 ' % fmt(dl[3]),
                     '남은 수치가 %s대이고 ' % fmt(dl[3]),
                     '%s대가 남은 상태이고 ' % fmt(dl[3])],
                    ['우대 대상이면 우선순위 물량도 함께 보면 됩니다.',
                     '해당 유형 잔여가 판단 기준이 됩니다.',
                     '내 유형의 칸을 보는 것이 정확합니다.',
                     '자기 유형 숫자를 기준으로 판단하면 됩니다.']))
            elif (dl[3] or 0) <= 0:
                which = [lab[i] for i in range(4) if (dl[i] or 0) > 0]
                if which:
                    wtxt = '·'.join(which)
                    pE.append(CC('gen-zero',
                        ['일반 물량 잔여는 0이고 ', '개인 일반 몫은 소진됐고 ', '일반 칸은 0으로 잡히고 '],
                        ['남아 있는 것은 %s 몫입니다.' % wtxt,
                         '잔여는 %s 유형에만 있습니다.' % wtxt,
                         '%s 쪽 수치만 남아 있습니다.' % wtxt]))
        pE.append(CC('alloc-tail',
            ['', '읽는 법 하나: ', '한 가지 주의로 ', '해석 팁을 덧붙이면 '],
            ['유형 합계는 ', '표의 유형 숫자는 ', '이 분해 값은 ', '유형별 칸의 수치는 '],
            ['회차 이월 때문에 전체 수치와 어긋날 수 있습니다.',
             '회차 구분 탓에 전체 합계와 다를 수 있습니다.',
             '이월분이 섞이면 전체와 안 맞을 수 있습니다.',
             '공고 회차가 나뉘면 전체와 차이 날 수 있습니다.',
             '공고가 여러 차수로 쪼개진 지역에서는 전체와 어긋나기도 합니다.',
             '이월 물량이 반영되는 시점에 따라 전체 수치와 달라질 수 있습니다.']))

    # ── F 안내 (선정 방식·연락처·서류·다음 확인 포인트·기준시각·출처) ──
    pF = []
    m = st.get('m') or ''
    if m:
        if '출고' in m:
            pF.append(CC('method-ship',
                ["이 지역의 선정 방식은 '%s'로, " % m,
                 "공고상 선정 기준은 '%s'인데, " % m,
                 "'%s' 방식이 적용되는 지역이라 " % m],
                ['신청 순서가 아니라 출고·등록 순서로 배정되므로 ',
                 '접수 순이 아닌 출고 순 배정이라 ',
                 '출고등록이 빠른 순서로 대상자가 정해져 '],
                ['출고가 빠른 차종·트림이 유리할 수 있습니다.',
                 '재고 있는 트림을 고르는 것이 실리적입니다.',
                 '계약 전 제조사에 출고 예정일부터 확인하는 것이 순서입니다.']))
        else:
            pF.append(CC('method',
                ['', '절차 쪽을 보면 ', '선정 규정으로는 '],
                ["이 지역의 선정 방식은 '%s'라 " % m,
                 "공고상 '%s' 방식으로 대상자를 정하므로 " % m,
                 "선정 기준이 '%s'로 안내돼 있어 " % m],
                ['방식에 따른 유불리는 공고문의 세부 기준으로 확인하세요.',
                 '내 조건에서의 순위는 공고문이 기준입니다.',
                 '세부 순위 규정은 원문 확인이 필요합니다.']))
    dept = r.get('dept') or ''
    tel = r.get('tel') or ''
    if dept and tel and not re.search(r'0000-?0000', tel):
        pF.append(CC('contact',
            ['', '문의 창구도 적어 두면, ', '확인이 필요할 때는, '],
            ['담당 부서는 %s(%s)이며 ' % (dept, tel),
             '문의는 %s(%s)로 하면 되고 ' % (dept, tel),
             '공고 담당은 %s(%s)인데 ' % (dept, tel)],
            ['공고 해석이 애매한 부분은 전화 확인이 가장 정확합니다.',
             '애매한 조항은 직접 물어보는 편이 빠릅니다.',
             '세부 자격 판단은 전화로 확정하는 것이 안전합니다.']))
    elif dept:
        pF.append(CC('contact-nophone',
            ['담당 부서는 %s이며 ' % dept,
             '문의처는 %s 쪽이고 ' % dept,
             '공고 담당은 %s인데 ' % dept],
            ['연락처는 ev.or.kr의 지자체 문의처 목록에서 확인할 수 있습니다.',
             '전화번호는 ev.or.kr 지자체 문의처 페이지에 있습니다.',
             '정확한 번호는 ev.or.kr 문의처에서 찾으면 됩니다.']))
    pF.append(CC('docs',
        ['', '서류 쪽 규칙도 중요한데, ', '절차 면에서는 '],
        ['신청 서류에는 출고예정일이 적힌 구매계약서가 들어가며 ',
         '구매계약이 먼저이고(신청서에 계약서 첨부) ',
         '계약서 없이 신청부터 할 수는 없고 '],
        ['거주요건 기준일은 계약일이 아니라 구매신청서 접수일입니다.',
         '주소지 요건은 구매신청서 접수일 기준으로 판정합니다.',
         '거주요건 판정일은 구매신청서 접수일이라는 점을 기억하세요.',
         '이사 예정자라면 구매신청서 접수일이 기준일이라는 점부터 확인해야 합니다.']))
    if closed['closed'] or (left is not None and left <= 0):
        pF.append(CC('next-closed',
            ['', '앞으로의 관전 포인트는 ', '이제 볼 것은 '],
            ['추가 공고(추경) 여부가 다음 확인 사항이라 ',
             '재공고 신호가 관건이라 ',
             '새 공고 모니터링이 핵심이라 '],
            ['잔여가 다시 늘거나 새 공고가 뜨면 이 페이지 상태도 함께 갱신됩니다.',
             '지자체 공지와 이 페이지의 잔여 수치를 함께 지켜보세요.',
             '잔여가 갑자기 늘면 추가 공고가 나왔다는 뜻으로 읽으면 됩니다.']))
    elif left is not None and left < 30:
        pF.append(CC('next-low',
            ['', '잔여가 적은 만큼 ', '막판 구간이라 '],
            ['신청 전 체크는 잔여 재확인 → 자격 요건(주민등록 주소지) → 접수 기간 순서로 ',
             '순서가 중요해서 잔여 재확인, 자격 확인, 출고 시점 확인을 마친 뒤 ',
             '접수 직전 잔여 확인과 출고 빠른 트림 선택이 사실상 승부처라 '],
            ['빠르게 움직이는 것이 좋습니다.',
             '바로 접수까지 이어가는 편이 안전합니다.',
             '지체 없이 진행하세요.']))
    else:
        pF.append(CC('next-open',
            ['', '신청 전에는 ', '준비 단계에서는 '],
            ['공고문에서 자격 요건과 접수 기간, 차량 출고 가능 시점을 함께 확인해야 하며 ',
             '자격 요건(주소지·보유 대수 등)과 접수 기간 확인이 먼저이며 ',
             '접수 기간·자격 요건·출고 기한 규정을 먼저 읽어 두는 것이 좋고 '],
            ['보조금은 주민등록 주소지 지자체 기준으로 신청합니다.',
             '신청 접수는 주민등록 주소지 지자체에 합니다.',
             '신청처는 주민등록상 주소지 지자체입니다.']))
    upd = updated.replace('T', ' ')
    pF.append(CC('stamp',
        ['', '끝으로 ', '덧붙이면 '],
        ['이 문단의 수치는 %s 수집 기준이며 ' % upd,
         '수치 기준 시각은 %s이고 ' % upd,
         '위 수치는 %s에 수집된 값이며 ' % upd,
         '본 안내의 기준 시각은 %s이며 ' % upd],
        ['페이지를 열면 접속 시점 데이터로 갱신됩니다.',
         '접속 시점의 최신 수치를 페이지가 다시 불러옵니다.',
         '화면의 뱃지·잔여는 열람 시점 기준으로 갱신됩니다.',
         '뱃지와 잔여 대수는 접속 시점 데이터로 덧씌워집니다.']))
    note = (st.get('note') or '').strip()
    if not note:
        # 공지 원문이 없는 지역 — 데이터 출처·검증 문단으로 보강 (정직한 자동화 공개)
        pF.append(CC('prov',
            ['', '출처를 밝혀 두면, ', '참고로 '],
            ['%s%s ev.or.kr에 공지 원문이 등록돼 있지 않은 지역이라 ' % (name, josa(name, '은', '는')),
             '이 지역은 무공해차 통합누리집에 별도 공지문이 올라와 있지 않아 ',
             '누리집에 등록된 공지 원문이 없어 공고 전문은 싣지 못했으니 '],
            ['접수 기간·세부 자격 같은 공고 상세는 지자체 채널에서 확인해야 합니다.',
             '접수 일정·서류 등 세부는 지자체 홈페이지나 전화로 확인하세요.',
             '자세한 일정과 요건은 지자체 공고문이 기준입니다.']))
    elif len(note) < 200:
        # 짧은 공지 지역 — '공지 없음'이 아니라 '짧다'는 사실만 서술
        pF.append(CC('shortnote',
            ['', '한 가지 덧붙이면, ', '참고로 '],
            ['누리집에 게시된 공지가 %s자 분량으로 짧아 ' % fmt(len(note)),
             '이 지역 공지문은 비교적 간단한 편이라 ',
             '게시된 공지 원문이 짧아 '],
            ['접수 기간·서류 같은 세부까지는 담겨 있지 않을 수 있으니 지자체 공고문을 함께 확인하세요.',
             '세부 조건은 지자체 홈페이지·전화로 보완 확인하는 편이 안전합니다.',
             '상세 요건은 원 공고문 확인이 필요합니다.']))

    # ── 문단 조립 — 순서·구성 시드 가변(필수 정보는 전 페이지 유지) ──
    mids = [b for b in
            [[pB, pC1, pC2, pE][i] for i in
             pick('%s:order' % cd, [(0, 1, 2, 3), (0, 2, 1, 3), (1, 0, 2, 3), (0, 1, 3, 2),
                                    (2, 0, 1, 3), (1, 2, 0, 3), (0, 3, 1, 2), (2, 1, 0, 3)])]
            if b]
    paras = [' '.join(pA)] + [' '.join(b) for b in mids] + [' '.join(pF)]
    return [esc(p) for p in paras]


# ══════════════════════════════════════════════════════════
#  car 페이지
# ══════════════════════════════════════════════════════════
_MODEL_RULES = [
    (re.compile(r'아이오닉\s?5'), '아이오닉5'), (re.compile(r'아이오닉\s?6'), '아이오닉6'),
    (re.compile(r'아이오닉\s?9|아이오닉9'), '아이오닉9'),
    (re.compile(r'EV3', re.I), 'EV3'), (re.compile(r'EV4', re.I), 'EV4'), (re.compile(r'EV5', re.I), 'EV5'),
    (re.compile(r'EV6', re.I), 'EV6'), (re.compile(r'EV9', re.I), 'EV9'), (re.compile(r'PV5', re.I), 'PV5'),
    (re.compile(r'코나'), '코나 일렉트릭'), (re.compile(r'캐스퍼'), '캐스퍼 일렉트릭'),
    (re.compile(r'레이'), '레이 EV'), (re.compile(r'니로', re.I), '니로 EV'), (re.compile(r'스타리아'), '스타리아 일렉트릭'),
    (re.compile(r'GV60', re.I), 'GV60'), (re.compile(r'GV70', re.I), 'GV70'), (re.compile(r'G80', re.I), 'G80'),
    (re.compile(r'Model 3', re.I), '모델3'), (re.compile(r'Model Y', re.I), '모델Y'),
    (re.compile(r'EQA', re.I), 'EQA'), (re.compile(r'EQB', re.I), 'EQB'), (re.compile(r'EX30', re.I), 'EX30'),
    (re.compile(r'토레스'), '토레스 EVX'),
    (re.compile(r'ID\.4', re.I), 'ID.4'), (re.compile(r'ID\.5', re.I), 'ID.5'),
    (re.compile(r'Q4', re.I), 'Q4 e-tron'), (re.compile(r'Q6', re.I), 'Q6 e-tron'),
    (re.compile(r'Countryman', re.I), 'MINI 컨트리맨'), (re.compile(r'Aceman', re.I), 'MINI 에이스맨'),
    (re.compile(r'Cooper|JCW', re.I), 'MINI 쿠퍼'),
    (re.compile(r'iX1', re.I), 'iX1'), (re.compile(r'iX2', re.I), 'iX2'), (re.compile(r'iX3', re.I), 'iX3'),
    (re.compile(r'i4', re.I), 'i4'), (re.compile(r'i5', re.I), 'i5'),
    (re.compile(r'ATTO', re.I), 'BYD 아토3'), (re.compile(r'DOLPHIN', re.I), 'BYD 돌핀'),
    (re.compile(r'SEALION', re.I), 'BYD 씨라이언7'), (re.compile(r'SEAL', re.I), 'BYD 씰'),
]


def model_group(c):
    for rex, g in _MODEL_RULES:
        if rex.search(c['name']):
            return g
    return c['name'].replace('(단종)', '').strip()


def build_car(car, cars, regions, meta, status, ctx):
    cid = car['id']
    name = car['name']
    # 색인은 모델그룹 대표 트림만 — 트림 변형(19/20인치 등)끼리는 근사중복이라 심사·검색 표면에서 제외.
    # 페이지 자체는 전 트림 생성·상호링크 유지(이용자 탐색·비교 기능은 그대로).
    noindex = bool(car['disc']) or cid not in ctx.get('car_rep', set())
    maker = MAKER_SHORT.get(car['maker'], car['maker'])
    eff = round(car['range'] / car['batt'], 1) if car.get('range') and car.get('batt') else None
    cr = round(car['rangeCold'] / car['range'] * 100) if car.get('range') and car.get('rangeCold') else None

    # 지역별 합계 (9999 제외)
    rows = []
    for k, r in regions.items():
        if k == '9999':
            continue
        v = car_v(r, cid)
        if not v:
            continue
        rows.append((k, r, v[0], car['nat'] + v[0]))
    rows.sort(key=lambda x: (-x[3], x[1]['name']))
    # 상위 표는 5행만 정적 노출(전체는 detail.js 확장) — 전 차종 유사 순위표의 반복 footprint 축소
    trs = ['<tr><td><a href="/region/%s.html" style="color:inherit;font-weight:700">%s</a>'
           '<div class="small muted">%s</div></td><td class="num">%s</td>'
           '<td class="num" style="font-weight:800;color:var(--money)">%s</td></tr>'
           % (k, esc(r['name']), esc(r.get('sido', '')), fmt(loc), fmt(tot))
           for k, r, loc, tot in rows[:5]]

    # 시도별 요약 — 이 차종의 시도 단위 합계 분포(차종마다 값이 다른 실질 요약)
    by_sido = {}
    for k, r, loc, tot in rows:
        by_sido.setdefault(r.get('sido', ''), []).append((k, r, tot))
    sido_trs = []
    for sido, items in sorted(by_sido.items(), key=lambda x: -max(t for _, _, t in x[1])):
        top_k, top_r, top_t = max(items, key=lambda x: x[2])
        lo = min(t for _, _, t in items)
        rng = ('%s만원' % fmt(top_t)) if lo == top_t else ('%s만~%s만원' % (fmt(lo), fmt(top_t)))
        slug = SIDO_SLUG.get(sido)
        sido_cell = ('<a href="/sido/%s.html" style="color:inherit;font-weight:700">%s</a>' % (slug, esc(SIDO_FULL.get(sido, sido)))
                     if slug else '<b>%s</b>' % esc(SIDO_FULL.get(sido, sido)))
        sido_trs.append('<tr><td>%s</td><td class="num">%d</td><td class="num">%s</td>'
                        '<td class="small"><a href="/region/%s.html" style="color:inherit">%s</a> %s만원</td></tr>'
                        % (sido_cell, len(items), rng, top_k, esc(top_r['name']), fmt(top_t)))
    tots_all = sorted(t for _, _, _, t in rows)
    if tots_all:
        mid = (tots_all[len(tots_all) // 2] if len(tots_all) % 2
               else round((tots_all[len(tots_all) // 2 - 1] + tots_all[len(tots_all) // 2]) / 2))
        dist_line = ('%s 기준 전국 %d개 지역 합계: 중앙값 %s만원 · 평균 %s만원 · 범위 %s만~%s만원'
                     % (esc(name), len(tots_all), fmt(mid), fmt(round(sum(tots_all) / len(tots_all))),
                        fmt(tots_all[0]), fmt(tots_all[-1])))
    else:
        dist_line = ''

    prose = car_prose(car, cars, rows, eff, cr, meta, status, ctx)
    prose_html = ''.join('<p style="line-height:1.75;margin:10px 0">%s</p>' % p for p in prose)

    specs = ('<div class="kv"><span>1회 충전 주행거리 (상온)</span><b>%s</b></div>'
             '<div class="kv"><span>1회 충전 주행거리 (저온·겨울)</span><b>%s</b></div>'
             '<div class="kv"><span>배터리 용량</span><b>%s</b></div>'
             '<div class="kv"><span>추정 전비 <span class="notice-badge">주행거리÷배터리</span></span><b>%s</b></div>'
             % ('%s km' % car['range'] if car.get('range') else '미공개',
                '%s km' % car['rangeCold'] if car.get('rangeCold') else '미공개',
                '%s kWh' % car['batt'] if car.get('batt') else '미공개',
                '%s km/kWh' % eff if eff else '-'))
    if cr:
        if cr >= 85:
            w_note = compose('car%d' % cid, 'wnote',
                             ['저온 효율이 좋은 편이라 ', '겨울 감소폭이 작은 축이라 ',
                              '유지율이 높은 그룹이라 ', '한파 내성이 좋은 쪽이라 '],
                             ['한파 주행에서도 부담이 덜합니다.', '동절기 실사용 격차가 작은 편입니다.',
                              '겨울 장거리에도 상대적으로 유리합니다.', '겨울 운용 스트레스가 덜한 모델입니다.'])
        elif cr >= 75:
            w_note = compose('car%d' % cid, 'wnote',
                             ['평균적인 유지율이라 ', '중간 수준의 겨울 성능이라 ',
                              '무난한 저온비여서 ', '유지율이 중간 지대라 '],
                             ['일반적인 통근 거리라면 무리가 없습니다.', '동급 대비 특이점은 없는 수준입니다.',
                              '통상 범위의 겨울 감소로 보면 됩니다.', '평균 수준의 동절기 감소를 예상하면 됩니다.'])
        else:
            w_note = compose('car%d' % cid, 'wnote',
                             ['겨울 감소폭이 큰 편이라 ', '저온 유지율이 낮은 축이라 ',
                              '한파에 민감한 그룹이라 ', '동절기 손실이 큰 쪽이라 '],
                             ['장거리 출퇴근이라면 저온값 기준으로 계산하세요.', '겨울 실주행은 저온 인증값으로 가늠해야 합니다.',
                              '동절기에는 여유 있는 충전 계획이 필요합니다.', '겨울 왕복 거리는 저온값으로 따져 보세요.'])
        winter = ('<div class="callout callout-warn small">❄️ 겨울(저온) 주행거리: 상온의 <b>%d%%</b> 수준'
                  ' <span class="small muted">(국내 인증값 기준)</span><br>%s</div>' % (cr, w_note))
    else:
        winter = '<div class="callout callout-warn small">저온 인증값 미공개 모델 — 겨울 주행거리 비교 불가</div>'

    # 같은 모델그룹 트림 (최대 6)
    grp = model_group(car)
    trims = [c for c in cars if c['id'] != cid and not c['disc'] and model_group(c) == grp][:6]
    trim_html = ''.join('<a class="row" href="/car/%d.html"><div class="grow"><div class="tit">%s</div>'
                        '<div class="desc">%skm · %skWh</div></div><div class="amt">국비 %s만원</div></a>'
                        % (c['id'], esc(c['name']), c.get('range') or '-', c.get('batt') or '-', fmt(c['nat']))
                        for c in trims) or '<p class="muted small" style="padding:10px 4px">등록된 형제 트림 없음</p>'

    disc_banner = ''
    if car['disc']:
        succ = ''.join(' <a href="/car/%d.html"><b>%s</b></a>' % (c['id'], esc(c['name'])) for c in trims[:3])
        disc_banner = ('<div class="callout callout-warn"><b>단종/이월 모델</b> — 2026년 신규 계약이 어려울 수 있는 모델입니다. '
                       '단가는 기록용으로 제공합니다.%s</div>'
                       % ((' 후속·현행 트림:' + succ) if succ else ' 같은 모델그룹의 현행 트림이 확인되지 않습니다.'))

    related = ['<a class="chip" href="price-tiers.html">💰 가격구간(기본가격) 바로 알기</a>',
               '<a class="chip" href="guide.html">📋 신청 절차 총정리</a>']
    if car.get('rangeCold'):
        related.append('<a class="chip" href="winter-range.html">❄️ 겨울 주행거리의 진실</a>')
    # 모델 시리즈 상호링크 — 발행 게이트를 통과해 실제 생성된 편만(미발행 시리즈로의 깨진 링크 금지)
    pub_slug = (ctx.get('model_pub') or {}).get(grp)
    if pub_slug:
        related.append('<a class="chip" href="model/%s.html">🔍 %s 보조금 심층 분석</a>' % (pub_slug, esc(grp)))

    canonical = '%s/car/%d.html' % (BASE, cid)
    ld = [{'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': '홈', 'item': BASE + '/'},
        {'@type': 'ListItem', 'position': 2, 'name': '%s 보조금' % name, 'item': canonical}]}]

    mapping = {
        'NAME': esc(name), 'ID': str(cid),
        'MAKER': esc(maker) + (' · 단종/이월 모델' if car['disc'] else ''),
        'SUB': '2026년 국비 %s만원 · 지역별 합계 %s만~%s만원' % (fmt(car['nat']),
                                                       fmt(rows[-1][3]) if rows else '-', fmt(rows[0][3]) if rows else '-'),
        'DISC_BANNER': disc_banner,
        'PROSE': prose_html,
        'AD1': '', 'AD2': '',
        'SPECS': specs,
        'WINTER': winter,
        'TABLE_SUB': '상위 %d개 / 전체 %d개 지역' % (min(5, len(rows)), len(rows)),
        'TABLE_ROWS': ''.join(trs),
        'SIDO_ROWS': ''.join(sido_trs),
        'DIST_LINE': dist_line,
        'REGION_COUNT': str(len(rows)),
        'TRIMS': trim_html,
        'RELATED': ''.join(related),
    }
    # 광고 게이트: app.js renderAds와 동일하게 정적 <main> 전체 텍스트 기준(1,200자)
    gate = len(strip_tags(render(ctx['tpl_car'], mapping)))
    mapping['AD1'] = ad_slot('car-1', gate, noindex)
    mapping['AD2'] = ad_slot('car-2', gate, noindex)
    main = render(ctx['tpl_car'], mapping)
    page = render(ctx['tpl_page'], {
        'TITLE': esc('%s 보조금 2026 — 국비 %s만원·지역별 합계 | EV보조금' % (name, fmt(car['nat']))),
        'DESC': esc('%s 2026년 전기차 보조금: 국비 %s만원, 지역별 국비+지방비 합계 %s만~%s만원. 주행거리 %skm(저온 %skm), 인증 제원과 트림 비교까지.'
                    % (name, fmt(car['nat']),
                       fmt(rows[-1][3]) if rows else '-', fmt(rows[0][3]) if rows else '-',
                       car.get('range') or '-', car.get('rangeCold') or '-')),
        'ROBOTS': '\n<meta name="robots" content="noindex">' if noindex else '',
        'CANONICAL': canonical,
        'JSONLD': jsonld_script(ld),
        'BREADCRUMB': '<a href="/">홈</a> › <a href="/car/%d.html">차종</a> › <b>%s</b>' % (cid, esc(name)),
        'MAIN': main,
        'META_UPDATED': esc(meta['updated']),
    })
    return page, gate


def car_prose(car, cars, rows, eff, cr, meta, status, ctx):
    cid = car['id']
    name = car['name']
    P = lambda slot, opts: pick('car%d:%s' % (cid, slot), opts)
    live = [c for c in cars if not c['disc']]
    grp = model_group(car)
    grp_n = sum(1 for c in live if model_group(c) == grp)

    CC = lambda slot, *parts: compose('car%d' % cid, slot, *parts)
    maker_short = MAKER_SHORT.get(car['maker'], car['maker'])
    maker_n = sum(1 for c in live if c['maker'] == car['maker'])

    # ── ① 스펙 서사 (동급 내 위치는 실측 분포 기준) ──
    p1 = []
    if maker_n > 1:
        p1.append(CC('makerctx',
            ['', '제조사 라인업으로 보면 ', '브랜드 단위로는 '],
            ['%s의 보조금 대상 현행 트림은 %d종이 등록돼 있고 ' % (maker_short, maker_n),
             '%s 이름으로는 %d개 트림이 보조금 목록에 올라 있고 ' % (maker_short, maker_n),
             '보조금 목록에서 %s 트림은 %d개가 잡히고 ' % (maker_short, maker_n)],
            ['이 페이지는 그중 %s를 다룹니다.' % name,
             '여기서는 %s 기준으로 정리합니다.' % name,
             '그 하나가 지금 보는 %s입니다.' % name]))
    if car.get('range'):
        ranges = sorted((c['range'] for c in live if c.get('range')), reverse=True)
        r_rank = ranges.index(car['range']) + 1 if car['range'] in ranges else None
        p1.append(CC('spec',
            ['', '핵심 제원부터 보면 ', '수치부터 확인하면 '],
            ['%s%s ' % (name, josa(name, '은', '는')),
             '%s의 경우 ' % name,
             '이 트림(%s)은 ' % name],
            ['1회 충전 주행거리(상온 인증)가 %skm인 전기승용입니다.' % fmt(car['range']),
             '상온 인증 기준 한 번 충전에 %skm를 달립니다.' % fmt(car['range']),
             '상온 주행거리 인증값이 %skm입니다.' % fmt(car['range']),
             '인증 주행거리 %skm(상온)를 확보한 모델입니다.' % fmt(car['range'])]))
        if r_rank:
            q = len(ranges)
            rword = ('상위권' if r_rank <= q // 4 or r_rank <= 3 else
                     '중상위' if r_rank <= q // 2 else
                     '중하위' if r_rank <= q * 3 // 4 else '하위권')
            p1.append(CC('specrank',
                ['이는 국내 보조금 대상 현행 %d개 모델 가운데 %d번째로, ' % (q, r_rank),
                 '주행거리만 놓고 보면 현행 %d개 모델 중 %d위라 ' % (q, r_rank),
                 '보조금 목록의 현행 %d개 모델과 견주면 %d위여서 ' % (q, r_rank)],
                ['%s에 해당하는 수치입니다.' % rword,
                 '거리 스펙으로는 %s입니다.' % rword,
                 '%s 자리에 놓입니다.' % rword]))
        if cr:
            crs = sorted((round(c['rangeCold'] / c['range'] * 100)
                          for c in live if c.get('range') and c.get('rangeCold')), reverse=True)
            med = crs[len(crs) // 2] if crs else None
            c_rank = (crs.index(cr) + 1) if crs and cr in crs else None
            pos = ('평균보다 좋은' if med and cr > med else
                   '평균 수준의' if med and cr == med else '평균보다 아쉬운')
            p1.append(CC('cold',
                ['겨울(저온) 인증 주행거리는 %skm로 상온의 %d%%인데, ' % (fmt(car['rangeCold']), cr),
                 '저온에서는 %skm까지 줄어 상온 대비 %d%%를 유지하는데, ' % (fmt(car['rangeCold']), cr),
                 '한파 기준 저온 인증값은 %skm(상온의 %d%%)로, ' % (fmt(car['rangeCold']), cr)],
                ['전체 모델 저온비 중앙값(%d%%)과 비교하면 %s 편입니다.' % (med or 0, pos),
                 '현행 모델 중앙값 %d%% 대비 %s 성적입니다.' % (med or 0, pos),
                 '중앙값이 %d%%이니 %s 쪽입니다.' % (med or 0, pos)]))
            if c_rank:
                cw = ('강한' if c_rank <= len(crs) // 4 or c_rank <= 3 else
                      '무난한' if c_rank <= len(crs) * 3 // 4 else '취약한')
                p1.append(CC('coldrank',
                    ['저온 유지율로 줄을 세우면 ', '겨울 성능 순위로는 ', '유지율 기준 서열은 '],
                    ['%d개 모델 중 %d위로 ' % (len(crs), c_rank),
                     '저온비 집계 %d개 가운데 %d번째로 ' % (len(crs), c_rank),
                     '%d위(%d개 모델 중)라 ' % (c_rank, len(crs))],
                    ['겨울에 %s 축입니다.' % cw,
                     '한파 대응이 %s 편입니다.' % cw,
                     '동절기 감소 내성은 %s 그룹입니다.' % cw]))
            dloss = car['range'] - car['rangeCold']
            p1.append(CC('colddiff',
                ['', '체감으로 환산하면, ', '거리로 옮기면, '],
                ['상온과 저온의 차이는 한 번 충전당 %skm라 ' % fmt(dloss),
                 '겨울에는 충전 한 번에 %skm가 사라지는 셈이라 ' % fmt(dloss),
                 '저온 손실분이 %skm에 이르러 ' % fmt(dloss)],
                ['겨울 왕복 동선이 길다면 이 수치로 계산해야 합니다.',
                 '동절기 주행 계획은 저온값 기준이 안전합니다.',
                 '한파철에는 충전 주기가 그만큼 짧아집니다.']))
    else:
        p1.append(P('nospec', [
            '%s%s 인증 주행거리·배터리 용량이 아직 공개되지 않은 모델입니다. 인증값은 공개되는 대로 무공해차 통합누리집(ev.or.kr)에 게시되며, 이 페이지에도 매일 반영됩니다. 겨울철 실사용 감각은 저온 인증값(상온 대비 비율)이 좌우하므로, 구매 결정 전에 공개 여부를 확인하는 것이 좋습니다.' % (name, josa(name, '은', '는')),
            '%s의 주행거리·배터리 인증값은 아직 데이터에 잡히지 않습니다. 보조금 단가는 확정되어 있지만 제원 비교는 어려운 상태이니, 인증값이 게시되는 ev.or.kr 공개 시점을 확인하세요. 특히 저온(겨울) 주행거리는 모델별 편차가 커서 확인 없이 계약하지 않는 편이 안전합니다.' % name,
            '제원 인증값이 미공개인 모델입니다(%s). 상온·저온 주행거리와 배터리 용량이 공개되면 이 페이지에 자동 반영됩니다. 그 전까지는 판매사에 인증 진행 상황과 출고 예정 시점을 함께 확인하는 것을 권합니다.' % name,
        ]))
    if eff:
        effs = sorted((round(c['range'] / c['batt'], 1) for c in live
                       if c.get('range') and c.get('batt')), reverse=True)
        e_rank = (effs.index(eff) + 1) if eff in effs else None
        p1.append(CC('eff',
            ['', '전비 감각으로는 ', '효율 쪽을 보면 '],
            ['배터리 용량은 %skWh이고 ' % car['batt'],
             '%skWh 배터리를 얹어 ' % car['batt'],
             '배터리 %skWh 기준으로 ' % car['batt']],
            ['주행거리를 용량으로 나눈 추정 전비는 %skm/kWh입니다(충전 손실 제외).' % eff,
             '추정 전비가 %skm/kWh 수준입니다(주행거리÷용량).' % eff,
             '전비는 대략 %skm/kWh로 추정됩니다.' % eff]))
        if e_rank:
            ew = ('효율이 좋은' if e_rank <= len(effs) // 3 else
                  '중간 효율의' if e_rank <= len(effs) * 2 // 3 else '효율보다 다른 강점을 볼')
            p1.append(CC('effrank',
                ['이 추정 전비는 현행 %d개 모델 중 %d위로 ' % (len(effs), e_rank),
                 '전비 순위로는 %d개 가운데 %d번째라 ' % (len(effs), e_rank),
                 '효율 서열 %d위(%d개 중)여서 ' % (e_rank, len(effs))],
                ['%s 자리입니다.' % ew,
                 '%s 그룹에 듭니다.' % ew,
                 '%s 위치입니다.' % ew]))
        p1.append(CC('per100',
            ['', '같은 값을 뒤집으면 ', '단위를 바꿔 보면 '],
            ['100km를 달리는 데 약 %skWh를 쓰는 셈이라 ' % round(100 / eff, 1),
             '100km당 소요 전력이 약 %skWh 꼴이라 ' % round(100 / eff, 1),
             '100km 기준 약 %skWh가 드는 수준이라 ' % round(100 / eff, 1)],
            ['충전기 요금표와 바로 대조해 볼 수 있습니다.',
             '충전 단가만 알면 주행비 감이 잡힙니다.',
             '완속·급속 단가를 곱해 보면 유지비가 나옵니다.']))
        kwh = 15000 / eff * 1.1
        cost = int(kwh * (150 * 0.6 + 350 * 0.4))
        p1.append(CC('fuel',
            ['', '유지비 감각을 잡자면, ', '거칠게 계산하면, '],
            ['연 15,000km를 집밥 60%(150원/kWh)·급속 40%(350원/kWh), 충전 손실 10% 가정으로 달리면 ',
             '같은 전비로 연 15,000km(완속 6:급속 4, 손실 10% 가정)를 달리면 ',
             '연 15,000km 기준(완속 150원·급속 350원/kWh 6:4 혼합, 손실 10%)으로 '],
            ['전기요금은 연 약 %s원으로 계산됩니다.' % fmt(round(cost, -3)),
             '충전비는 연 약 %s원 수준입니다.' % fmt(round(cost, -3)),
             '연간 충전비가 약 %s원으로 추산됩니다.' % fmt(round(cost, -3))]))
    grp_trims = [c for c in live if c['id'] != cid and model_group(c) == grp]
    if grp_n == 1:
        p1.append(CC('solo',
            ['', '트림 구성으로는 ', '라인업상 '],
            ['현행 보조금 목록에서 %s 계열은 이 트림 하나뿐이라 ' % grp,
             '%s%s 목록상 단일 트림으로 등록돼 있어 ' % (name, josa(name, '은', '는')),
             '이 모델은 계열 내 대체 트림이 없어 '],
            ['트림 간 비교 없이 이 사양이 기준이 됩니다.',
             '사양 선택의 여지는 없는 셈입니다.',
             '구매 검토는 이 사양 그대로를 놓고 하면 됩니다.']))
    if grp_n > 1:
        p1.append(CC('family',
            ['', '계열 안에서 보면 ', '트림 구성으로는 '],
            ['이 차는 %s 계열 %d개 트림 중 하나라 ' % (grp, grp_n),
             '%s 계열에는 현행 트림이 %d개 있어 ' % (grp, grp_n),
             '같은 %s 그룹의 트림이 총 %d개이므로 ' % (grp, grp_n)],
            ['트림에 따라 주행거리·배터리·보조금이 조금씩 다릅니다.',
             '아래 트림 목록에서 사양 차이를 비교할 수 있습니다.',
             '형제 트림도 함께 보는 것을 권합니다.']))
        grp_rngs = [c['range'] for c in [car] + grp_trims if c.get('range')]
        if grp_n > 2 and len(grp_rngs) >= 2 and min(grp_rngs) != max(grp_rngs):
            p1.append(CC('groupspan',
                ['', '폭을 재 보면 ', '계열 전체로는 '],
                ['이 계열의 인증 주행거리는 %s~%skm에 걸쳐 있어 ' % (fmt(min(grp_rngs)), fmt(max(grp_rngs))),
                 '트림별 주행거리가 %skm부터 %skm까지 벌어져 ' % (fmt(min(grp_rngs)), fmt(max(grp_rngs))),
                 '계열 내 거리 스펙 폭이 %s~%skm라 ' % (fmt(min(grp_rngs)), fmt(max(grp_rngs)))],
                ['어느 트림이냐에 따라 체감이 꽤 달라집니다.',
                 '트림 선택이 실사용 거리를 좌우합니다.',
                 '같은 이름이라도 스펙 확인이 필요합니다.']))
        # 형제 트림 실명 비교 — 주행거리가 가장 가까운 트림과의 실측 차
        cmpds = [c for c in grp_trims if c.get('range')] if car.get('range') else []
        if cmpds:
            tt = min(cmpds, key=lambda c: (abs(c['range'] - car['range']), c['id']))
            dr = car['range'] - tt['range']
            dnat = car['nat'] - tt['nat']
            if dr == 0:
                rtxt = ['주행거리 인증값이 같고 ', '거리 스펙은 동일하고 ', '인증 거리에서는 차이가 없고 ']
            elif dr > 0:
                rtxt = ['주행거리가 %skm 더 길고 ' % fmt(dr),
                        '한 번 충전에 %skm를 더 가고 ' % fmt(dr),
                        '거리에서 %skm 앞서고 ' % fmt(dr)]
            else:
                rtxt = ['주행거리가 %skm 짧은 대신 ' % fmt(-dr),
                        '거리에서는 %skm 뒤지지만 ' % fmt(-dr),
                        '인증 거리가 %skm 덜 나오고 ' % fmt(-dr)]
            if dnat == 0:
                ntxt = ['국비는 %s만원으로 같습니다.' % fmt(car['nat']),
                        '국비 몫은 동일한 %s만원입니다.' % fmt(car['nat']),
                        '국비 차이는 없습니다(각 %s만원).' % fmt(car['nat'])]
            elif dnat > 0:
                ntxt = ['국비는 %s만원 더 받습니다.' % fmt(dnat),
                        '국비 몫이 %s만원 큽니다.' % fmt(dnat),
                        '국비에서 %s만원 유리합니다.' % fmt(dnat)]
            else:
                ntxt = ['국비는 %s만원 적습니다.' % fmt(-dnat),
                        '국비 몫이 %s만원 작습니다.' % fmt(-dnat),
                        '국비에서는 %s만원 불리합니다.' % fmt(-dnat)]
            p1.append(CC('trimcmp',
                ['가장 가까운 형제 트림인 %s와 견주면 ' % tt['name'],
                 '비교 대상으로 자주 묶이는 %s 대비 ' % tt['name'],
                 '계열 내 이웃인 %s와의 차이는, ' % tt['name']],
                rtxt, ntxt))

    # ── ② 보조금 (지역별 최고/최저 실명 — WAV류는 별도 안내) ──
    p2 = []
    p2.append(CC('nat',
        ['', '금액으로 넘어가면 ', '보조금부터 보면 ', '지원액 쪽을 보면 '],
        ['2026년 국비 보조금은 ', '이 차의 2026년 국비 지원액은 ',
         '국비 기준 지원액은 ', '올해 국비 몫은 '],
        ['%s만원입니다.' % fmt(car['nat']),
         '%s만원으로 책정돼 있습니다.' % fmt(car['nat']),
         '%s만원(전국 동일)입니다.' % fmt(car['nat']),
         '%s만원이 기준입니다.' % fmt(car['nat'])]))
    nm = meta.get('natMax')
    if nm and car.get('nat') is not None:
        nshare = round(car['nat'] / nm * 100)
        if car['nat'] >= nm:
            p2.append(CC('natshare',
                ['', '기준점과 견주면 ', '위치를 짚으면 '],
                ['이는 올해 국비 상한(%s만원)을 꽉 채운 금액이라 ' % fmt(nm),
                 '국비 상한 %s만원을 그대로 받는 트림이라 ' % fmt(nm),
                 '올해 국비 최고액(%s만원)에 해당해 ' % fmt(nm)],
                ['국비 몫에서는 더 받을 여지가 없습니다.',
                 '국비 기준으로는 최상단입니다.',
                 '차이는 지방비에서만 납니다.']))
        else:
            p2.append(CC('natshare',
                ['', '기준점과 견주면 ', '위치를 짚으면 '],
                ['이는 올해 국비 상한(%s만원)의 약 %d%% 수준이라 ' % (fmt(nm), nshare),
                 '국비 상한 %s만원 대비 약 %d%%에 해당해 ' % (fmt(nm), nshare),
                 '올해 국비 최고액(%s만원)과 견주면 약 %d%%라 ' % (fmt(nm), nshare)],
                ['상한 만액 트림과는 국비 몫부터 차이가 납니다.',
                 '가격 구간·성능 계수의 영향이 반영된 금액입니다.',
                 '만액 지원 모델 대비 낮게 잡힌 편입니다.']))
    if len(rows) >= 6:
        hi3 = rows[:3]
        lo3 = rows[-3:]
        tots = [t for _, _, _, t in rows]
        avg = round(sum(tots) / len(tots))
        med = sorted(tots)[len(tots) // 2]
        hi_txt = '·'.join('%s %s만원' % (r['name'], fmt(t)) for _, r, _, t in hi3)
        lo_txt = '·'.join('%s %s만원' % (r['name'], fmt(t)) for _, r, _, t in lo3)
        p2.append(CC('hilo',
            ['', '어디 사는지에 따라 갈리는데, ', '지역 변수로는, '],
            ['지방비는 주소지 지자체마다 달라 합계 기준 상위 3곳은 %s이고, ' % hi_txt,
             '합계가 가장 큰 쪽은 %s이며, ' % hi_txt,
             '많이 주는 3곳을 꼽으면 %s이고, ' % hi_txt,
             '지역 격차의 상단에는 %s이 있고, ' % hi_txt],
            ['하위 3곳은 %s입니다.' % lo_txt,
             '가장 작은 쪽은 %s입니다.' % lo_txt,
             '반대편에는 %s이 놓입니다.' % lo_txt,
             '바닥권은 %s입니다.' % lo_txt]))
        p2.append(CC('avg',
            ['', '분포로 보면 ', '전국 단위로는 ', '평균선을 그어 보면 '],
            ['%d개 지자체의 이 차종 합계 평균은 약 %s만원이고 ' % (len(rows), fmt(round(avg, -1))),
             '%d개 지역 평균이 약 %s만원이며 ' % (len(rows), fmt(round(avg, -1))),
             '평균 합계는 약 %s만원(%d개 지역)이고 ' % (fmt(round(avg, -1)), len(rows)),
             '전체 평균은 약 %s만원 선이며 ' % fmt(round(avg, -1))],
            ['중앙값은 %s만원입니다.' % fmt(med),
             '절반의 지역이 %s만원 이상을 지원합니다.' % fmt(med),
             '중앙값 기준으로는 %s만원입니다.' % fmt(med),
             '가운데 값(중앙값)은 %s만원입니다.' % fmt(med)]))
        spread = rows[0][3] - rows[-1][3]
        ceil_cnt = sum(1 for t in tots if t == rows[0][3])
        distinct = len(set(tots))
        p2.append(CC('dist',
            ['', '격차를 재 보면 ', '지역차를 정리하면 '],
            ['최고와 최저의 차이는 %s만원이고 ' % fmt(spread),
             '최고액과 최저액은 %s만원 벌어져 있고 ' % fmt(spread),
             '상하단 격차가 %s만원에 이르고 ' % fmt(spread)],
            ['최고 금액(%s만원)을 주는 곳은 %s입니다.' % (fmt(rows[0][3]), knu(ceil_cnt, '곳')),
             '전국의 합계 금액은 %s로 갈립니다.' % knu(distinct, '가지') if distinct <= 10
             else '전국의 합계 금액은 %d가지로 갈립니다.' % distinct,
             '정점인 %s만원은 %s에서 받습니다.' % (fmt(rows[0][3]), knu(ceil_cnt, '곳'))]))
        srt = sorted(tots)
        q_lo, q_hi = srt[len(srt) // 4], srt[len(srt) * 3 // 4]
        if q_lo != q_hi:
            p2.append(CC('quart',
                ['', '4분위로 끊어 보면 ', '분포의 허리를 보면 '],
                ['상위 4분의 1 문턱이 %s만원, 하위 4분의 1 문턱이 %s만원이라 ' % (fmt(q_hi), fmt(q_lo)),
                 '위쪽 25%% 경계는 %s만원, 아래쪽 25%% 경계는 %s만원이라 ' % (fmt(q_hi), fmt(q_lo)),
                 '가운데 절반의 지역이 %s만~%s만원 사이에 몰려 있어 ' % (fmt(q_lo), fmt(q_hi))],
                ['대부분 지역의 체감 격차는 이 범위 안에 있습니다.',
                 '내 지역이 어느 쪽 끝인지 표에서 확인해 볼 만합니다.',
                 '극단값보다 이 구간이 현실적인 기대치입니다.']))
    elif rows:
        p2.append('이 차종은 %d개 지역에서 지방비 단가가 확인되며, 합계는 %s만~%s만원입니다.'
                  % (len(rows), fmt(rows[-1][3]), fmt(rows[0][3])))
    else:
        p2.append('현재 이 차종의 지역별 지방비 단가가 확인되는 지자체가 없습니다. 공고 등록 전이거나 지원 대상에서 빠진 경우일 수 있습니다.')
    if 'WAV' in name:
        p2.append('이 트림은 WAV(휠체어 탑승 가능 차량) 사양으로, 일반 승용 구매와 지원 조건·물량 구분이 다를 수 있습니다. 반드시 해당 지자체 공고의 WAV 조항을 확인하세요.')
    p2.append(CC('bojocaveat',
        ['', '단서 하나: ', '주의점으로, ', '당연하지만 중요한 전제인데, '],
        ['표시 금액은 단가 기준이라 ',
         '이 표는 단가표일 뿐이어서 ',
         '금액이 큰 지역이라도 ',
         '단가와 수령은 별개라 '],
        ['실제로 받으려면 주소지 지자체의 접수가 열려 있어야 하며 ',
         '해당 지자체 접수가 마감되면 받을 수 없으며 ',
         '물량이 소진됐다면 의미가 없으며 ',
         '접수 창구가 닫히면 그림의 떡이며 '],
        ['잔여·마감 상태는 각 지역 페이지에서 확인할 수 있습니다.',
         '계약 전 지역 페이지의 잔여 현황을 함께 보세요.',
         '지역 페이지의 잔여·마감 뱃지를 교차 확인하세요.',
         '내 주소지 페이지의 상태 뱃지부터 확인하는 것이 순서입니다.']))
    oc = ctx.get('open_cnt')
    ob = ctx.get('open_base', 160)
    if oc is not None:
        p2.append(CC('opencnt',
            ['', '참고로 ', '전국 단위로는 ', '접수 지형을 요약하면 '],
            ['%s 수집 기준 %d개 지자체 중 ' % (ctx['asof'], ob),
             '%s 기준 전국 %d개 지자체 가운데 ' % (ctx['asof'], ob),
             '전국 %d개 지자체를 훑으면(%s 기준) ' % (ob, ctx['asof']),
             '이 시점(%s) 전국 %d개 지자체에서 ' % (ctx['asof'], ob)],
            ['잔여가 남고 마감 공지가 없는 곳은 %d곳입니다.' % oc,
             '접수 가능성이 남은 곳(잔여 보유·마감 공지 없음)은 %d곳으로 집계됩니다.' % oc,
             '%d곳이 잔여를 보유한 채 마감 공지가 없는 상태입니다.' % oc,
             '마감 공지 없이 잔여가 남은 곳은 %d곳뿐입니다.' % oc]))

    # ── ③ 구매 맥락 (가격 구간 — '기본가격' 기준·'미만/이상' 표현 고정) ──
    full_b = meta.get('priceBands', {}).get('full', 5300)
    half_b = meta.get('priceBands', {}).get('half', 8500)
    p3 = []
    p3.append(CC('band',
        ['국비 산정 비율은 ', '보조금 구간 판정은 ', '가격 구간 규칙을 정확히 쓰면, ', '지원 비율을 가르는 기준은 '],
        ['제조사가 신고한 「차량 인증사양별 기본가격」 기준으로 %s만원 미만이면 100%%, %s만원 이상~%s만원 미만이면 50%%, '
         % (fmt(full_b), fmt(full_b), fmt(half_b)),
         '「차량 인증사양별 기본가격」(제조사 신고 값)이 %s만원 미만일 때 100%%, %s만원 이상 %s만원 미만일 때 50%%, '
         % (fmt(full_b), fmt(full_b), fmt(half_b)),
         '견적서 최종가가 아니라 「차량 인증사양별 기본가격」으로 판정해 %s만원 미만 100%%, %s만원 이상 %s만원 미만 50%%, '
         % (fmt(full_b), fmt(full_b), fmt(half_b)),
         '「차량 인증사양별 기본가격」(제조사 신고)을 기준 삼아 %s만원 미만은 100%%, %s만원 이상 %s만원 미만은 50%%, '
         % (fmt(full_b), fmt(full_b), fmt(half_b))],
        ['%s만원 이상이면 지원이 없습니다.' % fmt(half_b),
         '%s만원 이상은 0원입니다.' % fmt(half_b),
         '%s만원 이상은 지원 대상에서 빠집니다.' % fmt(half_b),
         '%s만원 이상은 지원 제외입니다.' % fmt(half_b)]))
    p3.append(CC('option',
        ['', '자주 묻는 부분인데, ', '덧붙이면 ', '오해가 잦은 지점으로, '],
        ['옵션·색상 가격은 기본가격에 포함되지 않으므로 ',
         '판정에 쓰이는 기본가격에는 옵션가가 들어가지 않아 ',
         '기본가격은 옵션과 무관한 신고 값이라 ',
         '옵션가는 판정 기준 밖이라 '],
        ['옵션을 추가한다고 보조금 구간이 바뀌지는 않습니다.',
         '옵션 선택으로 구간이 넘어가는 일은 없습니다.',
         '구간 걱정으로 옵션을 포기할 필요는 없습니다.',
         '색상·옵션을 더해도 구간 판정은 그대로입니다.']))
    p3.append(CC('conv',
        ['', '별도 항목으로, ', '추가 지원도 있는데, ', '전환 조건이라면, '],
        ['기존 내연기관차를 폐차·처분하고 전환하면 ',
         '내연차에서 전환하는 구매라면 ',
         '내연기관차 처분을 동반한 전환 구매에는 ',
         '내연차를 정리하고 넘어오는 경우 '],
        ['국비 최대 %s만원의 전환지원금이 추가되고 지자체에 따라 지방비 전환지원금이 더해질 수 있습니다.' % fmt(meta.get('convNatMax', 100)),
         '전환지원금(국비 최대 %s만원+지자체별 지방비)을 챙길 수 있습니다.' % fmt(meta.get('convNatMax', 100)),
         '국비 전환지원금 최대 %s만원과 지자체별 지방비 몫이 별도로 붙습니다.' % fmt(meta.get('convNatMax', 100)),
         '국비 %s만원 한도의 전환지원금이 따로 있습니다(지방비는 지자체 공고 기준).' % fmt(meta.get('convNatMax', 100))]))
    if car.get('convNat'):
        p3.append(CC('convcar',
            ['', '이 트림 기준으로 좁히면, ', '차종별 값으로는, '],
            ['%s의 전환지원금 국비 몫은 %s만원으로 책정돼 있어 ' % (name, fmt(car['convNat'])),
             '이 차에 잡힌 전환 국비는 %s만원이라 ' % fmt(car['convNat']),
             '데이터상 이 트림의 전환 국비 단가는 %s만원이어서 ' % fmt(car['convNat'])],
            ['폐차·처분 전환 구매라면 그만큼이 기본 보조금 위에 얹어집니다.',
             '전환 조건 충족 시 합계에 이 금액을 더해 계산하면 됩니다.',
             '전환 요건을 채우는 경우의 가산분으로 보면 됩니다.']))
    p3.append(CC('close',
        ['', '마지막으로, ', '정리하면 ', '끝으로, '],
        ['실제 지급액과 접수 가능 여부는 관할 지자체 공고로 확정되므로 ',
         '최종 금액·자격은 지자체 공고가 기준이므로 ',
         '여기 적힌 금액은 %s 단가 기준이므로 ' % meta['updated'],
         '이 페이지의 단가 기준일은 %s이므로 ' % meta['updated']],
        ['계약 전 공고문과 무공해차 통합누리집(ev.or.kr)에서 확인하는 것이 안전합니다(단가 기준일 %s).' % meta['updated'],
         '계약 전 공고문과 ev.or.kr에서 확정 조건을 확인하세요(단가 기준일 %s).' % meta['updated'],
         '확정 조건은 관할 지자체 공고 원문과 ev.or.kr에서 최종 확인해야 합니다.',
         '계약 전 지자체 공고 원문으로 최종 조건을 확인하는 것이 순서입니다.']))
    paras = [p1, p2, p3]

    # 단종/이월 모델 — 사실 안내 문단 추가 (noindex이지만 유입 시 오독 방지)
    if car['disc']:
        paras.append([P('disc', [
            '이 트림은 단종/이월로 분류된 모델입니다. 2026년 보조금 단가표에는 남아 있지만 신규 계약이 어려울 수 있고, 재고·이월 물량을 계약하는 경우에만 위 단가가 적용됩니다. 구매 가능 여부는 판매사에, 보조금 적용 여부는 지자체에 각각 확인해야 합니다. 위 트림 목록에서 같은 모델그룹의 현행 트림을 확인할 수 있습니다.',
            '단종/이월 모델이라는 점을 먼저 확인하세요. 단가는 기록·이월 물량 대응용으로 제공되며, 신규 계약 가능 여부는 판매사 재고에 달려 있습니다. 이월 재고를 계약한다면 보조금 신청 가능 여부를 지자체에 미리 확인하는 것이 안전하고, 현행 대체 트림은 위 목록에서 볼 수 있습니다.',
            '주의: 단종/이월 트림입니다. 이 페이지의 단가는 이월 재고 구매자를 위한 참고 자료로 유지되고 있으며, 실제 계약 가능성(재고)과 보조금 신청 가능 여부(지자체)를 각각 확인해야 합니다. 같은 계열의 현행 트림 비교는 트림 목록을 이용하세요.',
        ])])
    return [esc(' '.join(p)) for p in paras]


# ══════════════════════════════════════════════════════════
#  sido 허브
# ══════════════════════════════════════════════════════════
def md_to_html(md_text):
    """산문 md(W2 작성) → (HTML, 프런트매터 dict).
    지원: --- YAML 프런트매터(title/description/publish), ## 소제목, **굵게**, 빈 줄 문단,
    내부 링크 [텍스트](region:4180 | car:12 | sido:seoul | model:ioniq5 | https://…)."""
    fm = {}
    m = re.match(r'\s*---\s*\n(.*?)\n---\s*\n', md_text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ':' in line:
                k, v = line.split(':', 1)
                fm[k.strip()] = v.strip()
        md_text = md_text[m.end():]

    def link_repl(mm):
        txt, tgt = mm.group(1), mm.group(2)
        if tgt.startswith('region:'):
            href = '/region/%s.html' % tgt[7:]
        elif tgt.startswith('car:'):
            href = '/car/%s.html' % tgt[4:]
        elif tgt.startswith('sido:'):
            href = '/sido/%s.html' % tgt[5:]
        elif tgt.startswith('model:'):
            href = '/model/%s.html' % tgt[6:]
        elif tgt.startswith('http'):
            return '<a href="%s" target="_blank" rel="noopener">%s</a>' % (tgt, txt)
        else:
            href = tgt
        return '<a href="%s">%s</a>' % (href, txt)

    out = []
    for block in re.split(r'\n\s*\n', md_text.strip()):
        block = block.strip()
        if not block:
            continue
        if block.startswith('## '):
            out.append('<h2>%s</h2>' % esc(block[3:].strip()))
            continue
        if block.startswith('# '):
            continue  # 문서 제목은 페이지 h1이 대신함
        body = esc(re.sub(r'\s*\n\s*', ' ', block))          # 이스케이프 먼저(링크 문법은 보존됨)
        body = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', link_repl, body)
        body = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', body)
        out.append('<p style="line-height:1.75;margin:10px 0">%s</p>' % body)
    return '\n'.join(out), fm


def sido_auto_prose(sido, sibs, status, meta, asof):
    """updater/content/sido/{slug}.md가 아직 없을 때의 데이터 요약 산문(빌드는 항상 성공)."""
    full = SIDO_FULL[sido]
    P = lambda slot, opts: pick('sido%s:%s' % (sido, slot), opts)
    n_r = len(sibs)
    maxs = [(v.get('maxP') or 0, v['name']) for _, v in sibs]
    hi = max(maxs)
    lo = min(maxs)
    rep_cnt = sum(1 for _, v in sibs if v.get('rep'))
    total_n = sum((status['data'].get(k) or {}).get('n') or 0 for k, _ in sibs)
    total_left = sum((status['data'].get(k) or {}).get('left') or 0 for k, _ in sibs)
    closed_cnt = 0
    zero_cnt = 0
    open_cnt = 0
    for k, _ in sibs:
        stt = status['data'].get(k) or {}
        ci = detect_closed(stt.get('note'))
        if stt.get('left') is not None and stt['left'] <= 0:
            zero_cnt += 1
        elif ci['closed'] and not ci['partial']:
            closed_cnt += 1
        else:
            open_cnt += 1
    paras = []
    if n_r == 1:
        paras.append(P('single', [
            '%s는 시·군·구 구분 없이 시 전체가 하나의 공고로 운영되는 지역입니다. 2026년 전기승용 기준 국비+지방비 합계 최대 %s만원이 지원됩니다.' % (full, fmt(hi[0])),
            '%s의 전기차 보조금은 단일 공고 체계입니다. 승용 기준 최대 지원액은 국비+지방비 합계 %s만원입니다(%s 기준).' % (full, fmt(hi[0]), asof),
        ]))
    else:
        paras.append(P('multi', [
            '%s에는 %d개 시·군이 각자 전기차 보조금 공고를 운영합니다. 2026년 승용 기준 최대 지원액은 %s(%s만원)이 가장 크고 %s(%s만원)이 가장 작아, 같은 도 안에서도 %s만원 차이가 납니다.'
            % (full, n_r, hi[1], fmt(hi[0]), lo[1], fmt(lo[0]), fmt(hi[0] - lo[0])),
            '%s %d개 시·군의 2026년 전기승용 최대 지원액은 %s만원(%s)부터 %s만원(%s)까지 분포합니다. 주소지에 따라 최대 %s만원까지 달라지는 셈입니다.'
            % (full, n_r, fmt(lo[0]), lo[1], fmt(hi[0]), hi[1], fmt(hi[0] - lo[0])),
        ]))
        if rep_cnt:
            paras.append('단가 구조를 보면 %d개 시·군 중 %d곳이 도 공통 단가(대표 단가 복제)를 적용하고 있습니다. 도 공통 단가 지역이라도 시·군 자체 추가 지원이 별도로 있을 수 있어 개별 공고 확인이 필요합니다.' % (n_r, rep_cnt))
        else:
            paras.append('이 지역 시·군들은 도 공통 단가가 아니라 각자 자체 단가를 운영합니다. 차종별 금액이 시·군마다 다르므로 주소지 기준으로 확인해야 합니다.')
    if total_n:
        paras.append(P('budget', [
            '공고 물량 규모는 %s 전체 합계 %s대이며, %s 수집 기준 잔여 합계는 %s대입니다.' % (full, fmt(total_n), asof, fmt(total_left)),
            '%s 기준 %s의 전기승용 공고 물량은 총 %s대, 남은 물량 합계는 %s대로 집계됩니다.' % (asof, full, fmt(total_n), fmt(total_left)),
        ]))
    paras.append('접수 상태 분포는 접수 진행·확인 가능 %d곳, 공지상 마감 안내 %d곳, 잔여 소진 %d곳입니다(%s 기준). 잔여가 남아 있어도 공지상 마감인 지역이 있으니, 아래 표의 상태와 각 지역 페이지의 공지 원문을 함께 확인하세요.' % (open_cnt, closed_cnt, zero_cnt, asof))
    paras.append('이 표와 수치는 무공해차 통합누리집(ev.or.kr) 공고 데이터를 매시간 수집해 만든 것입니다. 실제 신청 자격·기간·서류는 각 시·군 공고문이 기준이며, 보조금은 주민등록 주소지 지자체에 신청합니다.')
    return '\n'.join('<p style="line-height:1.75;margin:10px 0">%s</p>' % esc(p) for p in paras)


def build_sido(sido, regions, meta, status, ctx):
    slug = SIDO_SLUG[sido]
    full = SIDO_FULL[sido]
    updated = status.get('updated', '')
    asof = updated[:10]
    sibs = sorted(((k, v) for k, v in regions.items() if v.get('sido') == sido and k != '9999'),
                  key=lambda kv: (-(kv[1].get('maxP') or 0), kv[1]['name']))
    md_path = os.path.join(SIDO_MD_DIR, slug + '.md')
    published = asof
    fm = {}
    if os.path.exists(md_path):
        with open(md_path, encoding='utf-8') as f:
            prose, fm = md_to_html(f.read())
        # 게시일은 프런트매터 publish가 정본(본문 '게시 시점' 앵커와 일치) — 없을 때만 mtime 폴백
        pub_fm = (fm.get('publish') or '').strip()
        published = (pub_fm if re.fullmatch(r'\d{4}-\d{2}-\d{2}', pub_fm)
                     else datetime.date.fromtimestamp(os.path.getmtime(md_path)).isoformat())
    else:
        # W2 산문이 아직 없으면 데이터 요약 산문으로 자동 대체 — 빌드는 항상 성공
        prose = sido_auto_prose(sido, sibs, status, meta, asof)

    trs = []
    for k, v in sibs:
        stt = status['data'].get(k) or {}
        cls, label = badge_of(stt, ctx['closed_map'].get(k) or detect_closed(stt.get('note')))
        trs.append('<tr data-cd="%s"><td><a href="/region/%s.html" style="font-weight:700">%s</a></td>'
                   '<td class="num">%s</td><td class="num" data-cell="left">%s</td>'
                   '<td><span class="badge %s" data-cell="badge"><span class="dot"></span>%s</span></td></tr>'
                   % (k, k, esc(v['name']), fmt(v.get('maxP')), fmt(stt.get('left')), cls, esc(label)))

    # 단일 지자체 시도(광역시·세종·제주)는 '1개 시군구 총정리'가 doorway 인상 + region 페이지와 근사중복
    # → 에세이 중심 제목으로 재구성(마감 패턴·경쟁 상황 분석이 이 페이지들의 실제 가치)
    single = len(sibs) <= 1
    head_txt = ('%s 전기차 보조금 2026 — 접수 흐름·마감 패턴 분석' % full if single
                else '%s 전기차 보조금 2026 — %d개 시군구 총정리' % (full, len(sibs)))
    canonical = '%s/sido/%s.html' % (BASE, slug)
    ld = [{'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': '홈', 'item': BASE + '/'},
        {'@type': 'ListItem', 'position': 2, 'name': '%s 전기차 보조금' % full, 'item': canonical}]},
        {'@context': 'https://schema.org', '@type': 'Article',
         'headline': head_txt,
         'datePublished': published, 'dateModified': asof, 'inLanguage': 'ko',
         'author': {'@type': 'Person', 'name': 'HyeongHun Lee', 'url': BASE + '/about.html#operator'},
         'publisher': {'@type': 'Organization', 'name': 'EV보조금'},
         'mainEntityOfPage': canonical}]

    mapping = {
        'NAME': esc(full),
        'SUB': ('2026년 전기승용 기준 · 접수 흐름·마감 패턴과 현재 잔여 현황' if single
                else '2026년 전기승용 기준 · %d개 시·군·구 최대 보조금·잔여 현황' % len(sibs)),
        'PUBLISHED': esc(published), 'ASOF': esc(asof),
        'PROSE': prose,
        'AD1': '', 'AD2': '',
        'TABLE_SUB': '%d개 지역 · 최대 보조금 순' % len(sibs),
        'TABLE_ROWS': ''.join(trs),
    }
    gate = len(strip_tags(render(ctx['tpl_sido'], mapping)))   # app.js와 동일: <main> 전체 텍스트 기준
    mapping['AD1'] = ad_slot('sido-1', gate, False)
    mapping['AD2'] = ad_slot('sido-2', gate, False)
    main = render(ctx['tpl_sido'], mapping)
    page = render(ctx['tpl_page'], {
        'TITLE': esc('%s | EV보조금' % head_txt),
        'DESC': esc(fm.get('description') or
                    ('%s 2026년 전기차 보조금: 올해 접수 흐름과 마감 패턴, 현재 잔여·접수 상태를 %s 기준 실측 데이터로 분석했습니다.' % (full, asof) if single else
                     '%s 2026년 전기차 보조금 총정리: %d개 시·군·구별 최대 지원액(국비+지방비)·잔여 물량·접수 상태를 %s 기준 데이터로 한 표에 정리했습니다.' % (full, len(sibs), asof))),
        'ROBOTS': '',
        'CANONICAL': canonical,
        'JSONLD': jsonld_script(ld),
        'BREADCRUMB': '<a href="/">홈</a> › <b>%s</b>' % esc(full),
        'MAIN': main,
        'META_UPDATED': esc(meta['updated']),
    })
    return page


# ══════════════════════════════════════════════════════════
#  model 시리즈 (시차 발행 게이트 — publish가 KST 오늘보다 미래면 전면 제외)
# ══════════════════════════════════════════════════════════
def load_model_entries(today_kst):
    """updater/content/model/{slug}.md 로드 — W2 작성 전(md 없음)·미래 publish는 조용히 스킵(빌드 성공).
    발행 게이트를 통과한 편만 반환하므로 페이지·허브·사이트맵·car 상호링크가 전부 같은 집합을 본다."""
    entries = []
    for slug, group in MODEL_SERIES.items():
        if not re.fullmatch(r'[a-z0-9-]+', slug):
            print('경고: model 슬러그 형식 불일치 %r — 제외' % slug, file=sys.stderr)
            continue                                    # 고정 슬러그지만 경로 이중 방어
        path = os.path.join(MODEL_MD_DIR, slug + '.md')
        if not os.path.exists(path):
            continue                                    # 에세이 미작성 — 무소음 강등
        with open(path, encoding='utf-8') as f:
            prose, fm = md_to_html(f.read())
        pub = (fm.get('publish') or '').strip()
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', pub):
            print('경고: model/%s.md publish 형식 불일치 %r — 제외' % (slug, pub), file=sys.stderr)
            continue
        if pub > today_kst:
            continue                                    # 시차 발행 — 도래 전엔 어디에도 노출하지 않음
        entries.append({'slug': slug, 'group': group, 'prose': prose, 'fm': fm, 'publish': pub})
    entries.sort(key=lambda e: (e['publish'], e['slug']))
    return entries


def build_model(entry, cars, regions, meta, status, ctx):
    """모델 시리즈 한 편 — 에세이(md) + 매시간 갱신 데이터 섹션(트림 표·대표 트림 지역 분포)."""
    slug, group, fm = entry['slug'], entry['group'], entry['fm']
    updated = status.get('updated', '')
    asof = updated[:10]
    # 현행 트림만, WAV·'미지원' 사양은 표·대표 트림에서 제외(일반 구매와 조건이 다름)
    trims = sorted((c for c in cars if not c['disc'] and model_group(c) == group
                    and 'WAV' not in c['name'] and '미지원' not in c['name']),
                   key=lambda c: (-c['nat'], c['id']))
    if not trims:
        print('경고: model/%s — 현행 트림 없음, 페이지 제외' % slug, file=sys.stderr)
        return None
    rep = trims[0]                                      # 대표 트림 = 그룹 내 국비 최고 비단종
    nat_lo = min(c['nat'] for c in trims)
    nat_hi = max(c['nat'] for c in trims)

    trs = []
    for c in trims:
        eff = round(c['range'] / c['batt'], 1) if c.get('range') and c.get('batt') else None
        trs.append('<tr><td><a href="/car/%d.html" style="color:inherit;font-weight:700">%s</a></td>'
                   '<td class="num">%s</td><td class="num">%s / %s</td><td class="num">%s</td></tr>'
                   % (c['id'], esc(c['name']), fmt(c['nat']),
                      fmt(c['range']) if c.get('range') else '-',
                      fmt(c['rangeCold']) if c.get('rangeCold') else '-',
                      eff if eff else '-'))

    # 대표 트림 기준 지역별 합계(9999 제외) + 상태 뱃지(detect_closed 재사용 — closed_map)
    rows = []
    for k, r in regions.items():
        if k == '9999':
            continue
        v = car_v(r, rep['id'])
        if not v:
            continue
        rows.append((k, r, rep['nat'] + v[0]))
    rows.sort(key=lambda x: (-x[2], x[1]['name']))
    rtrs = []
    for k, r, tot in rows[:15]:
        stt = status['data'].get(k) or {}
        cls, label = badge_of(stt, ctx['closed_map'][k])
        rtrs.append('<tr><td><a href="/region/%s.html" style="color:inherit;font-weight:700">%s</a>'
                    '<div class="small muted">%s</div></td>'
                    '<td class="num" style="font-weight:800;color:var(--money)">%s</td>'
                    '<td><span class="badge %s"><span class="dot"></span>%s</span></td></tr>'
                    % (k, esc(r['name']), esc(r.get('sido', '')), fmt(tot), cls, esc(label)))
    dist = ''
    if rows:
        tots = sorted(t for _, _, t in rows)
        n = len(tots)
        # 표준 중앙값(짝수면 가운데 두 값 평균) — 에세이(md) 계산 관례와 통일
        med = tots[n // 2] if n % 2 else round((tots[n // 2 - 1] + tots[n // 2]) / 2)
        dist = ('<p class="small" style="line-height:1.7;margin-top:10px">%s 수집 기준 %d개 지자체에서 '
                '%s의 국비+지방비 합계는 최고 %s만원(%s), 최저 %s만원(%s), 중앙값 %s만원입니다. '
                '표의 금액은 공고 단가 기준이라 접수 마감 여부와는 별개이며, 실제 접수 가능 여부는 '
                '각 지역 페이지의 상태 뱃지와 공지 원문으로 확인하세요.</p>'
                % (esc(asof), len(rows), esc(rep['name']), fmt(rows[0][2]), esc(rows[0][1]['name']),
                   fmt(rows[-1][2]), esc(rows[-1][1]['name']), fmt(med)))

    related = ['<a class="chip" href="winter-range-ranking.html">❄️ 겨울 주행거리 랭킹</a>',
               '<a class="chip" href="price-tiers.html">💰 가격구간(기본가격) 바로 알기</a>',
               '<a class="chip" href="status.html">🗺 전국 현황판</a>',
               '<a class="chip" href="model/">📚 모델별 시리즈 전체 보기</a>']

    title = fm.get('title') or '%s 보조금 2026 — 트림·지역·겨울 성능 심층 분석' % group
    desc = fm.get('description') or ('%s 2026년 보조금 심층 분석: 현행 트림 %d종 국비 %s만~%s만원, 지역별 국비+지방비 합계 분포와 접수 상태, 저온(겨울) 주행거리까지 실측 데이터 기준.'
                                     % (group, len(trims), fmt(nat_lo), fmt(nat_hi)))
    canonical = '%s/model/%s.html' % (BASE, slug)
    ld = [{'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': '홈', 'item': BASE + '/'},
        {'@type': 'ListItem', 'position': 2, 'name': '모델별 보조금 심층 시리즈', 'item': BASE + '/model/'},
        {'@type': 'ListItem', 'position': 3, 'name': '%s 보조금' % group, 'item': canonical}]},
        {'@context': 'https://schema.org', '@type': 'Article',
         'headline': title, 'datePublished': entry['publish'], 'dateModified': asof, 'inLanguage': 'ko',
         'author': {'@type': 'Person', 'name': 'HyeongHun Lee', 'url': BASE + '/about.html#operator'},
         'publisher': {'@type': 'Organization', 'name': 'EV보조금'},
         'mainEntityOfPage': canonical}]

    mapping = {
        'NAME': esc(title.split(' — ')[0] if ' — ' in title else title),
        'GROUP': esc(group),
        'SUB': '2026년 전기승용 기준 · 현행 트림 %d종 · 국비 %s만~%s만원' % (len(trims), fmt(nat_lo), fmt(nat_hi)),
        'PUBLISHED': esc(entry['publish']), 'ASOF': esc(asof),
        'PROSE': entry['prose'],
        'AD1': '', 'AD2': '',
        'TRIM_SUB': '%d개 트림 · 국비 순' % len(trims),
        'TRIM_ROWS': ''.join(trs),
        'REP_NAME': esc(rep['name']),
        'REGION_SUB': '상위 %d개 / 전체 %d개 지역 · %s 수집 기준' % (min(15, len(rows)), len(rows), esc(asof)),
        'REGION_ROWS': ''.join(rtrs),
        'DIST': dist,
        'RELATED': ''.join(related),
    }
    gate = len(strip_tags(render(ctx['tpl_model'], mapping)))   # app.js와 동일: <main> 전체 텍스트 기준
    mapping['AD1'] = ad_slot('model-1', gate, False)
    mapping['AD2'] = ad_slot('model-2', gate, False)
    main = render(ctx['tpl_model'], mapping)
    return render(ctx['tpl_page'], {
        'TITLE': esc('%s | EV보조금' % title),
        'DESC': esc(desc),
        'ROBOTS': '',
        'CANONICAL': canonical,
        'JSONLD': jsonld_script(ld),
        'BREADCRUMB': '<a href="/">홈</a> › <a href="/model/">모델별 시리즈</a> › <b>%s</b>' % esc(group),
        'MAIN': main,
        'META_UPDATED': esc(meta['updated']),
    })


def build_model_hub(entries, meta, status, ctx):
    """시리즈 허브 — 발행 게이트를 통과한 편만 나열. articles.html·홈은 이 허브 하나만 가리키면 된다."""
    asof = status.get('updated', '')[:10]
    rows = ''.join('<a class="row" href="/model/%s.html"><div class="grow"><div class="tit">%s</div>'
                   '<div class="desc">%s</div><div class="desc" style="opacity:.75">게시 %s</div></div></a>'
                   % (e['slug'],
                      esc(e['fm'].get('title') or '%s 보조금 심층 분석' % e['group']),
                      esc(e['fm'].get('description') or '트림·지역·겨울 성능 실측 분석'),
                      esc(e['publish']))
                   for e in entries)
    listing = ('<div class="rowlist">%s</div>' % rows if rows else
               '<p class="muted small" style="padding:10px 4px">첫 편을 준비 중입니다. 발행되는 대로 이곳에 나열돼요.</p>')
    # 시리즈 소개 2문단 — 정적(멱등). 키워드 반복 제한: '전기차 보조금' 문단당 1회 이하
    intro = (
        '<p style="line-height:1.75;margin:10px 0">이 시리즈는 관심이 큰 전기차 모델을 한 편에 하나씩 깊게 다루는 연재입니다. '
        '같은 이름의 차라도 트림에 따라 국비가 달라지고, 주소지에 따라 지방비가 갈리며, 겨울(저온) 주행거리 유지율도 제각각입니다. '
        '각 편은 무공해차 통합누리집(ev.or.kr) 공고 데이터를 매시간 수집한 실측치를 근거로, '
        '트림별 국비 차이 → 지역별 합계 분포 → 겨울 성능 → 신청 실무 순서로 정리합니다.</p>'
        '<p style="line-height:1.75;margin:10px 0">본문 산문에는 작성 기준일을 명시하고, 데이터 표(트림·지역·접수 상태)는 '
        '매시간 자동 갱신됩니다. 시리즈는 순차 발행되며 발행된 편만 아래에 나열됩니다. 표시 금액은 공고 단가 기준이므로, '
        '실제 신청 자격·기간·접수 가능 여부는 관할 지자체 공고문으로 확인하세요.</p>')
    canonical = BASE + '/model/'
    main_body = (
        '<div class="hero" style="text-align:left;padding-bottom:0">\n'
        '  <h1>모델별 <span class="hl">보조금 심층 시리즈</span></h1>\n'
        '  <p>인기 전기차를 한 편에 하나씩 — 트림·지역·겨울 성능 실측 분석</p>\n'
        '</div>\n'
        '<p class="stamp">글·데이터: HyeongHun Lee (<a href="about.html#operator">EV보조금 운영자</a>) · 데이터 기준 %s</p>\n'
        '<section class="card">\n%s\n</section>\n'
        '%s\n'
        '<section class="card">\n  <h2 class="mt0">발행된 편 <span class="sub">%d편 · 발행일 순</span></h2>\n  %s\n</section>\n'
        '<section class="card">\n  <h2 class="mt0">다음 단계</h2>\n  <div class="chips">\n'
        '    <a class="chip" href="status.html">🗺 전국 현황판</a>\n'
        '    <a class="chip" href="winter-range-ranking.html">❄️ 겨울 주행거리 랭킹</a>\n'
        '    <a class="chip" href="articles.html">📚 읽을거리 전체</a>\n'
        '  </div>\n</section>\n')
    gate = len(strip_tags(main_body % (esc(asof), intro, '', len(entries), listing)))
    ad1 = ad_slot('model-hub-1', gate, False)
    main = main_body % (esc(asof), intro, ad1, len(entries), listing)
    ld = [{'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': '홈', 'item': BASE + '/'},
        {'@type': 'ListItem', 'position': 2, 'name': '모델별 보조금 심층 시리즈', 'item': canonical}]},
        {'@context': 'https://schema.org', '@type': 'CollectionPage',
         'name': '모델별 전기차 보조금 심층 시리즈',
         'description': '인기 전기차 모델별 보조금 심층 분석 연재 — 트림·지역·겨울 성능 실측 데이터 기준.',
         'url': canonical, 'inLanguage': 'ko'}]
    if entries:
        ld.append({'@context': 'https://schema.org', '@type': 'ItemList',
                   'name': '모델별 보조금 심층 시리즈 발행 목록',
                   'itemListOrder': 'https://schema.org/ItemListOrderAscending',
                   'numberOfItems': len(entries),
                   'itemListElement': [
                       {'@type': 'ListItem', 'position': i + 1,
                        'url': '%s/model/%s.html' % (BASE, e['slug']),
                        'name': e['fm'].get('title') or '%s 보조금 심층 분석' % e['group']}
                       for i, e in enumerate(entries)]})
    return render(ctx['tpl_page'], {
        'TITLE': esc('모델별 전기차 보조금 심층 시리즈 — 트림·지역·겨울 성능 | EV보조금'),
        'DESC': esc('아이오닉5·EV3·모델Y 등 인기 모델의 2026년 보조금을 한 편에 하나씩 심층 분석. 트림별 국비, 지역별 합계 분포, 저온 주행거리까지 매시간 갱신되는 실측 데이터 기준.'),
        'ROBOTS': '',
        'CANONICAL': canonical,
        'JSONLD': jsonld_script(ld),
        'BREADCRUMB': '<a href="/">홈</a> › <b>모델별 시리즈</b>',
        'MAIN': main,
        'META_UPDATED': esc(meta['updated']),
    })


# ══════════════════════════════════════════════════════════
#  brief (일간 브리핑 통합 — 날짜 파일은 daily_brief.py 산출물, 허브·사이트맵만 여기 소유)
# ══════════════════════════════════════════════════════════
BRIEF_RE = re.compile(r'(\d{4}-\d{2}-\d{2})\.html$')


def list_brief_days(today_iso):
    """site/brief/의 날짜 파일 중 최근 30일분(내림차순). 파일 자체는 영구 보존 — 목록만 자름."""
    droot = os.path.join(SITE, 'brief')
    if not os.path.isdir(droot):
        return []
    cut = (datetime.date.fromisoformat(today_iso) - datetime.timedelta(days=29)).isoformat()  # 오늘 포함 30일 창
    days = sorted((m.group(1) for fn in os.listdir(droot)
                   for m in [BRIEF_RE.fullmatch(fn)] if m), reverse=True)
    return [d for d in days if d >= cut]


def _brief_desc(day):
    """발행된 브리핑 파일의 meta description을 허브 요약으로 재사용(파일 앞부분만 읽음)."""
    try:
        with open(os.path.join(SITE, 'brief', day + '.html'), encoding='utf-8') as f:
            head = f.read(4096)
        m = re.search(r'<meta name="description" content="([^"]*)"', head)
        return m.group(1) if m else ''
    except OSError:
        return ''


def build_brief_hub(brief_days, meta, status, ctx):
    """/brief/ 허브 — 최근 30일 목록 + 자동 생성 공개 문단(정적·멱등)."""
    wd = ['월', '화', '수', '목', '금', '토', '일']
    rows = []
    for d in brief_days:
        dt = datetime.date.fromisoformat(d)
        rows.append('<a class="row" href="/brief/%s.html"><div class="grow">'
                    '<div class="tit">%d월 %d일(%s) 브리핑</div><div class="desc">%s</div>'
                    '<div class="desc" style="opacity:.75">발행 %s</div></div></a>'
                    % (d, dt.month, dt.day, wd[dt.weekday()], _brief_desc(d), d))
    listing = ('<div class="rowlist">%s</div>' % ''.join(rows) if rows else
               '<p class="muted small" style="padding:10px 4px">첫 브리핑을 준비 중입니다. 발행되는 대로 이곳에 나열돼요.</p>')
    intro = (
        '<p style="line-height:1.75;margin:10px 0">일일 브리핑은 무공해차 통합누리집(ev.or.kr)에서 매시간 수집하는 '
        '지자체 공고 데이터를 바탕으로 매일 아침 발행되는 페이지입니다(집계 자동화 · 방법 설계·검수 운영자). 전국 잔여 합계의 전일 대비 변화, '
        '가장 많이 줄어든 지역, 새로 마감이 공지된 지역, 물량이 크게 늘어난(추가 공고 가능성) 지역을 '
        '그날의 실측 수치로만 정리합니다. 외부 기사를 재작성하지 않습니다.</p>'
        '<p style="line-height:1.75;margin:10px 0">변화가 없거나 데이터 수집이 오래된 날에는 발행을 건너뜁니다. '
        '발행된 브리핑은 그날의 기록으로 보존되며 이후 수정하지 않습니다. 목록에는 최근 30일분만 나열하지만 '
        '지난 브리핑 페이지 자체는 계속 유지됩니다. 데이터·생성: EV보조금 자동 브리핑 · '
        '편집 책임: <a href="about.html#operator">HyeongHun Lee</a>.</p>')
    canonical = BASE + '/brief/'
    main_body = (
        '<div class="hero" style="text-align:left;padding-bottom:0">\n'
        '  <h1>매일 아침 <span class="hl">보조금 브리핑</span></h1>\n'
        '  <p>어제 하루 전국 잔여 변화 — 실측 데이터 자동 브리핑</p>\n'
        '</div>\n'
        '<p class="stamp">데이터 기준 %s · 매일 아침 발행(변화 없는 날 제외) · 출처 ev.or.kr</p>\n'
        '<section class="card">\n%s\n</section>\n'
        '<section class="card">\n  <h2 class="mt0">지난 브리핑 <span class="sub">최근 30일 · %d편</span></h2>\n  %s\n</section>\n'
        '<section class="card">\n  <h2 class="mt0">다음 단계</h2>\n  <div class="chips">\n'
        '    <a class="chip" href="status.html">🗺 전국 현황판</a>\n'
        '    <a class="chip" href="quota-reading.html">📖 잔여 대수 읽는 법</a>\n'
        '    <a class="chip" href="articles.html">📚 읽을거리 전체</a>\n'
        '  </div>\n</section>\n'
        % (esc(status.get('updated', '')[:10]), intro, len(brief_days), listing))
    ld = [{'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': '홈', 'item': BASE + '/'},
        {'@type': 'ListItem', 'position': 2, 'name': '일일 브리핑', 'item': canonical}]},
        {'@context': 'https://schema.org', '@type': 'CollectionPage',
         'name': '전기차 보조금 일일 브리핑',
         'description': '전국 전기승용 보조금 잔여 변화를 매일 아침 실측 데이터로 자동 정리하는 브리핑 모음.',
         'url': canonical, 'inLanguage': 'ko'}]
    return render(ctx['tpl_page'], {
        'TITLE': esc('전기차 보조금 일일 브리핑 — 전국 잔여 변화 매일 아침 정리 | EV보조금'),
        'DESC': esc('전국 160개 지자체의 전기승용 보조금 잔여 변화·신규 마감·물량 증가를 매일 아침 실측 데이터로 자동 정리. 최근 30일 브리핑 모음.'),
        # 브리핑 섹션은 데이터 집계 페이지 — 자동 생성 콘텐츠 정책상 색인 제외(사이트 이용자용 발행은 유지)
        'ROBOTS': '\n<meta name="robots" content="noindex">',
        'CANONICAL': canonical,
        'JSONLD': jsonld_script(ld),
        'BREADCRUMB': '<a href="/">홈</a> › <b>일일 브리핑</b>',
        'MAIN': main_body,
        'META_UPDATED': esc(meta['updated']),
    })


# ══════════════════════════════════════════════════════════
#  sitemap · 쓰기 · 메인
# ══════════════════════════════════════════════════════════
def build_sitemap(regions, cars, today, model_entries=(), brief_days=(), car_rep=None,
                  pages=None, store=None, region_noindex=()):
    """lastmod 신뢰 원칙: **실제 내용이 바뀐 날만** 기재.

    - 정적 CORE + 데이터 페이지(region/car/sido/모델 허브) = <main> 내용 해시(수치 마스킹) 비교.
      직전 회차와 해시가 같으면 저장된 날짜를 그대로 쓰고, 다르거나 기록이 없으면 오늘로 갱신.
      캐시가 없거나 깨졌으면 전부 오늘로 폴백(종전 동작) — 빌드는 실패시키지 않는다.
    - 모델 시리즈 = 발행일 고정 · 브리핑 = noindex 정책이라 사이트맵 전체 제외
    반환: (xml, URL 수, 갱신된 캐시 dict) — 캐시는 이번 사이트맵에 실린 URL만 남긴다(잔재 정리)."""
    pages = pages or {}
    prev = store or {}
    new_store = {}
    noidx = set(region_noindex or ())

    def lm_of(key, html, fallback):
        h = content_hash(html)
        if not h:
            return fallback                # 본문을 못 읽음 → 폴백(파일 mtime 또는 오늘)
        rec = prev.get(key)
        d = rec['d'] if (rec and rec['h'] == h) else today
        new_store[key] = {'h': h, 'd': d}
        return d

    urls = []
    for path, freq in CORE_PAGES:
        fp = os.path.join(SITE, path.lstrip('/') or 'index.html')
        try:                               # 폴백: 파일 mtime(내용을 못 읽는 경우에만 사용)
            fb = datetime.date.fromtimestamp(os.path.getmtime(fp)).isoformat()
        except OSError:
            fb = today
        try:
            with open(fp, encoding='utf-8') as f:
                html = f.read()
        except OSError:
            html = ''
        urls.append((BASE + path, freq, lm_of(path, html, fb)))
    for cd in sorted(regions):
        if cd == '9999' or cd in noidx:
            continue                       # noindex — 사이트맵 제외
        key = '/region/%s.html' % cd
        urls.append((BASE + key, 'daily',
                     lm_of(key, pages.get(os.path.join(SITE, 'region', cd + '.html')), today)))
    for c in cars:
        if c['disc']:
            continue                       # 단종 noindex — 제외
        if car_rep is not None and c['id'] not in car_rep:
            continue                       # 비대표 트림 noindex — 제외(트림 근사중복)
        key = '/car/%d.html' % c['id']
        urls.append((BASE + key, 'weekly',
                     lm_of(key, pages.get(os.path.join(SITE, 'car', '%d.html' % c['id'])), today)))
    for sido in SIDO_SLUG:
        key = '/sido/%s.html' % SIDO_SLUG[sido]
        urls.append((BASE + key, 'daily',
                     lm_of(key, pages.get(os.path.join(SITE, 'sido', SIDO_SLUG[sido] + '.html')), today)))
    # 시리즈 허브(index.html) — 항상 생성. 편이 늘거나 요약이 바뀐 날만 lastmod 갱신
    urls.append((BASE + '/model/', 'weekly',
                 lm_of('/model/', pages.get(os.path.join(SITE, 'model', 'index.html')), today)))
    for e in model_entries:                             # 발행 게이트 통과분만 — 미래 publish는 미포함
        urls.append(('%s/model/%s.html' % (BASE, e['slug']), 'weekly', e.get('publish') or today))
    # 브리핑(/brief/)은 자동 생성 콘텐츠 정책상 noindex — 사이트맵에서 전체 제외(발행·열람은 유지)
    body = '\n'.join('<url><loc>%s</loc><lastmod>%s</lastmod><changefreq>%s</changefreq></url>'
                     % (u, lm, f) for u, f, lm in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s\n</urlset>\n' % body,
            len(urls), new_store)


def atomic_write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp~'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(content)
    os.replace(tmp, path)


def main():
    t0 = datetime.datetime.now()
    cars, regions, meta, status, hist, rounds = load_data()
    # 경로 안전 검증: cd는 ^[0-9]{4,5}$, 차종 id는 0~99999 정수만 파일명·사이트맵에 사용.
    # 불일치 항목은 경고 후 스킵(디렉터리 밖 쓰기·경로 조작 차단, 사이트맵에도 미포함).
    bad_cd = sorted(cd for cd in regions if not re.fullmatch(r'[0-9]{4,5}', str(cd)))
    for cd in bad_cd:
        print('경고: 지역 코드 형식 불일치 %r — 생성·사이트맵 제외' % cd, file=sys.stderr)
    regions = {cd: r for cd, r in regions.items() if cd not in set(bad_cd)}
    ok_cars = []
    for c in cars:
        cid = c.get('id')
        if isinstance(cid, int) and not isinstance(cid, bool) and 0 <= cid <= 99999:
            ok_cars.append(c)
        else:
            print('경고: 차종 id 형식 불일치 %r — 생성·사이트맵 제외' % cid, file=sys.stderr)
    cars = ok_cars
    today = datetime.date.today().isoformat()
    asof_day = None
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', status.get('updated', ''))
    if m:
        asof_day = (datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) - D0).days
    closed_map = {cd: detect_closed((status['data'].get(cd) or {}).get('note')) for cd in regions}
    open_cnt = sum(1 for cd in regions
                   if cd != '9999'
                   and ((status['data'].get(cd) or {}).get('left') or 0) > 0
                   and not closed_map[cd]['closed'])
    ctx = {'tpl_page': load_tpl('page.tpl'), 'tpl_region': load_tpl('region.tpl'),
           'tpl_car': load_tpl('car.tpl'), 'tpl_sido': load_tpl('sido.tpl'),
           'tpl_model': load_tpl('model.tpl'),
           'asof_day': asof_day if asof_day is not None else (datetime.date.today() - D0).days,
           'asof': status.get('updated', '')[:10],
           'closed_map': closed_map, 'open_cnt': open_cnt,
           'open_base': sum(1 for cd in regions if cd != '9999'),
           'rounds': rounds or {},
           'region_noindex': load_region_noindex() & set(regions)}
    # 색인 대상 차종 = 모델그룹 대표 트림(국비 최고 비단종, 동률은 id 낮은 쪽) — 트림 근사중복의 색인 노출 차단
    rep_by_group = {}
    for c in cars:
        if c['disc']:
            continue
        g = model_group(c)
        cur = rep_by_group.get(g)
        if cur is None or (c['nat'] or 0, -c['id']) > (cur['nat'] or 0, -cur['id']):
            rep_by_group[g] = c
    ctx['car_rep'] = {c['id'] for c in rep_by_group.values()}

    pages = {}   # 전부 메모리에서 완성 → 성공 시에만 원자 쓰기(부분 파일 금지)

    # 모델 시리즈 — car 상호링크가 '실제 생성된 편' 집합을 봐야 하므로 car보다 먼저 조립
    today_kst = datetime.datetime.now(KST).date().isoformat()
    pub_entries = []
    for e in load_model_entries(today_kst):
        html = build_model(e, cars, regions, meta, status, ctx)
        if html is None:
            continue                                   # 트림 전멸 등 — 무소음 강등
        pages[os.path.join(SITE, 'model', e['slug'] + '.html')] = html
        pub_entries.append(e)
    ctx['model_pub'] = {e['group']: e['slug'] for e in pub_entries}
    pages[os.path.join(SITE, 'model', 'index.html')] = build_model_hub(pub_entries, meta, status, ctx)

    for cd, r in regions.items():
        html, _ = build_region(cd, r, cars, regions, meta, status, hist, ctx)
        pages[os.path.join(SITE, 'region', cd + '.html')] = html
    for c in cars:
        html, _ = build_car(c, cars, regions, meta, status, ctx)
        pages[os.path.join(SITE, 'car', '%d.html' % c['id'])] = html
    for sido in SIDO_SLUG:
        pages[os.path.join(SITE, 'sido', SIDO_SLUG[sido] + '.html')] = build_sido(sido, regions, meta, status, ctx)

    # 일간 브리핑 허브 — 날짜 파일(daily_brief.py 산출물)은 여기서 생성하지 않고 목록만 읽음
    brief_days = list_brief_days(today_kst)
    pages[os.path.join(SITE, 'brief', 'index.html')] = build_brief_hub(brief_days, meta, status, ctx)
    if brief_days:
        # 홈 상단 배너용 최신 브리핑 메타(JS가 fetch — 없으면 배너는 정적 문구로 강등)
        pages[os.path.join(SITE, 'brief', 'latest.json')] = json.dumps(
            {'d': brief_days[0], 'desc': _brief_desc(brief_days[0])}, ensure_ascii=False)

    n_region = sum(1 for p in pages if os.sep + 'region' + os.sep in p)
    n_car = sum(1 for p in pages if os.sep + 'car' + os.sep in p)
    n_sido = sum(1 for p in pages if os.sep + 'sido' + os.sep in p)
    n_model = sum(1 for p in pages if os.sep + 'model' + os.sep in p)
    if (n_region != len(regions) or n_car != len(cars) or n_sido != len(SIDO_SLUG)
            or n_model != len(pub_entries) + 1):
        raise RuntimeError('페이지 수 불일치: region %d/%d car %d/%d sido %d/%d model %d/%d'
                           % (n_region, len(regions), n_car, len(cars), n_sido, len(SIDO_SLUG),
                              n_model, len(pub_entries) + 1))

    sitemap, n_urls, lm_store = build_sitemap(
        regions, cars, today, pub_entries, brief_days, ctx.get('car_rep'),
        pages=pages, store=load_lastmod_store(), region_noindex=ctx['region_noindex'])

    for path, html in pages.items():
        atomic_write(path, html)
    # 생성 대상에서 빠진 잔재 파일 정리(차종 삭제·발행 회수 등) — 이 5개 디렉터리는 생성기 소유.
    # 단 brief의 날짜 파일(YYYY-MM-DD.html)은 daily_brief.py 산출물이라 절대 삭제하지 않음(영구 보존).
    for sub in ('region', 'car', 'sido', 'model', 'brief'):
        droot = os.path.join(SITE, sub)
        if not os.path.isdir(droot):
            continue
        for fn in os.listdir(droot):
            fp = os.path.join(droot, fn)
            if sub == 'brief' and BRIEF_RE.fullmatch(fn):
                continue                       # 발행된 브리핑은 허브·사이트맵과 무관하게 보존
            if fn.endswith('.html') and fp not in pages:
                os.remove(fp)
    atomic_write(os.path.join(SITE, 'sitemap.xml'), sitemap)
    save_lastmod_store(lm_store)   # 사이트맵과 같은 회차의 해시만 남김(실패해도 빌드는 성공)

    dt = (datetime.datetime.now() - t0).total_seconds()
    n_rx = len(ctx['region_noindex']) + (1 if '9999' in regions else 0)   # 롱테일 + 한국환경공단
    print('prerender OK: region %d(noindex %d) · car %d · sido %d · model %d(허브 포함) · '
          'brief 허브+%d편 · sitemap %d URLs · lastmod 오늘자 %d/%d · %.1fs'
          % (n_region, n_rx, n_car, n_sido, n_model, len(brief_days), n_urls,
             sum(1 for v in lm_store.values() if v['d'] == today), len(lm_store), dt))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print('prerender FAIL: %s — 기존 정적 파일 유지' % e, file=sys.stderr)
        sys.exit(1)
