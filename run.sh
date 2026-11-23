#!/usr/bin/env sh
# Loop: pull latest code from GitHub, check seats, wait. Edits to watch.py apply on the next cycle.
cd "$(dirname "$0")"
termux-wake-lock 2>/dev/null
while true; do
  git pull -q --ff-only || echo "git pull failed, using local copy"
  NTFY_TOPIC="${NTFY_TOPIC:-f0efcceaf0c3}" python watch.py
  sleep "${INTERVAL:-300}"
done
