#!/bin/bash
# Root-Helfer der NuOrb-Verwaltung: startet NUR die vier freigegebenen Dienste neu.
# Ausgeloest von nuorb-admin-ctl.path, wenn der Dienst (Benutzer nuorb) $D/request schreibt.
# Sicherheit: Anfrage wird nur per Muster gelesen (kein eval), Symlinks werden abgelehnt,
# das Ergebnis wird per mktemp + mv geschrieben (folgt keinen Symlinks).
set -u
D=/var/lib/nuorb-admin-ctl
REQ="$D/request"
[ -e "$REQ" ] || exit 0
if [ -L "$REQ" ] || [ ! -f "$REQ" ]; then rm -f -- "$REQ"; exit 0; fi
LINE=$(head -c 120 -- "$REQ" | head -n1 | tr -cd 'a-z0-9 \n')
rm -f -- "$REQ"
read -r ACTION NAME ID <<<"$LINE"
case "$NAME" in
  hermes) UNIT=hermes-gateway-c51abf38.service ;;
  stt)    UNIT=nuorb-stt-router.service ;;
  ui)     UNIT=nuorb-ui.service ;;
  admin)  UNIT=nuorb-admin.service ;;
  *)      UNIT="" ;;
esac
OK=false; MSG="abgelehnt"
if [ "$ACTION" = "restart" ] && [ -n "$UNIT" ]; then
  if timeout 90 systemctl restart "$UNIT"; then OK=true; MSG="neu gestartet"; else MSG="Neustart fehlgeschlagen"; fi
fi
logger -t nuorb-admin-ctl "Anfrage '$ACTION $NAME' -> $MSG"
TMP=$(mktemp "$D/.result.XXXXXX")
printf '{"id":"%s","action":"%s","unit":"%s","ok":%s,"message":"%s","time":"%s"}\n' \
  "${ID:0:16}" "${ACTION:0:16}" "$UNIT" "$OK" "$MSG" "$(date -Iseconds)" > "$TMP"
chmod 644 "$TMP"
mv -f -- "$TMP" "$D/result.json"
