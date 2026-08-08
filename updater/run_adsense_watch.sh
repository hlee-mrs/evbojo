#!/bin/bash
# 애드센스 승인 감시 — 매시간 launchd(com.evbojo.adsense)가 실행.
# 광고 게재가 처음 감지되면 macOS 알림을 띄우고 상태 파일에 기록(중복 알림 방지).
# 승인 확정 후에는 상태 파일 덕에 즉시 종료 — 잡을 내려도 되고 두어도 무해.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
STATE="$DIR/.adsense_state"
LOG="$DIR/adsense_watch.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

# 1순위: 공식 API 폴링(양방향 — 승인 READY·반려류 NEEDS_ATTENTION 모두 감지)
if [ -f "$DIR/secrets/adsense-oauth.json" ]; then
  OUT="$(/usr/bin/python3 "$DIR/check_adsense_api.py" 2>>"$LOG")"
  RC=$?
  log "api rc=$RC $OUT"
  [ "$RC" -eq 0 ] && exit 0
  log "API 실패 → 광고 게재 감지 방식으로 폴백"
fi

# 2순위(폴백): 광고 실게재 감지 — 승인만 감지 가능
# 이미 승인 감지됨 → 할 일 없음
[ "$(cat "$STATE" 2>/dev/null)" = "approved" ] && exit 0

OUT="$(/usr/bin/python3 "$DIR/check_adsense.py" 2>>"$LOG")"
RC=$?
log "rc=$RC $OUT"

if [ "$RC" -eq 0 ]; then
  echo "approved" > "$STATE"
  log "APPROVED — 광고 게재 첫 감지"
  osascript -e 'display notification "evbojo.co.kr에 광고 게재가 감지됐어요. 애드센스 콘솔에서 승인 상태를 확정 확인하세요." with title "🎉 애드센스 승인 신호 감지" sound name "Glass"' 2>/dev/null
fi
# rc=3(심사 중)·rc=2(일시 오류)는 로그만 남기고 다음 시간에 재시도

# 로그 롤링(1000줄)
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 1000 ]; then
  tail -500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
exit 0
