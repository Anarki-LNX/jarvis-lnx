#!/usr/bin/env bash
# Rendert public/img/og-{en,de}.png aus og/og.html mit headless Chromium (schonend, eigenes Wegwerf-Profil).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .tmp public/img
for l in en de; do
  prof=$(mktemp -d -p .tmp chrome-XXXXXX)
  timeout 60 nice -n 19 ionice -c3 chromium --headless=new --disable-gpu --no-first-run --no-default-browser-check \
    --user-data-dir="$PWD/$prof" --hide-scrollbars --force-device-scale-factor=1 --window-size=1200,630 \
    --virtual-time-budget=1500 --screenshot="$PWD/public/img/og-$l.png" "file://$PWD/og/og.html#$l" >/dev/null 2>&1 || true
  rm -rf "$prof"
done
ls -la public/img/og-*.png
