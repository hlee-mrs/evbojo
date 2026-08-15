#!/bin/bash
# EV보조금 자동 수집+배포 (launchd가 매시 :10에 실행)
# - 매시간: --status (잔여현황 + history.json)
# - 04시:   --once  (차종·지방비 full + status, full은 40% 변경 보류 가드 내장)
# 실패 시 updater 자체 fail-safe가 기존 데이터 유지. 여기선 로그만 남기고 다음 시간에 재시도.
set -u
export PATH="/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin"
REPO="/Users/hlee/Projects/전기차 보조금 현황"
LOG="$REPO/updater/auto.log"
LOCK="$REPO/updater/.auto.lock"

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

# 중복 실행 방지 (full이 오래 걸려 다음 시간과 겹칠 수 있음)
if ! mkdir "$LOCK" 2>/dev/null; then log "SKIP 이미 실행 중"; exit 0; fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

cd "$REPO" || { log "FAIL repo 없음"; exit 1; }

# 원격 최신화 (다른 세션 커밋과 충돌 방지)
git fetch origin >> "$LOG" 2>&1
git rebase --autostash origin/main >> "$LOG" 2>&1 || { git rebase --abort >> "$LOG" 2>&1; log "FAIL rebase 충돌 — 이번 회차 건너뜀"; exit 1; }

# 04시엔 전체 재수집(--once = full+status), 그 외엔 status만
HOUR=$(date +%H)
if [ "$HOUR" = "04" ]; then MODE="--once"; else MODE="--status"; fi
log "RUN $MODE 시작"
if ! /usr/bin/python3 updater/update.py "$MODE" >> "$LOG" 2>&1; then
  log "FAIL 수집 실패($MODE) — 기존 데이터 유지, 다음 시간 재시도"
  exit 1
fi

# 변경 없으면 종료 (불필요한 커밋·배포 방지)
if git diff --quiet -- site/data; then log "OK 변경 없음"; exit 0; fi

# 프리렌더 (지역·차종·시도 정적 페이지 + sitemap 전량 재생성)
# 실패해도 데이터 갱신·배포는 계속한다 — 기존 정적 페이지가 유지되므로 안전(fail-safe).
if /usr/bin/python3 updater/prerender.py >> "$LOG" 2>&1; then
  git add site/region site/car site/sido site/model site/brief site/sitemap.xml >> "$LOG" 2>&1 || log "WARN prerender 산출물 add 실패"
else
  log "WARN prerender 실패 — 기존 정적 페이지 유지, 데이터만 배포"
fi

git add site/data
git commit -q -m "data: 자동 갱신($MODE) $(date '+%F %H:%M')" || { log "FAIL commit"; exit 1; }
git push origin HEAD:main >> "$LOG" 2>&1 || { log "FAIL push main — 다음 시간 재시도"; exit 1; }

SHA=$(git subtree split --prefix site HEAD 2>> "$LOG" | tail -1)
if [ -n "$SHA" ] && git push -f origin "${SHA}:refs/heads/gh-pages" >> "$LOG" 2>&1; then
  log "OK 배포 완료 ($SHA)"
else
  log "FAIL gh-pages 배포"
  exit 1
fi

# 로그 비대 방지 (최근 2000줄 유지)
tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
