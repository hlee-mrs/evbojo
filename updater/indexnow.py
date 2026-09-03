#!/usr/bin/env python3
"""IndexNow 제출 — EV보조금 evbojo.co.kr (네이버·빙·얀덱스 등 공동 엔드포인트)

배포 직후 run_auto.sh가 호출한다. 이번 회차에 실제로 바뀐 페이지 URL만 검색엔진에 직접
통지해 사이트맵 재크롤을 기다리지 않게 하는 용도(국내 1위 네이버가 핵심 대상, 구글은 미참여).

- 엔드포인트: POST https://api.indexnow.org/indexnow (JSON: host/key/keyLocation/urlList).
  한 곳에 보내면 참여 엔진 전체에 공유된다. 요청당 URL 10,000건 이하.
- 키: updater/indexnow.json 의 "key" + 공개 키 파일 site/<key>.txt (내용 = 키 그대로).
  IndexNow 키는 프로토콜상 공개 값이므로 커밋해도 된다(public repo여도 무방).
- 입력: updater/.lastmod_changed.json — prerender가 이번 빌드에서 sitemap <lastmod>가 오늘로
  움직인 절대 URL을 기록한다. {"date": "YYYY-MM-DD", "urls": [...]}. 없거나 깨졌거나
  date가 오늘보다 오래되면(프리렌더 실패로 남은 옛 목록) 제출할 것이 없는 것으로 본다(--all 제외).
- 필터: https://evbojo.co.kr/ 로 시작 + site/sitemap.xml 의 <loc>에 있는 URL만.
  → noindex·미발행 페이지는 애초에 사이트맵에 없으므로 제출되지 않는다(헌법 I9와 자동 정합).
- 중복 방지: updater/.indexnow_sent.json = {url: 마지막 수락일}. 같은 날은 재제출 안 함,
  30일 지난 항목은 저장 시 정리. 429(과다 요청)는 기록하지 않고 다음 회차에 재시도.
- 응답: 200/202 수락 · 400 형식 오류 · 403 키 불일치 · 422 URL/호스트 불일치 · 429 과다 요청.
- 종료 코드: 제출할 것 없음/수락/429 = 0, 그 외 실패 = 1 (run_auto.sh는 실패해도 WARN만 남긴다).

표준라이브러리 전용(/usr/bin/python3 3.9). 모든 쓰기는 tmp + os.replace 원자 교체.
    /usr/bin/python3 updater/indexnow.py                # 이번 회차 변경분 제출(run_auto.sh가 호출)
    /usr/bin/python3 updater/indexnow.py --dry-run      # 제출 예정 목록만 출력, 네트워크 없음
    /usr/bin/python3 updater/indexnow.py --all          # 사이트맵 전체 제출(최초 1회 시드), 당일 중복 제외
    /usr/bin/python3 updater/indexnow.py --all --force  # 당일 중복 무시하고 전체 재제출
"""
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPDATER_DIR = os.path.join(ROOT, "updater")
SITE_DIR = os.path.join(ROOT, "site")
SITEMAP = os.path.join(SITE_DIR, "sitemap.xml")
KEY_META = os.path.join(UPDATER_DIR, "indexnow.json")
CHANGED_FILE = os.path.join(UPDATER_DIR, ".lastmod_changed.json")
SENT_FILE = os.path.join(UPDATER_DIR, ".indexnow_sent.json")

HOST = "evbojo.co.kr"
ORIGIN = "https://" + HOST + "/"
ENDPOINT = "https://api.indexnow.org/indexnow"
TIMEOUT = 30
USER_AGENT = "evbojo-indexnow/1.0 (+https://evbojo.co.kr)"
MAX_PER_REQUEST = 10000                          # IndexNow 요청당 URL 상한
KEEP_DAYS = 30                                   # 제출 이력 보존 기간
KEY_RE = re.compile(r"^[A-Za-z0-9-]{8,128}$")    # IndexNow 키 허용 형식
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TAG = "[indexnow]"
HTTP_HINT = {200: "수락", 202: "수락(처리 대기)", 400: "요청 형식 오류",
             403: "키 불일치(site/<key>.txt 미배포?)", 422: "URL·호스트 불일치", 429: "과다 요청"}
OPTIONS = ("--dry-run", "--all", "--force")


# ── 파일 유틸 ────────────────────────────────────────────────
def _load_json(path):
    """없거나 깨진 파일은 None."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _atomic_write_json(path, obj):
    """tmp에 쓰고 os.replace — 중간 상태 파일을 남기지 않는다."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


# ── 키 ───────────────────────────────────────────────────────
def load_key(path=KEY_META):
    """updater/indexnow.json 의 키. 없거나 형식이 틀리면 None."""
    meta = _load_json(path)
    key = meta.get("key") if isinstance(meta, dict) else None
    if not isinstance(key, str) or not KEY_RE.match(key):
        return None
    return key


def key_file_ok(key, site_dir=SITE_DIR):
    """공개 키 파일 site/<key>.txt 가 있고 내용이 키와 같은가."""
    try:
        with open(os.path.join(site_dir, key + ".txt"), encoding="utf-8") as f:
            return f.read().strip() == key
    except OSError:
        return False


# ── 대상 URL ─────────────────────────────────────────────────
def sitemap_urls(path=SITEMAP):
    """site/sitemap.xml 의 <loc> 목록(순서 유지·중복 제거). 파일이 없으면 None(=사이트맵 필터 생략)."""
    try:
        with open(path, encoding="utf-8") as f:
            xml = f.read()
    except OSError:
        return None
    out, seen = [], set()
    for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
        u = html.unescape(loc.strip())
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def changed_urls(path=CHANGED_FILE, today=None):
    """prerender가 남긴 이번 빌드 변경 URL 목록 → (urls, 사유).

    사유: None(정상) · "missing"(파일 없음) · "invalid"(형식 오류) · "stale"(date가 오늘보다 오래됨).
    """
    if not os.path.exists(path):
        return [], "missing"
    data = _load_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("urls"), list):
        return [], "invalid"
    date = data.get("date")
    if today and isinstance(date, str) and DATE_RE.match(date) and date < today:
        return [], "stale(date={})".format(date)
    return [u for u in data["urls"] if isinstance(u, str)], None


def load_sent(path=SENT_FILE):
    """{url: 마지막 수락일}. 없거나 깨졌으면 빈 dict."""
    data = _load_json(path)
    if not isinstance(data, dict):
        return {}
    return {u: d for u, d in data.items()
            if isinstance(u, str) and isinstance(d, str) and DATE_RE.match(d)}


def save_sent(sent, today, path=SENT_FILE, keep_days=KEEP_DAYS):
    """KEEP_DAYS 지난 항목을 정리한 뒤 원자 저장."""
    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=keep_days)).isoformat()
    _atomic_write_json(path, {u: d for u, d in sent.items() if d >= cutoff})


def select(candidates, sitemap, sent, today, force=False):
    """호스트·사이트맵·중복·당일 기제출 필터 → (대상 목록, 제외 사유별 건수)."""
    skipped = {"host": 0, "sitemap": 0, "dup": 0, "today": 0}
    picked, seen = [], set()
    for raw in candidates:
        u = raw.strip()
        if not u.startswith(ORIGIN):
            skipped["host"] += 1
            continue
        if sitemap is not None and u not in sitemap:
            skipped["sitemap"] += 1
            continue
        if u in seen:
            skipped["dup"] += 1
            continue
        seen.add(u)
        if not force and sent.get(u) == today:
            skipped["today"] += 1
            continue
        picked.append(u)
    return picked, skipped


# ── 제출 ─────────────────────────────────────────────────────
def submit(urls, key):
    """IndexNow POST 1회 → (HTTP 코드 또는 None, 응답 요약). 예외를 밖으로 내지 않는다."""
    body = json.dumps({
        "host": HOST,
        "key": key,
        "keyLocation": ORIGIN + key + ".txt",
        "urlList": urls,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read(300).decode("utf-8", "replace").strip()
    except urllib.error.HTTPError as ex:
        try:
            msg = ex.read(300).decode("utf-8", "replace").strip()
        except Exception:
            msg = ""
        return ex.code, msg
    except Exception as ex:                      # URLError·timeout·socket 등 네트워크 계열
        return None, "{}: {}".format(type(ex).__name__, ex)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    unknown = [a for a in argv if a not in OPTIONS]
    if unknown:
        print("{} 알 수 없는 옵션: {} (허용: {})".format(TAG, " ".join(unknown), " ".join(OPTIONS)))
        return 2
    dry, do_all, force = ("--dry-run" in argv), ("--all" in argv), ("--force" in argv)
    today = dt.date.today().isoformat()

    sitemap_list = sitemap_urls(SITEMAP)
    sitemap = set(sitemap_list) if sitemap_list is not None else None
    sent = load_sent(SENT_FILE)

    if do_all:
        candidates, reason, src = list(sitemap_list or []), None, "사이트맵 전체"
        if sitemap_list is None:
            print("{} 사이트맵 없음: {}".format(TAG, SITEMAP))
    else:
        candidates, reason = changed_urls(CHANGED_FILE, today)
        src = "이번 회차 변경분"
        if reason and reason != "missing":     # 파일 없음은 정상(프리렌더가 안 돈 회차) — 조용히 지나간다
            print("{} 변경 목록 {} — 건너뜀: {}".format(TAG, reason, CHANGED_FILE))

    pending, skipped = select(candidates, sitemap, sent, today, force=force)
    if candidates:
        print("{} {} 후보 {}건 → 대상 {}건 (호스트 외 {} · 사이트맵 외 {} · 중복 {} · 오늘 이미 제출 {})".format(
            TAG, src, len(candidates), len(pending),
            skipped["host"], skipped["sitemap"], skipped["dup"], skipped["today"]))
    if not pending:
        print("{} 제출 대상 없음".format(TAG))
        return 0

    key = load_key(KEY_META)
    if dry:
        print("{} (dry-run) 제출 예정 {}건 → {}  key={}".format(TAG, len(pending), ENDPOINT, key or "(없음)"))
        for u in pending:
            print("  " + u)
        return 0

    # 실제 제출 전 키 점검 — 키 파일이 없으면 서버가 403을 돌려주므로 미리 막는다
    if key is None:
        print("{} FAIL 키 없음/형식 오류: {}".format(TAG, KEY_META))
        return 1
    if not key_file_ok(key, SITE_DIR):
        print("{} FAIL 공개 키 파일 없음/불일치: site/{}.txt".format(TAG, key))
        return 1

    # 한 번에 보낸다(≤10,000건). 상한을 넘는 경우에만 나눠 보낸다.
    accepted, code = 0, None
    for i in range(0, len(pending), MAX_PER_REQUEST):
        chunk = pending[i:i + MAX_PER_REQUEST]
        code, msg = submit(chunk, key)
        if code in (200, 202):
            for u in chunk:
                sent[u] = today
            accepted += len(chunk)
            continue
        if accepted:                              # 앞 청크 수락분은 이력에 남긴다
            save_sent(sent, today, SENT_FILE)
        if code == 429:
            print("{} WARN HTTP 429 과다 요청 — 이번 회차 보류, 다음 회차 재시도 ({}건 미제출)".format(
                TAG, len(pending) - accepted))
            return 0
        where = "HTTP {} {}".format(code, HTTP_HINT.get(code, "")).strip() if code else "네트워크 오류"
        print("{} FAIL {}: {}".format(TAG, where, msg or "(응답 본문 없음)"))
        return 1

    save_sent(sent, today, SENT_FILE)
    print("{} 제출 {}건 (HTTP {})".format(TAG, accepted, code))
    return 0


if __name__ == "__main__":
    sys.exit(main())
