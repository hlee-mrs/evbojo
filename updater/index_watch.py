#!/usr/bin/env python3
"""색인 상태 모니터링 (Google Search Console URL Inspection API) — EV보조금 evbojo.co.kr

"구글이 우리 편집 콘텐츠를 실제로 색인했는가"를 사람이 GSC를 열지 않고 확인하기 위한 모듈.

- 인증: gsc_report.py의 서비스계정 JWT 흐름 재사용(스코프 webmasters.readonly — 실호출로 동작 확인).
- API: POST https://searchconsole.googleapis.com/v1/urlInspection/index:inspect
- 감시 대상: site/sitemap.xml에서 **편집 콘텐츠만** 추린 목록(루트 정적 + /sido/ + /model/).
  사이트맵을 정본으로 쓰므로 noindex·미발행 페이지는 애초에 조회하지 않는다(헌법 I9와 자동 정합).
- 쿼터: URL Inspection은 일 2,000 / 분 600 수준. 대상 ~55개를 **하루 1회**만 조회하고,
  같은 날 두 번째 호출은 그날 스냅샷(updater/reports/index-YYYY-MM-DD.json)을 재사용한다.
- 출력: updater/reports/index-YYYY-MM-DD.json (원본 스냅샷)
        + gsc_report.py 주간 리포트의 "## 색인 현황" 섹션(render_section)

표준라이브러리 전용. 단독 실행도 가능:
    /usr/bin/python3 updater/index_watch.py            # 하루 1회(캐시 있으면 재사용)
    /usr/bin/python3 updater/index_watch.py --force    # 캐시 무시하고 재조회
    /usr/bin/python3 updater/index_watch.py --print    # 마크다운 섹션 미리보기
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITEMAP = os.path.join(ROOT, "site", "sitemap.xml")
OUT_DIR = os.path.join(ROOT, "updater", "reports")
SITE_URL = "sc-domain:evbojo.co.kr"
ORIGIN = "https://evbojo.co.kr"
INSPECT_API = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
LANG = "ko"

# 쿼터·예절 파라미터 (환경변수로 조정 가능)
MAX_URLS = int(os.environ.get("INDEX_MAX_URLS", "60"))     # 하루 조회 상한
DELAY = float(os.environ.get("INDEX_DELAY", "1.0"))        # 요청 간 간격(초)
RETRIES = 3                                                # 429/5xx 지수 백오프 횟수

# 편집 콘텐츠 우선순위 — 앞쪽부터 채우고 MAX_URLS에서 자른다.
CORE_PAGES = ["/", "/articles.html", "/about.html", "/guide.html", "/law.html", "/faq.html"]
BUCKET_ORDER = ["core", "sido", "model", "article"]


# ── 감시 대상 목록 ────────────────────────────────────────────
def _bucket(path):
    """사이트맵 경로 → 감시 버킷. 편집 콘텐츠가 아니면 None(=조회 안 함)."""
    if path in CORE_PAGES:
        return "core"
    if path.startswith("/sido/"):
        return "sido"
    if path.startswith("/model/"):
        return "model"
    if "/" not in path[1:]:          # 루트 단일 계층 정적 해설 페이지
        return "article"
    return None                       # /region/·/car/ 등 데이터 페이지는 제외


def watch_urls(sitemap_path=SITEMAP, limit=MAX_URLS):
    """site/sitemap.xml에서 편집 콘텐츠 URL만 추려 (url, bucket) 리스트로 반환.

    사이트맵에 없는 것(noindex·미발행)은 대상이 아니다 — 조회 낭비이자 정책상 색인 기대 대상이 아님.
    """
    with open(sitemap_path, encoding="utf-8") as f:
        xml = f.read()
    locs = re.findall(r"<loc>([^<]+)</loc>", xml)
    picked, seen = [], set()
    for loc in locs:
        url = loc.strip()
        if not url.startswith(ORIGIN):
            continue
        path = url[len(ORIGIN):] or "/"
        b = _bucket(path)
        if b is None or url in seen:
            continue
        seen.add(url)
        picked.append((url, b))
    picked.sort(key=lambda t: (BUCKET_ORDER.index(t[1]),
                               CORE_PAGES.index(t[0][len(ORIGIN):] or "/")
                               if t[1] == "core" else 0))
    return picked[:limit]


# ── API 호출 ─────────────────────────────────────────────────
class QuotaExceeded(Exception):
    pass


def inspect(token, url, site_url=SITE_URL, timeout=60):
    """URL 1건 검사 → indexStatusResult(dict). 쿼터 초과는 QuotaExceeded로 올린다."""
    body = json.dumps({"inspectionUrl": url, "siteUrl": site_url,
                       "languageCode": LANG}).encode()
    req = urllib.request.Request(INSPECT_API, data=body, method="POST", headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json"})
    wait = 2.0
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
            return data.get("inspectionResult", {}).get("indexStatusResult", {}) or {}
        except urllib.error.HTTPError as ex:
            msg = ex.read().decode(errors="replace")[:300]
            if ex.code == 429 or (ex.code == 403 and "uota" in msg):
                raise QuotaExceeded("{} {}".format(ex.code, msg))
            if ex.code >= 500 and attempt < RETRIES - 1:
                time.sleep(wait)
                wait *= 2
                continue
            raise RuntimeError("HTTP {}: {}".format(ex.code, msg))
        except Exception as ex:
            if attempt < RETRIES - 1:
                time.sleep(wait)
                wait *= 2
                continue
            raise RuntimeError(str(ex))


def _default_token():
    """단독 실행용 — gsc_report의 서비스계정 토큰 발급을 재사용(순환 import 회피 위해 지연 import)."""
    sys.path.insert(0, os.path.join(ROOT, "updater"))
    import gsc_report
    return gsc_report.get_token(json.load(open(gsc_report.SA_KEY_PATH)))


# ── 스냅샷 수집·저장 ──────────────────────────────────────────
def snapshot_path(day):
    return os.path.join(OUT_DIR, "index-{}.json".format(day))


def collect(token, urls, delay=DELAY, verbose=False):
    """감시 대상 전체 조회. 쿼터 초과 시 그 시점까지의 결과를 담아 정상 반환(부분 수집)."""
    results, errors, quota = [], [], False
    for n, (url, bucket) in enumerate(urls, 1):
        if n > 1 and delay > 0:
            time.sleep(delay)
        try:
            r = inspect(token, url)
        except QuotaExceeded as ex:
            quota = True
            errors.append({"url": url, "error": "quota", "message": str(ex)})
            if verbose:
                print("[쿼터] {} 에서 중단: {}".format(url, ex))
            break
        except Exception as ex:
            errors.append({"url": url, "error": "request", "message": str(ex)})
            if verbose:
                print("[오류] {}: {}".format(url, ex))
            continue
        results.append({
            "url": url, "bucket": bucket,
            "verdict": r.get("verdict", "UNKNOWN"),
            "coverageState": r.get("coverageState", ""),
            "lastCrawlTime": r.get("lastCrawlTime", ""),
            "robotsTxtState": r.get("robotsTxtState", ""),
            "indexingState": r.get("indexingState", ""),
            "pageFetchState": r.get("pageFetchState", ""),
            "googleCanonical": r.get("googleCanonical", ""),
            "userCanonical": r.get("userCanonical", ""),
        })
        if verbose:
            print("[{}/{}] {} → {} / {}".format(
                n, len(urls), url, r.get("verdict", "UNKNOWN"), r.get("coverageState", "")))
    return results, errors, quota


def run(token=None, force=False, verbose=False, limit=MAX_URLS, delay=DELAY):
    """하루 1회 스냅샷. 오늘자 파일이 있고 force가 아니면 재조회 없이 그대로 쓴다."""
    day = dt.date.today().isoformat()
    path = snapshot_path(day)
    if not force and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            snap = json.load(f)
        snap["cached"] = True
        return snap

    urls = watch_urls(limit=limit)
    if not urls:
        raise RuntimeError("감시 대상 0건 — sitemap.xml 확인 필요")
    if token is None:
        token = _default_token()

    results, errors, quota = collect(token, urls, delay=delay, verbose=verbose)
    snap = {
        "date": day,
        "generated": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "site": SITE_URL,
        "requested": len(urls),
        "checked": len(results),
        "quota_exceeded": quota,
        "results": results,
        "errors": errors,
        "cached": False,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)          # 원자 교체 — 중간 상태 파일을 남기지 않는다
    return snap


def previous_snapshot(before_day):
    """before_day 이전의 가장 최근 스냅샷(dict) 또는 None."""
    if not os.path.isdir(OUT_DIR):
        return None
    days = []
    for name in os.listdir(OUT_DIR):
        m = re.fullmatch(r"index-(\d{4}-\d{2}-\d{2})\.json", name)
        if m and m.group(1) < before_day:
            days.append(m.group(1))
    if not days:
        return None
    try:
        with open(snapshot_path(max(days)), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ── 마크다운 섹션 ─────────────────────────────────────────────
BUCKET_KO = {"core": "핵심", "article": "해설", "sido": "시도 시리즈", "model": "모델 시리즈"}


def _counts(results):
    c = {}
    for r in results:
        c[r.get("verdict", "UNKNOWN")] = c.get(r.get("verdict", "UNKNOWN"), 0) + 1
    return c


def _short(url):
    return url.replace(ORIGIN, "") or "/"


def _crawl_day(v):
    return v[:10] if v else "—"


def render_section(snap, prev=None):
    """주간 리포트에 붙일 '## 색인 현황' 마크다운 줄 리스트."""
    res = snap.get("results", [])
    if prev is None:
        prev = previous_snapshot(snap.get("date", dt.date.today().isoformat()))
    cur_c = _counts(res)
    prev_res = (prev or {}).get("results", [])
    prev_c = _counts(prev_res)
    passed = cur_c.get("PASS", 0)
    total = len(res)

    L = []
    L.append("")
    L.append("## 색인 현황")
    L.append("")
    L.append("URL Inspection API 실측({} 조회, 감시 대상 {}건 중 {}건 응답). "
             "감시 대상 = sitemap.xml의 편집 콘텐츠(핵심·해설·시도·모델).".format(
                 snap.get("date", "?"), snap.get("requested", total), total))
    if snap.get("quota_exceeded"):
        L.append("")
        L.append("> ⚠️ 쿼터 초과로 조회가 중단됨 — 아래 수치는 부분 집계다.")
    if not res:
        L.append("")
        L.append("응답 0건 — 집계 생략(조회 실패 {}건).".format(len(snap.get("errors", []))))
        return L
    L.append("")
    L.append("**색인됨(verdict=PASS) {}/{}**{}".format(
        passed, total,
        " · 전 스냅샷({}) {}/{}".format(prev.get("date"), prev_c.get("PASS", 0), len(prev_res))
        if prev else ""))
    L.append("")
    L.append("| 판정 | 이번 | 전 스냅샷 | 증감 |")
    L.append("|---|---:|---:|---:|")
    for v in sorted(set(cur_c) | set(prev_c), key=lambda k: (-cur_c.get(k, 0), k)):
        a, b = cur_c.get(v, 0), prev_c.get(v, 0)
        L.append("| {} | {} | {} | {:+d} |".format(v, a, b, a - b))

    # 버킷별 색인률 — 어느 시리즈가 통째로 안 들어갔는지 한눈에
    L.append("")
    L.append("| 구분 | 색인 | 대상 |")
    L.append("|---|---:|---:|")
    for b in BUCKET_ORDER:
        rows = [r for r in res if r.get("bucket") == b]
        if rows:
            L.append("| {} | {} | {} |".format(
                BUCKET_KO.get(b, b), sum(1 for r in rows if r.get("verdict") == "PASS"), len(rows)))

    # 핵심 산출물 — 색인 안 된 편집 페이지(색인 요청을 쓸 곳)
    miss = [r for r in res if r.get("verdict") != "PASS"]
    L.append("")
    L.append("### 색인 안 된 편집 페이지 ({}건)".format(len(miss)))
    if miss:
        L.append("")
        L.append("| 페이지 | 구분 | 판정 | 상태 | 최근 크롤 |")
        L.append("|---|---|---|---|---|")
        for r in sorted(miss, key=lambda r: (BUCKET_ORDER.index(r.get("bucket", "article"))
                                             if r.get("bucket") in BUCKET_ORDER else 9,
                                             r["url"])):
            L.append("| {} | {} | {} | {} | {} |".format(
                _short(r["url"]), BUCKET_KO.get(r.get("bucket"), r.get("bucket", "—")),
                r.get("verdict", "—"), r.get("coverageState", "—") or "—",
                _crawl_day(r.get("lastCrawlTime"))))
        L.append("")
        L.append("→ 색인 요청(Search Console URL 검사 > 색인 생성 요청)은 이 목록 위쪽부터.")
    else:
        L.append("")
        L.append("없음 — 감시 대상 전부 색인됨.")

    # 전 스냅샷 대비 상태 전환
    if prev_res:
        pmap = {r["url"]: r.get("verdict") for r in prev_res}
        gained = [r["url"] for r in res
                  if r.get("verdict") == "PASS" and pmap.get(r["url"]) not in (None, "PASS")]
        lost = [r["url"] for r in res
                if r.get("verdict") != "PASS" and pmap.get(r["url"]) == "PASS"]
        if gained or lost:
            L.append("")
            L.append("### 전 스냅샷 대비 변화")
            L.append("")
            for u in sorted(gained):
                L.append("- 신규 색인: {}".format(_short(u)))
            for u in sorted(lost):
                L.append("- 색인 이탈: {}".format(_short(u)))

    # 표준 URL 불일치 — 중복 판정 신호
    canon = [r for r in res if r.get("googleCanonical") and r.get("userCanonical")
             and r["googleCanonical"] != r["userCanonical"]]
    if canon:
        L.append("")
        L.append("### 표준 URL 불일치 ({}건)".format(len(canon)))
        L.append("")
        L.append("| 페이지 | 구글이 고른 표준 |")
        L.append("|---|---|")
        for r in canon:
            L.append("| {} | {} |".format(_short(r["url"]), _short(r["googleCanonical"])))

    errs = snap.get("errors", [])
    if errs:
        L.append("")
        L.append("조회 실패 {}건: {}".format(
            len(errs), ", ".join("{}({})".format(_short(e["url"]), e.get("error")) for e in errs[:5])))
    return L


def summary_line(snap):
    res = snap.get("results", [])
    return "색인 {}/{}".format(sum(1 for r in res if r.get("verdict") == "PASS"), len(res))


def main():
    force = "--force" in sys.argv
    snap = run(force=force, verbose=True)
    print("[스냅샷] {} ({}{})".format(snapshot_path(snap["date"]), summary_line(snap),
                                     ", 캐시 재사용" if snap.get("cached") else ""))
    if "--print" in sys.argv:
        print("\n".join(render_section(snap)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
