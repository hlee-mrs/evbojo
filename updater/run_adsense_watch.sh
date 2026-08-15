#!/bin/bash
# 애드센스 승인 감시 — 매시간 launchd(com.evbojo.adsense)가 실행.
# 공식 API 폴링 단독(승인 READY·반려류 NEEDS_ATTENTION 모두 감지). 알림은 check_adsense_api.py가 직접 띄움.
# 실패(자격증명 없음·API 오류) 시에는 로그만 남기고 다음 시간에 재시도 — 헤드리스 폴백은 제거함
# (사이트를 브라우저로 여는 방식은 진단 외 상시 실행 가치가 없고 오탐 여지가 있음. 수동 진단은 check_adsense.py 직접 실행).
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/adsense_watch.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

if [ -f "$DIR/secrets/adsense-oauth.json" ]; then
  OUT="$(/usr/bin/python3 "$DIR/check_adsense_api.py" 2>>"$LOG")"
  RC=$?
  log "api rc=$RC $OUT"
  [ "$RC" -ne 0 ] && log "API 확인 실패 — 다음 시간에 재시도"
else
  log "oauth 자격증명 없음(secrets/adsense-oauth.json) — API 확인 생략"
fi

# 로그 롤링(1000줄)
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 1000 ]; then
  tail -500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
exit 0
