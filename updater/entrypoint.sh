#!/bin/bash
# EV보조금 갱신 스케줄러 — 컨테이너 안에서 무한 루프
#  · 매 STATUS_EVERY_MIN 분: 접수현황(status.json)
#  · 매일 FULL_AT_HOUR 시(KST): 전체 단가 재수집(cars/regions/meta)
set -u
STATUS_EVERY_MIN="${STATUS_EVERY_MIN:-60}"
FULL_AT_HOUR="${FULL_AT_HOUR:-4}"

echo "[entrypoint] pip deps..."
pip install --quiet playwright==1.45.0 2>/dev/null
# 이미지에 브라우저 포함되어 있지만, 버전 mismatch 대비
python -m playwright install chromium 2>/dev/null || true

LAST_FULL_DAY=""
# 시작 시 1회 즉시 현황 갱신
python /app/updater/update.py --status || echo "[entrypoint] 초기 status 실패 — 다음 주기에 재시도"

# 재시작 시 오늘 이미 full을 돌렸다면 건너뛰도록 마커 파일 사용
MARKER=/app/updater/.last_full
[ -f "$MARKER" ] && LAST_FULL_DAY=$(cat "$MARKER")

while true; do
  sleep "$((STATUS_EVERY_MIN * 60))"
  HOUR=$((10#$(TZ=Asia/Seoul date +%H)))
  DAY=$(TZ=Asia/Seoul date +%F)
  # 하루 1회, FULL_AT_HOUR시 이후 첫 주기에 전체 재수집 (재시작·지연에도 안전)
  if [ "$DAY" != "$LAST_FULL_DAY" ] && [ "$HOUR" -ge "$FULL_AT_HOUR" ]; then
    echo "[entrypoint] daily full update..."
    if python /app/updater/update.py --full; then
      LAST_FULL_DAY="$DAY"; echo "$DAY" > "$MARKER"
    fi
  fi
  python /app/updater/update.py --status || echo "[entrypoint] status 실패 — 기존 데이터 유지"
done
