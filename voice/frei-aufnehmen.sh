#!/usr/bin/env bash
# frei-aufnehmen.sh – freies Erzählen am AT2020USB+ aufnehmen (eine Datei pro Sitzung).
# Aufruf:  bash voice/frei-aufnehmen.sh
# Stoppen: q drücken (oder Strg+C). Danach werden Länge und Pegel angezeigt.
set -euo pipefail
export LC_NUMERIC=C

QUELLE=alsa_input.usb-audio-technica_AT2020USB_-00.analog-stereo
ZIEL="${ZIEL:-$(cd "$(dirname "$0")" && pwd)/frei}"
mkdir -p "$ZIEL"
DATEI="$ZIEL/frei-$(date +%Y%m%d-%H%M%S).wav"

echo "Aufnahme läuft → $DATEI"
echo "Erzähl einfach los (mindestens 1 Minute). Beenden mit q."
ffmpeg -hide_banner -loglevel error -stats \
  -f pulse -i "$QUELLE" -ac 1 -ar 48000 -c:a pcm_s24le "$DATEI" || true

echo
echo "== Prüfung =="
dauer=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$DATEI")
printf "Länge: %.0f s\n" "$dauer"
ffmpeg -hide_banner -nostats -i "$DATEI" -af volumedetect -f null - 2>&1 \
  | grep -E "mean_volume|max_volume" | sed 's/.*\] //'
echo "Ziel: max_volume zwischen -12 und -3 dB (0 dB = übersteuert), mean_volume etwa -30 bis -20 dB."
ls -1 "$ZIEL"/*.wav | wc -l | xargs echo "Aufnahmen bisher:"
