#!/usr/bin/env bash
: "${NUORB_SERVER_IP:?set NUORB_SERVER_IP (see config.env.example)}"
: "${PHONE_HOST:?set PHONE_HOST (see config.env.example)}"
# Testhilfe: Eingaben/Screenshots auf dem NuOrb-Handy (cage-Kiosk) per SSH.
#   phone.sh shot <datei.png>     Bildschirmfoto nach <datei.png> (lokal)
#   phone.sh key F14|F15|Return   Taste senden (wtype)
#   phone.sh type "Text"          Text tippen (wtype)
#   phone.sh log [n]              letzte Client-Log-Zeilen des Handys (aus dem nuorb-Journal)
set -euo pipefail
P=nuorb@${PHONE_HOST}; K=~/.ssh/id_ed25519_nuorb
ENV='export XDG_RUNTIME_DIR=/run/user/$(id -u) WAYLAND_DISPLAY=wayland-0;'
case "$1" in
  shot) ssh -o BatchMode=yes -i $K $P "$ENV /nix/store/rkc1f876ap766p918r1va5jps3f30c2j-grim-1.5.0/bin/grim -" > "$2" ;;
  key)  ssh -o BatchMode=yes -i $K $P "$ENV wtype -k $2" ;;
  type) ssh -o BatchMode=yes -i $K $P "$ENV wtype $(printf %q "$2")" ;;
  log)  ssh -o BatchMode=yes -i $K root@${NUORB_SERVER_IP} "journalctl -u nuorb-ui --since -15min --no-pager | grep 'client ${PHONE_HOST}' | cut -c 1-16,40-260 | tail -${2:-8}" ;;
esac
