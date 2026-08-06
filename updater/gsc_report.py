#!/usr/bin/env python3
"""주간 Google Search Console 리포트 생성기 (EV보조금 evbojo.co.kr)

매주 월요일 launchd(com.evbojo.gscreport)가 실행. 의존성 없음(표준라이브러리+openssl).
- 인증: 서비스계정 JSON(updater/secrets/gsc-sa.json) → JWT를 openssl로 서명 → 액세스 토큰
- 데이터: Search Analytics API (sc-domain:evbojo.co.kr, webmasters.readonly)
- 출력: updater/reports/gsc-<종료일>.md (+ latest.md, raw/*.json) — repo가 public이라 git 미추적
- 알림: macOS 알림으로 주간 요약 1줄

설정(키 발급·권한)은 docs/7-주간-GSC-리포트.md 참고.
"""
import base64
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SA_KEY_PATH = os.path.join(ROOT, "updater", "secrets", "gsc-sa.json")
OUT_DIR = os.path.join(ROOT, "updater", "reports")
SITE = "sc-domain:evbojo.co.kr"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
API = "https://searchconsole.googleapis.com/webmasters/v3/sites/{}/searchAnalytics/query".format(
    urllib.parse.quote(SITE, safe=""))

# 순위를 매주 추적할 관심 키워드 (자유롭게 수정)
WATCH_QUERIES = [
    "전기차 보조금",
    "전기차 보조금 조회",
    "전기차 보조금 계산기",
    "전기차 구매 보조금",
    "전기차 유지비 계산기",
]


def notify(title, msg):
    try:
        subprocess.run(["osascript", "-e",
                        'display notification "{}" with title "{}"'.format(
                            msg.replace('"', "'"), title.replace('"', "'"))],
                       check=False, capture_output=True, timeout=10)
    except Exception:
        pass


def b64u(b: bytes) -> bytes:
    return base64.urlsafe_b64encode(b).rstrip(b"=")


def get_token(key: dict) -> str:
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    header = b64u(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = b64u(json.dumps({
        "iss": key["client_email"], "scope": SCOPE,
        "aud": key["token_uri"], "iat": now, "exp": now + 3600,
    }).encode())
    signing_input = header + b"." + claims
    # 개인키는 secrets 디렉터리 안에서만 임시 파일로 존재
    with tempfile.NamedTemporaryFile(dir=os.path.dirname(SA_KEY_PATH), suffix=".pem") as f:
        f.write(key["private_key"].encode())
        f.flush()
        sig = subprocess.run(["openssl", "dgst", "-sha256", "-sign", f.name],
                             input=signing_input, capture_output=True, check=True).stdout
    jwt = signing_input + b"." + b64u(sig)
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt.decode(),
    }).encode()
    req = urllib.request.Request(key["token_uri"], data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["access_token"]


def query(token: str, start: str, end: str, dims, row_limit=500):
    body = json.dumps({"startDate": start, "endDate": end,
                       "dimensions": dims, "rowLimit": row_limit}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r).get("rows", [])


def totals(date_rows):
    c = sum(r["clicks"] for r in date_rows)
    i = sum(r["impressions"] for r in date_rows)
    pos = (sum(r["position"] * r["impressions"] for r in date_rows) / i) if i else 0.0
    ctr = (c / i * 100) if i else 0.0
    return c, i, ctr, pos


def delta(cur, prev, fmt="{:+,.0f}"):
    return fmt.format(cur - prev)


def rows_by_key(rows):
    return {r["keys"][0]: r for r in rows}


def fnum(n):
    return "{:,}".format(int(n))


def main():
    if not os.path.exists(SA_KEY_PATH):
        print("[설정 필요] 서비스계정 키가 없습니다:", SA_KEY_PATH)
        print("docs/7-주간-GSC-리포트.md의 1회 설정을 완료하면 다음 주부터 리포트가 생성됩니다.")
        notify("EV보조금 GSC 리포트", "설정 필요: 서비스계정 키 없음 (docs/7 참고)")
        return 2

    key = json.load(open(SA_KEY_PATH))
    try:
        token = get_token(key)
    except Exception as e:
        print("[실패] 토큰 발급:", e)
        notify("EV보조금 GSC 리포트", "실패: 구글 토큰 발급 오류 (gsc_report.log 확인)")
        return 3

    # 기간: GSC 데이터는 약 3일 지연 → 종료=오늘-3일, 7일 창 + 직전 7일 비교
    today = dt.date.today()
    end = today - dt.timedelta(days=3)
    start = end - dt.timedelta(days=6)
    p_end = start - dt.timedelta(days=1)
    p_start = p_end - dt.timedelta(days=6)
    s, e, ps, pe = (d.isoformat() for d in (start, end, p_start, p_end))

    try:
        cur_dates = query(token, s, e, ["date"], 40)
        prev_dates = query(token, ps, pe, ["date"], 40)
        cur_q = query(token, s, e, ["query"], 500)
        prev_q = query(token, ps, pe, ["query"], 500)
        cur_p = query(token, s, e, ["page"], 200)
        prev_p = query(token, ps, pe, ["page"], 200)
    except urllib.error.HTTPError as ex:
        body = ex.read().decode(errors="replace")[:400]
        print("[실패] API {}: {}".format(ex.code, body))
        if ex.code == 403:
            print("→ 서치콘솔 속성에 서비스계정({})이 '제한된' 사용자로 추가됐는지 확인하세요.".format(
                key.get("client_email", "?")))
        notify("EV보조금 GSC 리포트", "실패: API {} (gsc_report.log 확인)".format(ex.code))
        return 3

    c, i, ctr, pos = totals(cur_dates)
    pc, pi, pctr, ppos = totals(prev_dates)
    pq, pp = rows_by_key(prev_q), rows_by_key(prev_p)

    L = []
    L.append("# EV보조금 주간 서치콘솔 리포트 — {} ~ {}".format(s, e))
    L.append("")
    L.append("전주({} ~ {}) 대비. GSC 데이터는 약 3일 지연, 날짜는 태평양시 기준.".format(ps, pe))
    L.append("")
    L.append("## 총괄")
    L.append("| 지표 | 이번 주 | 전주 | 증감 |")
    L.append("|---|---:|---:|---:|")
    L.append("| 클릭 | {} | {} | {} |".format(fnum(c), fnum(pc), delta(c, pc)))
    L.append("| 노출 | {} | {} | {} |".format(fnum(i), fnum(pi), delta(i, pi)))
    L.append("| CTR | {:.1f}% | {:.1f}% | {:+.1f}%p |".format(ctr, pctr, ctr - pctr))
    if i and pi:
        L.append("| 평균 게재순위 | {:.1f} | {:.1f} | {:+.1f} |".format(pos, ppos, pos - ppos))
    elif i:
        L.append("| 평균 게재순위 | {:.1f} | — | — |".format(pos))

    L.append("")
    L.append("## 관심 키워드")
    L.append("| 키워드 | 노출 | 클릭 | 순위 | 전주 순위 |")
    L.append("|---|---:|---:|---:|---:|")
    cq = rows_by_key(cur_q)
    for w in WATCH_QUERIES:
        r, prv = cq.get(w), pq.get(w)
        L.append("| {} | {} | {} | {} | {} |".format(
            w,
            fnum(r["impressions"]) if r else "0",
            fnum(r["clicks"]) if r else "0",
            "{:.1f}".format(r["position"]) if r else "—",
            "{:.1f}".format(prv["position"]) if prv else "—"))

    L.append("")
    L.append("## TOP 검색어 (클릭·노출순 15)")
    L.append("| 검색어 | 클릭 | 노출 | 순위 | 전주 클릭 |")
    L.append("|---|---:|---:|---:|---:|")
    top_q = sorted(cur_q, key=lambda r: (-r["clicks"], -r["impressions"]))[:15]
    for r in top_q:
        prv = pq.get(r["keys"][0])
        L.append("| {} | {} | {} | {:.1f} | {} |".format(
            r["keys"][0], fnum(r["clicks"]), fnum(r["impressions"]),
            r["position"], fnum(prv["clicks"]) if prv else "0"))
    if not top_q:
        L.append("| (데이터 없음) | | | | |")

    new_q = sorted((r for r in cur_q if r["keys"][0] not in pq),
                   key=lambda r: -r["impressions"])[:10]
    if new_q:
        L.append("")
        L.append("## 신규 진입 검색어 (전주 미노출 → 이번 주 노출)")
        L.append("| 검색어 | 노출 | 클릭 | 순위 |")
        L.append("|---|---:|---:|---:|")
        for r in new_q:
            L.append("| {} | {} | {} | {:.1f} |".format(
                r["keys"][0], fnum(r["impressions"]), fnum(r["clicks"]), r["position"]))

    L.append("")
    L.append("## TOP 페이지 (10)")
    L.append("| 페이지 | 클릭 | 노출 | 전주 클릭 |")
    L.append("|---|---:|---:|---:|")
    for r in sorted(cur_p, key=lambda r: (-r["clicks"], -r["impressions"]))[:10]:
        url = r["keys"][0].replace("https://evbojo.co.kr", "") or "/"
        prv = pp.get(r["keys"][0])
        L.append("| {} | {} | {} | {} |".format(
            url, fnum(r["clicks"]), fnum(r["impressions"]),
            fnum(prv["clicks"]) if prv else "0"))

    L.append("")
    L.append("## 일별 추이 (2주)")
    L.append("| 날짜 | 클릭 | 노출 |")
    L.append("|---|---:|---:|")
    for r in sorted(prev_dates + cur_dates, key=lambda r: r["keys"][0]):
        L.append("| {} | {} | {} |".format(r["keys"][0], fnum(r["clicks"]), fnum(r["impressions"])))

    os.makedirs(os.path.join(OUT_DIR, "raw"), exist_ok=True)
    md_path = os.path.join(OUT_DIR, "gsc-{}.md".format(e))
    with open(md_path, "w") as f:
        f.write("\n".join(L) + "\n")
    with open(os.path.join(OUT_DIR, "latest.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    with open(os.path.join(OUT_DIR, "raw", "gsc-{}.json".format(e)), "w") as f:
        json.dump({"period": [s, e], "prev": [ps, pe],
                   "dates": cur_dates, "prev_dates": prev_dates,
                   "queries": cur_q, "prev_queries": prev_q,
                   "pages": cur_p, "prev_pages": prev_p}, f, ensure_ascii=False)

    print("[완료] {} (클릭 {} / 노출 {})".format(md_path, fnum(c), fnum(i)))
    notify("EV보조금 주간 GSC 리포트",
           "클릭 {} ({}) · 노출 {} ({})".format(fnum(c), delta(c, pc), fnum(i), delta(i, pi)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
