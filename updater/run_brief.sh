#!/bin/bash
# EV보조금 일간 브리핑 발행 (launchd가 매일 08:20 KST 실행)
# - daily_brief.py: 그날 1편 생성(변화 없음·stale이면 스킵 — 정상 종료)
# - 생성 시 prerender로 허브·사이트맵 갱신 후 run_auto.sh와 동일 rebase·subtree 패턴으로 배포
# - 실패 시에만 macOS 알림. 그 외에는 로그만.
set -u
export PATH="/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin"
REPO="/Users/hlee/Projects/전기차 보조금 현황"
LOG="$REPO/updater/brief.log"
LOCK="$REPO/updater/.brief.lock"
AUTOLOCK="$REPO/updater/.auto.lock"

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }
notify() { /usr/bin/osascript -e "display notification \"$1\" with title \"EV보조금 브리핑\"" >/dev/null 2>&1 || true; }

# 중복 실행 방지 (자체 락)
if ! mkdir "$LOCK" 2>/dev/null; then log "SKIP 이미 실행 중"; exit 0; fi
# updater와 양방향 상호배제: .auto.lock을 직접 획득(성공까지 최대 5분).
# run_auto는 이 락이 있으면 그 회차를 스스로 스킵하므로 git 작업이 절대 겹치지 않음.
GOT_AUTO=""
for _ in $(seq 1 30); do
  if mkdir "$AUTOLOCK" 2>/dev/null; then GOT_AUTO=1; break; fi
  sleep 10
done
if [ -z "$GOT_AUTO" ]; then
  rmdir "$LOCK" 2>/dev/null
  log "SKIP updater 장기 실행 중 — 이번 회차 건너뜀"
  exit 0
fi
# 종료 시: 락 해제 + 모든 경로에서 로그 롤링(최근 2000줄)
trap 'rmdir "$AUTOLOCK" "$LOCK" 2>/dev/null; tail -n 2000 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"' EXIT

cd "$REPO" || { log "FAIL repo 없음"; notify "브리핑 실패: repo 없음"; exit 1; }

# 원격 최신화 (충돌 시 이번 회차 건너뜀 — abort는 내 rebase가 진행 중일 때만)
git fetch origin >> "$LOG" 2>&1
if ! git rebase --autostash origin/main >> "$LOG" 2>&1; then
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then git rebase --abort >> "$LOG" 2>&1; fi
  log "FAIL rebase 충돌 — 이번 회차 건너뜀"
  exit 1
fi

log "RUN daily_brief 시작"
if ! OUT=$(/usr/bin/python3 updater/daily_brief.py 2>> "$LOG"); then
  log "FAIL daily_brief 생성 실패 — brief.log 확인"
  notify "브리핑 생성 실패 — brief.log 확인"
  exit 1
fi
log "$OUT"
case "$OUT" in
  *"brief SKIP"*) log "OK 스킵 — 커밋 없음"; exit 0;;
esac

# 허브·사이트맵 최신화 (brief 통합부는 prerender 소유 — 실패해도 브리핑 본문은 배포)
if /usr/bin/python3 updater/prerender.py >> "$LOG" 2>&1; then
  git add site/brief site/sitemap.xml site/region site/car site/sido site/model >> "$LOG" 2>&1 || log "WARN prerender 산출물 add 실패"
else
  log "WARN prerender 실패 — 브리핑 본문만 배포"
  git add site/brief >> "$LOG" 2>&1
fi

if git diff --cached --quiet; then log "OK 변경 없음"; exit 0; fi
git commit -q -m "brief: 일간 브리핑 $(date '+%F')" || { log "FAIL commit"; exit 1; }
# push 실패는 실패로 처리하지 않음 — 로컬 커밋이 남아 다음 시간 updater 커밋에 편승 배포됨
git push origin HEAD:main >> "$LOG" 2>&1 || { log "WARN push 실패 — 다음 시간 updater 커밋에 편승"; exit 0; }

SHA=$(git subtree split --prefix site HEAD 2>> "$LOG" | tail -1)
if [ -n "$SHA" ] && git push -f origin "${SHA}:refs/heads/gh-pages" >> "$LOG" 2>&1; then
  log "OK 배포 완료 ($SHA)"
else
  log "WARN gh-pages 배포 실패 — 다음 시간 updater 배포에 편승"
fi

# 로그 롤링은 trap EXIT에서 모든 경로에 대해 수행
