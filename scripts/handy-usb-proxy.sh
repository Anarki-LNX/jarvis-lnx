#!/bin/sh
: "${JARVIS_HOST:?set JARVIS_HOST (see config.env.example)}"
# Stellt dem Handy die JARVIS-UI (${JARVIS_HOST}:8443) über das USB-Kabel bereit, solange kein WLAN da ist.
# PC baut einen SSH-Reverse-Tunnel zum Handy auf (ausgehend, Host-Firewall bleibt unverändert):
#   Handy 127.0.0.1:8443  ->  (Tunnel)  ->  ${JARVIS_HOST}:8443
# Auf dem Handy leitet nftables (usb-fallback.nix) ${JARVIS_HOST}:8443 auf 127.0.0.1:8443 um.
while true; do
  if ip -4 addr show | grep -q 'inet 172.16.42.2/'; then
    # Uhrzeit des Handys stellen (keine RTC/NTP ohne Internet; TLS braucht die richtige Zeit)
    ssh -i ~/.ssh/id_ed25519_jarvis -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR \
      -o ConnectTimeout=5 root@172.16.42.1 "date -s @$(date +%s) >/dev/null" 2>/dev/null
    ssh -N -i ~/.ssh/id_ed25519_jarvis -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR \
      -o ConnectTimeout=5 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
      -R 127.0.0.1:8443:${JARVIS_HOST}:8443 root@172.16.42.1
  fi
  sleep 3
done
