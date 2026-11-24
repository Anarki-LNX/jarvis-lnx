#!/usr/bin/env bash
: "${JARVIS_HOST:?set JARVIS_HOST (see config.env.example)}"
# Installiert den MCP-Server "handy" (JARVIS-Sprachsteuerung) auf jarvis und traegt ihn in Hermes ein.
# Aufruf vom PC:  scripts/steuerung-install-jarvis.sh <Handy-WLAN-IP>
# Wiederholbar. Vorher wird config.yaml gesichert (config.yaml.vor-steuerung.<Zeit>).
set -euo pipefail
HANDY_IP=${1:?Handy-IP angeben}
cd "$(dirname "$0")"
J="ssh -i $HOME/.ssh/id_ed25519_jarvis -o BatchMode=yes root@${JARVIS_HOST}"
D=/home/jarvis/.hermes/steuerung
$J "install -d -o jarvis -g jarvis -m 700 $D"
for f in steuerung-handy-mcp.py:handy_mcp.py steuerung-hermes-config.py:hermes_config.py; do
  $J "cat > $D/${f#*:} && chown jarvis:jarvis $D/${f#*:} && chmod 700 $D/${f#*:}" < "${f%%:*}"
done
$J "su jarvis -s /bin/sh -c 'python3 $D/hermes_config.py $HANDY_IP'"
echo "== fertig; laut Doku uebernimmt das Gateway neue mcp_servers-Eintraege innerhalb ~1 min"
