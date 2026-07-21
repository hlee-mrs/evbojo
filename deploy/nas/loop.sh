#!/bin/bash
# EV보조금 자동 수집 루프 (NAS 컨테이너 안에서 24시간 실행)
# 매시 :10 — 잔여현황(--status) / 04:10 — 전체 재수집(--once, 40% 변경 보류 가드 내장)
# 수집 → site/data 변경 시에만 main 커밋·푸시 → gh-pages 배포. 실패는 로그만 남기고 다음 회차 재시도.
set -u
export TZ=Asia/Seoul
LOG=/logs/auto.log
log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

cd /repo || exit 1
git config user.name  "evbojo-updater"
git config user.email "hlee9108@gmail.com"
# 이미지에 git-subtree가 빠져 있으면 보강 (Ubuntu 패키지에 포함되지만 방어적으로)
git subtree -h >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq git >/dev/null 2>&1; }

log "===== 컨테이너 시작 (playwright $(python3 -c 'import playwright; print(getattr(playwright,\"__version__\",\"?\"))' 2>/dev/null)) ====="

while true; do
  # 다음 :10 까지 대기
  now=$(date +%s)
  next=$(date -d "$(date '+%Y-%m-%d %H'):10:00" +%s)
  [ "$next" -le "$now" ] && next=$((next + 3600))
  sleep $((next - now))

  # 원격 최신화 (다른 세션 커밋과 합류)
  if ! git fetch origin >> "$LOG" 2>&1; then log "FAIL fetch — 다음 회차 재시도"; continue; fi
  if ! git rebase --autostash origin/main >> "$LOG" 2>&1; then
    git rebase --abort >> "$LOG" 2>&1
    log "FAIL rebase 충돌 — 이번 회차 건너뜀"; continue
  fi

  H=$(date +%H)
  if [ "$H" = "04" ]; then MODE="--once"; else MODE="--status"; fi
  log "RUN $MODE"
  if ! python3 updater/update.py "$MODE" >> "$LOG" 2>&1; then
    log "FAIL 수집($MODE) — 기존 데이터 유지"; continue
  fi

  if git diff --quiet -- site/data; then log "OK 변경 없음"; continue; fi
  git add site/data
  git commit -q -m "data: 자동 갱신($MODE) $(date '+%F %H:%M')" || { log "FAIL commit"; continue; }
  if ! git push origin HEAD:main >> "$LOG" 2>&1; then log "FAIL push main — 다음 회차 재시도"; continue; fi

  SHA=$(git subtree split --prefix site HEAD 2>> "$LOG" | tail -1)
  if [ -n "$SHA" ] && git push -f origin "${SHA}:refs/heads/gh-pages" >> "$LOG" 2>&1; then
    log "OK 배포 완료 ($SHA)"
  else
    log "FAIL gh-pages 배포"
  fi

  tail -n 3000 "$LOG" > "$LOG.t" 2>/dev/null && mv "$LOG.t" "$LOG"
done
