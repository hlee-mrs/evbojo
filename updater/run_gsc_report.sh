#!/bin/bash
# EV보조금 주간 서치콘솔 리포트 (launchd가 매주 월 09:20 실행)
# 수동 실행도 언제든 가능: bash updater/run_gsc_report.sh
set -u
export PATH="/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin"
REPO="/Users/hlee/Projects/전기차 보조금 현황"
LOG="$REPO/updater/gsc_report.log"
LOCK="$REPO/updater/.gsc.lock"

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

if ! mkdir "$LOCK" 2>/dev/null; then log "SKIP 이미 실행 중"; exit 0; fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

cd "$REPO" || { log "FAIL repo 없음"; exit 1; }
log "RUN 주간 리포트 시작"
/usr/bin/python3 updater/gsc_report.py >> "$LOG" 2>&1
RC=$?
case $RC in
  0) log "OK 리포트 생성 완료" ;;
  2) log "SETUP 서비스계정 키 미설정 — docs/7 참고" ;;
  *) log "FAIL rc=$RC — 위 로그 확인"
     osascript -e 'display notification "gsc_report.log 확인 필요" with title "EV보조금 GSC 리포트 실패"' 2>/dev/null ;;
esac

# 로그 롤링 (최근 1000줄)
tail -n 1000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit 0
