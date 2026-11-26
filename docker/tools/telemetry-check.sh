#!/bin/bash
# NuOrb: Telemetrie-Prüfung des Images, vollständig offline (--network none).
# 1. mit den Standard-Einstellungen des Images  -> erwartet: 0 Verbindungsversuche
# 2. Gegenprobe mit ausgeschaltetem Schalter    -> erwartet: > 0 (zeigt, dass die Prüfung wirkt)
# Aufruf: tools/telemetry-check.sh [image]   (Standard: jarvis-lnx:test)
set -euo pipefail
IMG=${1:-jarvis-lnx:test}
HERE=$(cd "$(dirname "$0")" && pwd)
run() {
  docker run --rm --network none \
    --add-host mobile.events.data.microsoft.com:127.0.0.1 --add-host self.events.data.microsoft.com:127.0.0.1 \
    --add-host browser.events.data.microsoft.com:127.0.0.1 --add-host v10.events.data.microsoft.com:127.0.0.1 \
    "$@" -v "$HERE/telemetry_probe.py:/w/probe.py:ro" --entrypoint /opt/jarvis/venv/bin/python "$IMG" -I /w/probe.py 45 2>&1 \
    | sed -n 's/^connections: \([0-9]*\).*/\1/p'
}
a=$(run); b=$(run -e ORT_DISABLE_TELEMETRY=)
echo "Image-Standard: $a Verbindungsversuche (erwartet 0); Gegenprobe ohne Schalter: $b (erwartet > 0)"
[ "$a" = 0 ] && [ "${b:-0}" -gt 0 ] && echo "OK: keine Telemetrie" || { echo "FEHLER"; exit 1; }
