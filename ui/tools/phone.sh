#!/usr/bin/env bash
: "${JARVIS_HOST:?set JARVIS_HOST (see config.env.example)}"
: "${PHONE_HOST:?set PHONE_HOST (see config.env.example)}"
# Testhilfe: Eingaben/Screenshots auf dem JARVIS-Handy (cage-Kiosk) per SSH.
#   phone.sh shot <datei.png>     Bildschirmfoto nach <datei.png> (lokal)
#   phone.sh key F14|F15|Return   Taste senden (wtype)
#   phone.sh type "Text"          Text tippen (wtype)
#   phone.sh log [n]              letzte Client-Log-Zeilen des Handys (aus dem jarvis-Journal)
set -euo pipefail
P=jarvis@${PHONE_HOST}; K=~/.ssh/id_ed25519_jarvis
ENV='export XDG_RUNTIME_DIR=/run/user/$(id -u) WAYLAND_DISPLAY=wayland-0;'
case "$1" in
  shot) ssh -o BatchMode=yes -i $K $P "$ENV /nix/store/rkc1f876ap766p918r1va5jps3f30c2j-grim-1.5.0/bin/grim -" > "$2" ;;
  key)  ssh -o BatchMode=yes -i $K $P "$ENV wtype -k $2" ;;
  type) ssh -o BatchMode=yes -i $K $P "$ENV wtype $(printf %q "$2")" ;;
  log)  ssh -o BatchMode=yes -i $K root@${JARVIS_HOST} "journalctl -u jarvis-ui --since -15min --no-pager | grep 'client ${PHONE_HOST}' | cut -c 1-16,40-260 | tail -${2:-8}" ;;
esac
