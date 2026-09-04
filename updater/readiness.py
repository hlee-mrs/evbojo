#!/usr/bin/env python3
"""애드센스 재신청 준비도 게이트 — EV보조금 evbojo.co.kr

"지금 재신청해도 되는가"를 사람의 감이 아니라 실측 기준으로 매일 판정하는 모듈.

- 배경: 애드센스 3회 반려(저가치)의 실제 원인은 구글이 편집 콘텐츠 대부분을 크롤·색인한 적이 없어
  심사 입력에 편집 페이지가 들어가지 않았던 것(2026-08-30 GSC 색인 리포트로 규명). 실패 패턴은
  "수정이 구글에 보이기 전에 재신청" — 이 게이트는 그 패턴을 수치로 막는다.
- 입력: index_watch.py의 하루 1회 색인 스냅샷(updater/reports/index-YYYY-MM-DD.json)
        + selfcheck.py 정합 검사 + site/sitemap.xml + GSC Search Analytics + 라이브 status.json
- 판정: 기준 R1~R8을 전부 통과해야 GO, 하나라도 미충족이면 WAIT.
        측정 불가(ok=None)는 판정을 막지 않고 '미측정'으로 따로 표기한다.
- 출력: updater/reports/readiness.json(전체 결과) · readiness.md(마크다운)
        · readiness-history.jsonl(일별 1줄 이력) — repo가 public이라 reports/는 git 미추적
        + gsc_report.py 주간 리포트의 "## 재신청 준비도 게이트" 섹션(render_lines)
- 실행 경로: index_watch.py main() 끝에서 매일 07:40 자동 호출(com.evbojo.indexwatch).

표준라이브러리 전용. 단독 실행:
    /usr/bin/python3 updater/readiness.py                  # 판정 + 리포트 파일 갱신
    /usr/bin/python3 updater/readiness.py --print          # 마크다운 미리보기까지 출력
    /usr/bin/python3 updater/readiness.py --no-selfcheck   # R4 생략(느린 정합 검사 건너뜀)
    /usr/bin/python3 updater/readiness.py --no-gsc         # R6 생략 + 색인 스냅샷은 캐시만 사용(오프라인)
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "updater")
SITEMAP = os.path.join(ROOT, "site", "sitemap.xml")
OUT_DIR = os.path.join(HERE, "reports")
OUT_JSON = os.path.join(OUT_DIR, "readiness.json")
OUT_MD = os.path.join(OUT_DIR, "readiness.md")
OUT_HISTORY = os.path.join(OUT_DIR, "readiness-history.jsonl")
LIVE_STATUS_URL = "https://evbojo.co.kr/data/status.json"
ORIGIN = "https://evbojo.co.kr"
KST = dt.timezone(dt.timedelta(hours=9))
UA = "evbojo-readiness/1.0 (+https://evbojo.co.kr/about.html)"

# 형제 모듈(selfcheck·index_watch·gsc_report) import 경로 — launchd 최소 환경에서도 동작
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ── 판정 기준(임계값) — 근거는 애드센스 3차 반려(2026-08-26) 원인 규명 결과 ──────────
# R1 편집 콘텐츠 색인률. 8/31 실측 37%(54건 중 20건) 상태에서 재신청하면 심사 입력의 과반이
#    자동 생성 지역 페이지가 된다 → 편집 표면의 60% 이상이 색인된 뒤에만 재신청.
R1_MIN_INDEX_RATE = 0.60
# R2 해설 아티클(루트 단일 계층 정적 페이지) 색인률. '저가치' 판정의 직접 대상이 이 버킷이며
#    8/31 실측 22편 중 4편(18%)뿐이었다 → 절반 이상 색인이 최소선.
R2_MIN_ARTICLE_RATE = 0.50
# R3 '크롤링됨 - 현재 색인이 생성되지 않음' = 구글이 읽고도 색인 가치가 없다고 본 페이지.
#    이 상태의 편집 페이지가 남아 있으면 심사도 같은 판단을 한다 → 0건.
R3_MAX_CRAWLED_NOT_INDEXED = 0
# R4 selfcheck 정합 검사(상태 정합·산문↔표·광고 I4·색인 I9·금칙어·링크·구조) 위반 0건.
R4_MAX_SELFCHECK = 0
# R5 편집 표면(region·car 제외 sitemap URL)의 최종 변경 후 안정 기간. 구글 재크롤·재평가에
#    ~2주가 걸리므로 그 전에 재신청하면 고치기 전 상태가 심사된다(리서치 검증: 최소 2주, 권장 4주).
R5_MIN_STABLE_DAYS = 14
# R6 최근 7일 클릭 ≥ 직전 7일의 80% — 주간 변동 허용폭. 하락 추세에서의 재신청은 성장 근거가 없다.
R6_CLICK_RATIO = 0.8
# R7 sitemap lastmod가 '오늘'인 URL 비율 상한. 전 URL이 매일 갱신되면 '자동 생성 페이지' 신호
#    (8/30 규명된 크롤 차단 원인 ②) → 실변경일만 갱신되는지 매일 확인.
R7_MAX_TODAY_LASTMOD = 0.25
# R8 라이브 status.json 신선도 — 매시 무인 갱신 파이프라인(launchd → gh-pages → Cloudflare)이
#    살아 있어야 심사관이 보는 페이지가 최신이다.
R8_MAX_STALE_HOURS = 3
# GSC Search Analytics는 약 3일 지연 → 7일 창의 종료일 = 오늘-3일 (gsc_report.py와 동일)
GSC_LAG_DAYS = 3
GSC_WINDOW_DAYS = 7

# 색인 스냅샷의 버킷 키(index_watch._bucket) — '해설' 아티클은 article
ARTICLE_BUCKET = "article"
BUCKET_KO = {"core": "핵심", "article": "해설", "sido": "시도 시리즈", "model": "모델 시리즈"}

LABELS = {
    "R1": ("편집 콘텐츠 색인률", "≥ {:.0f}%".format(R1_MIN_INDEX_RATE * 100)),
    "R2": ("해설 아티클 색인률", "≥ {:.0f}%".format(R2_MIN_ARTICLE_RATE * 100)),
    "R3": ("크롤링됨-미색인 편집 페이지", "{}건".format(R3_MAX_CRAWLED_NOT_INDEXED)),
    "R4": ("selfcheck 위반", "{}건".format(R4_MAX_SELFCHECK)),
    "R5": ("편집 표면 안정 기간", "≥ {}일".format(R5_MIN_STABLE_DAYS)),
    "R6": ("검색 클릭 추세(7일 vs 직전 7일)", "≥ {:.0f}%".format(R6_CLICK_RATIO * 100)),
    "R7": ("sitemap lastmod 당일 비율", "< {:.0f}%".format(R7_MAX_TODAY_LASTMOD * 100)),
    "R8": ("라이브 status.json 신선도", "≤ {}시간".format(R8_MAX_STALE_HOURS)),
}


# ── 공통 유틸 ────────────────────────────────────────────────
def _now():
    return dt.datetime.now(KST)


def _crit(cid, value, ok, note="", raw=None):
    """기준 1건 dict. ok: True(충족) / False(미충족) / None(미측정 — 판정에서 제외)."""
    label, target = LABELS[cid]
    return {"id": cid, "label": label, "value": value, "target": target,
            "ok": ok, "note": note, "raw": raw}


def _skipped(cid, why):
    return _crit(cid, "미측정", None, "생략({})".format(why))


def _pct(n, d):
    return "{}% ({}/{})".format(int(round(n * 100.0 / d)) if d else 0, n, d)


def _short(url):
    return url.replace(ORIGIN, "") or "/"


def _parse_iso(s):
    """'2026-09-04T00:10+09:00' 류 ISO 문자열 → aware datetime. 오프셋이 없으면 KST로 간주."""
    s = (s or "").strip()
    if not s:
        raise ValueError("빈 날짜")
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?"
                         r"(?:([+-])(\d{2}):?(\d{2}))?", s)
        if not m:
            raise
        y, mo, da, hh, mm, ss, sign, oh, om = m.groups()
        tz = KST
        if sign:
            off = dt.timedelta(hours=int(oh), minutes=int(om))
            tz = dt.timezone(off if sign == "+" else -off)
        d = dt.datetime(int(y), int(mo), int(da), int(hh), int(mm), int(ss or 0), tzinfo=tz)
    if d.tzinfo is None:
        d = d.replace(tzinfo=KST)
    return d


def _atomic_write(path, text):
    """tmp에 완성 후 os.replace — 중간 상태 파일을 남기지 않는다."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _token():
    """GSC 서비스계정 토큰 — gsc_report의 JWT 흐름 재사용(키는 gsc_report.SA_KEY_PATH만 읽는다)."""
    import gsc_report
    with open(gsc_report.SA_KEY_PATH, encoding="utf-8") as f:
        key = json.load(f)
    return gsc_report.get_token(key)


def sitemap_entries(path=SITEMAP):
    """site/sitemap.xml → [(경로, lastmod date 또는 None)]. 정본 sitemap을 그대로 읽는다."""
    with open(path, encoding="utf-8") as f:
        xml = f.read()
    out = []
    for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>([^<]+)</loc>", block)
        if not loc:
            continue
        url = loc.group(1).strip()
        p = url[len(ORIGIN):] if url.startswith(ORIGIN) else url
        lm = re.search(r"<lastmod>([^<]+)</lastmod>", block)
        day = None
        if lm:
            try:
                day = dt.date.fromisoformat(lm.group(1).strip()[:10])
            except ValueError:
                day = None
        out.append((p or "/", day))
    return out


def _is_editorial(path):
    """R5의 편집 표면 = 루트 정적·해설 페이지.
    /region/·/car/(데이터 페이지)뿐 아니라 /sido/·/model/ 시리즈도 제외한다 — 시리즈는 잔여·상태에
    연동돼 거의 매일 lastmod가 움직여 '14일 안정'이 구조적으로 불가능했다(2026-09-01~04 실측: 편집
    URL 무변경일 0일). 원고 자체를 고친 날만 R5가 리셋되게 루트 페이지 기준으로 잰다."""
    return not path.startswith(("/region/", "/car/", "/sido/", "/model/"))


# ── 기준별 측정 ──────────────────────────────────────────────
def _passed(results):
    return sum(1 for r in results if r.get("verdict") == "PASS"), len(results)


def _snap_note(snap, prev_snap, results_filter=None):
    """R1·R2 비고 — 전 스냅샷 대비 수치 + 쿼터 초과 표시."""
    parts = []
    if prev_snap and prev_snap.get("results"):
        prev = prev_snap["results"]
        if results_filter:
            prev = [r for r in prev if results_filter(r)]
        pn, pd = _passed(prev)
        parts.append("전 스냅샷({}) {}".format(prev_snap.get("date", "?"), _pct(pn, pd)))
    if snap.get("quota_exceeded"):
        parts.append("쿼터 초과 부분 집계")
    return " · ".join(parts)


def crit_index_rate(snap, prev_snap):
    """R1 — 편집 콘텐츠(감시 대상 전체) 중 verdict=PASS 비율."""
    res = snap.get("results", [])
    n, d = _passed(res)
    if d == 0:
        return _crit("R1", "응답 0건", False, "스냅샷에 결과 없음", 0.0)
    rate = n / d
    return _crit("R1", _pct(n, d), rate >= R1_MIN_INDEX_RATE,
                 _snap_note(snap, prev_snap), round(rate * 100, 1))


def crit_article_rate(snap, prev_snap):
    """R2 — 해설 아티클 버킷만 따로 본 색인률."""
    flt = lambda r: r.get("bucket") == ARTICLE_BUCKET  # noqa: E731
    res = [r for r in snap.get("results", []) if flt(r)]
    n, d = _passed(res)
    if d == 0:
        return _crit("R2", "대상 0건", False, "스냅샷에 해설 버킷 없음", 0.0)
    rate = n / d
    return _crit("R2", _pct(n, d), rate >= R2_MIN_ARTICLE_RATE,
                 _snap_note(snap, prev_snap, flt), round(rate * 100, 1))


def crit_crawled_not_indexed(snap):
    """R3 — coverageState가 '크롤링됨'으로 시작하는 편집 페이지 수."""
    hit = [r for r in snap.get("results", [])
           if (r.get("coverageState") or "").startswith("크롤링됨")]
    note = ", ".join(_short(r["url"]) for r in hit[:3])
    if len(hit) > 3:
        note += " 외 {}건".format(len(hit) - 3)
    return _crit("R3", "{}건".format(len(hit)), len(hit) <= R3_MAX_CRAWLED_NOT_INDEXED,
                 note, len(hit))


def crit_selfcheck():
    """R4 — selfcheck.run() 위반 건수. 검사기 자체가 죽으면 미충족(검사기 오류)으로 표기."""
    try:
        import selfcheck
        total, head, lines = selfcheck.run(selfcheck.SITE, selfcheck.DATA, quiet=True)
    except Exception as ex:
        return _crit("R4", "검사 실패", False,
                     "검사기 오류: {}: {}".format(type(ex).__name__, str(ex)[:80]))
    fails = [ln[len("[FAIL] "):] for ln in lines if ln.startswith("[FAIL]")]
    note = "; ".join(fails[:3])
    if len(fails) > 3:
        note += "; 외 {}종".format(len(fails) - 3)
    return _crit("R4", "{}건".format(total), total <= R4_MAX_SELFCHECK, note, total)


def crit_surface_stable(today, sitemap_path=SITEMAP):
    """R5 — 편집 표면의 최근 lastmod 이후 경과일. 미충족이면 (기준, eta) 로 검토 가능일을 함께 돌려준다."""
    try:
        entries = sitemap_entries(sitemap_path)
    except Exception as ex:
        return _crit("R5", "측정 실패", False,
                     "sitemap 오류: {}: {}".format(type(ex).__name__, str(ex)[:80])), None
    days = [d for p, d in entries if _is_editorial(p) and d]
    if not days:
        return _crit("R5", "측정 실패", False, "편집 URL의 lastmod 없음"), None
    last = max(days)
    age = (today - last).days
    ok = age >= R5_MIN_STABLE_DAYS
    eta = None if ok else (last + dt.timedelta(days=R5_MIN_STABLE_DAYS)).isoformat()
    return _crit("R5", "{}일 (최근 변경 {})".format(age, last.isoformat()), ok,
                 "편집 URL {}건 기준".format(len(days)), age), eta


def crit_click_trend(token, today):
    """R6 — GSC 클릭: 최근 7일(종료=오늘-3일) vs 직전 7일. API 실패는 미측정(None)."""
    end = today - dt.timedelta(days=GSC_LAG_DAYS)
    start = end - dt.timedelta(days=GSC_WINDOW_DAYS - 1)
    p_end = start - dt.timedelta(days=1)
    p_start = p_end - dt.timedelta(days=GSC_WINDOW_DAYS - 1)
    window = "{}~{} vs {}~{}".format(start.isoformat()[5:], end.isoformat()[5:],
                                     p_start.isoformat()[5:], p_end.isoformat()[5:])
    try:
        if token is None:
            token = _token()
        import gsc_report
        cur = gsc_report.query(token, start.isoformat(), end.isoformat(), ["date"], 40)
        prev = gsc_report.query(token, p_start.isoformat(), p_end.isoformat(), ["date"], 40)
    except Exception as ex:
        return _crit("R6", "미측정", None,
                     "{}: {}".format(type(ex).__name__, str(ex)[:80]))
    c = sum(int(r.get("clicks", 0)) for r in cur)
    pc = sum(int(r.get("clicks", 0)) for r in prev)
    # 직전 7일이 0이면 비율을 정의할 수 없다 → 이번 7일에 클릭이 있으면 비하락으로 본다
    ok = c >= R6_CLICK_RATIO * pc or (pc == 0 and c > 0)
    ratio = "{:.0f}%".format(c * 100.0 / pc) if pc else "—"
    return _crit("R6", "{} / 직전 {} ({})".format(c, pc, ratio), ok, window,
                 {"clicks": c, "prev": pc})


def crit_lastmod_today(today, sitemap_path=SITEMAP):
    """R7 — sitemap 전체 URL 중 lastmod가 오늘(KST)인 비율."""
    try:
        entries = sitemap_entries(sitemap_path)
    except Exception as ex:
        return _crit("R7", "측정 실패", False,
                     "sitemap 오류: {}: {}".format(type(ex).__name__, str(ex)[:80]))
    total = len(entries)
    if total == 0:
        return _crit("R7", "URL 0건", False, "sitemap 비어 있음")
    n = sum(1 for p, d in entries if d == today)
    rate = n / total
    return _crit("R7", _pct(n, total), rate < R7_MAX_TODAY_LASTMOD, "", round(rate * 100, 1))


def crit_live_fresh(now):
    """R8 — 라이브 status.json의 updated가 지금(KST)으로부터 3시간 이내인가."""
    try:
        req = urllib.request.Request(LIVE_STATUS_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        updated = data.get("updated", "")
        age_h = (now - _parse_iso(updated)).total_seconds() / 3600.0
    except Exception as ex:
        return _crit("R8", "조회 실패", False,
                     "{}: {}".format(type(ex).__name__, str(ex)[:80]))
    return _crit("R8", "{} ({:.1f}시간 전)".format(updated, age_h),
                 age_h <= R8_MAX_STALE_HOURS, "", round(age_h, 2))


# ── 판정 ─────────────────────────────────────────────────────
def evaluate(snap, prev_snap=None, token=None, run_selfcheck=True, use_gsc=True):
    """색인 스냅샷 + 부가 실측으로 GO/WAIT 판정. token이 없으면 R6에서만 발급을 시도한다."""
    now = _now()
    today = now.date()
    snap_date = snap.get("date", "?")
    if prev_snap is None:
        try:
            import index_watch
            prev_snap = index_watch.previous_snapshot(snap_date)
        except Exception:
            prev_snap = None

    criteria = [crit_index_rate(snap, prev_snap),
                crit_article_rate(snap, prev_snap),
                crit_crawled_not_indexed(snap),
                crit_selfcheck() if run_selfcheck else _skipped("R4", "--no-selfcheck")]
    c5, eta = crit_surface_stable(today)
    criteria.append(c5)
    criteria.append(crit_click_trend(token, today) if use_gsc else _skipped("R6", "--no-gsc"))
    criteria.append(crit_lastmod_today(today))
    criteria.append(crit_live_fresh(now))

    unmet = [c["id"] for c in criteria if c["ok"] is False]
    unmeasured = [c["id"] for c in criteria if c["ok"] is None]
    return {
        "verdict": "GO" if not unmet else "WAIT",
        "date": today.isoformat(),
        "generated": now.isoformat(timespec="seconds"),
        "snapshot": {"date": snap_date, "checked": len(snap.get("results", [])),
                     "cached": bool(snap.get("cached")), "fallback": bool(snap.get("fallback"))},
        "criteria": criteria,
        "unmet": unmet,
        "unmeasured": unmeasured,
        "eta": eta if unmet else None,   # R5(시간 기준)가 충족되는 날 — 다른 기준은 별도
    }


# ── 마크다운 ─────────────────────────────────────────────────
def _cell(s):
    return str(s).replace("|", "／").replace("\n", " ")


def render_lines(result):
    """주간 리포트·readiness.md에 붙일 '## 재신청 준비도 게이트' 마크다운 줄 리스트."""
    snap = result.get("snapshot", {})
    src = "색인 스냅샷 {}({}건".format(snap.get("date", "?"), snap.get("checked", 0))
    if snap.get("fallback"):
        src += ", 이전 날짜 캐시로 대체"
    elif snap.get("cached"):
        src += ", 캐시 재사용"
    src += ")"

    L = []
    L.append("")
    L.append("## 재신청 준비도 게이트")
    L.append("")
    L.append("**판정: {}** ({})".format(result["verdict"], result["date"]))
    L.append("")
    L.append("{} · 기준 {}개 전부 충족 시 GO, 미측정(—)은 판정에서 제외.".format(
        src, len(result.get("criteria", []))))
    L.append("")
    L.append("| # | 기준 | 현재 | 목표 | 판정 |")
    L.append("|---|---|---|---|:-:|")
    for c in result.get("criteria", []):
        mark = "✅" if c["ok"] is True else ("❌" if c["ok"] is False else "—")
        L.append("| {} | {} | {} | {} | {} |".format(
            c["id"], _cell(c["label"]), _cell(c["value"]), _cell(c["target"]), mark))
    notes = [c for c in result.get("criteria", []) if c.get("note")]
    if notes:
        L.append("")
        for c in notes:
            L.append("- {} 비고: {}".format(c["id"], c["note"]))
    if result.get("unmeasured"):
        L.append("")
        L.append("- 미측정: {}".format(", ".join(result["unmeasured"])))
    if result["verdict"] == "WAIT":
        L.append("")
        L.append("- 미충족: {}".format(", ".join(result.get("unmet", [])) or "없음"))
        if result.get("eta"):
            L.append("- 가장 이른 재신청 검토일: {} (R5 안정 기간 충족일 — 나머지 기준은 별도 충족 필요)".format(
                result["eta"]))
    return L


def summary_line(result):
    return "[readiness] 판정 {} — 미충족: {}".format(
        result["verdict"], ", ".join(result.get("unmet", [])) or "없음")


# ── 스냅샷 확보·파일 출력 ─────────────────────────────────────
def latest_snapshot():
    """reports/의 가장 최근 index-YYYY-MM-DD.json(dict) 또는 None — 오프라인 대체 경로."""
    if not os.path.isdir(OUT_DIR):
        return None
    days = [m.group(1) for m in (re.fullmatch(r"index-(\d{4}-\d{2}-\d{2})\.json", n)
                                 for n in os.listdir(OUT_DIR)) if m]
    if not days:
        return None
    path = os.path.join(OUT_DIR, "index-{}.json".format(max(days)))
    try:
        with open(path, encoding="utf-8") as f:
            snap = json.load(f)
    except Exception:
        return None
    snap["cached"] = True
    return snap


def load_snapshot(token=None, live=True):
    """색인 스냅샷 확보. live면 index_watch.run(오늘자 캐시 재사용, 없으면 API 조회),
    실패하거나 live가 아니면 최신 index-*.json으로 대체해 오프라인에서도 판정이 나오게 한다."""
    if live:
        try:
            import index_watch
            return index_watch.run(token=token)
        except Exception as ex:
            print("[경고] 색인 스냅샷 조회 실패 — 최신 캐시로 대체: {}: {}".format(
                type(ex).__name__, str(ex)[:80]))
    snap = latest_snapshot()
    if snap is None:
        raise RuntimeError("색인 스냅샷 없음 — index_watch.py를 먼저 실행")
    snap["fallback"] = snap.get("date") != _now().date().isoformat()
    return snap


def _append_history(result):
    """readiness-history.jsonl에 오늘 1줄 추가(마지막 줄이 이미 오늘이면 건너뜀)."""
    old = ""
    if os.path.exists(OUT_HISTORY):
        with open(OUT_HISTORY, encoding="utf-8") as f:
            old = f.read()
    last = old.rstrip("\n").rsplit("\n", 1)[-1] if old.strip() else ""
    if last:
        try:
            if json.loads(last).get("date") == result["date"]:
                return False
        except ValueError:
            pass
    raw = {c["id"].lower(): c.get("raw") for c in result["criteria"]}
    rec = {"date": result["date"], "verdict": result["verdict"], "unmet": result["unmet"],
           "unmeasured": result["unmeasured"], "r1": raw.get("r1"), "r2": raw.get("r2"),
           "r3": raw.get("r3"), "r4": raw.get("r4"), "r5": raw.get("r5")}
    line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
    body = old if not old or old.endswith("\n") else old + "\n"
    _atomic_write(OUT_HISTORY, body + line + "\n")
    return True


def run(snap=None, token=None, run_selfcheck=True, use_gsc=True):
    """판정 후 reports/readiness.{json,md} + history 기록. snap을 주면 재조회 없이 그대로 쓴다."""
    live = use_gsc
    if snap is None and use_gsc and token is None:
        try:
            token = _token()
        except Exception as ex:
            print("[경고] GSC 토큰 발급 실패 — 캐시 스냅샷·R6 미측정으로 진행: {}: {}".format(
                type(ex).__name__, str(ex)[:80]))
            live = False
    if snap is None:
        snap = load_snapshot(token=token, live=live)

    result = evaluate(snap, token=token, run_selfcheck=run_selfcheck, use_gsc=use_gsc)

    _atomic_write(OUT_JSON, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    md = ["# 재신청 준비도 — {}".format(result["date"])] + render_lines(result)
    _atomic_write(OUT_MD, "\n".join(md) + "\n")
    _append_history(result)
    print(summary_line(result))
    return result


def main():
    args = sys.argv[1:]
    try:
        result = run(run_selfcheck="--no-selfcheck" not in args,
                     use_gsc="--no-gsc" not in args)
    except Exception as ex:
        print("[실패] readiness: {}: {}".format(type(ex).__name__, ex))
        return 1
    if "--print" in args:
        print("\n".join(render_lines(result)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
