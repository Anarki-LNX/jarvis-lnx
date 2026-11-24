#!/usr/bin/env bash
: "${NUORB_SERVER_IP:?set NUORB_SERVER_IP (see config.env.example)}"
# Installiert den MCP-Server "handy" (NuOrb-Sprachsteuerung) auf nuorb und traegt ihn in Hermes ein.
# Aufruf vom PC:  scripts/steuerung-install-nuorb.sh <Handy-WLAN-IP>
# Wiederholbar. Vorher wird config.yaml gesichert (config.yaml.vor-steuerung.<Zeit>).
set -euo pipefail
HANDY_IP=${1:?Handy-IP angeben}
cd "$(dirname "$0")"
J="ssh -i $HOME/.ssh/id_ed25519_nuorb -o BatchMode=yes root@${NUORB_SERVER_IP}"
D=/home/nuorb/.hermes/steuerung
$J "install -d -o nuorb -g nuorb -m 700 $D"
for f in steuerung-handy-mcp.py:handy_mcp.py steuerung-hermes-config.py:hermes_config.py; do
  $J "cat > $D/${f#*:} && chown nuorb:nuorb $D/${f#*:} && chmod 700 $D/${f#*:}" < "${f%%:*}"
done
$J "su nuorb -s /bin/sh -c 'python3 $D/hermes_config.py $HANDY_IP'"
echo "== fertig; laut Doku uebernimmt das Gateway neue mcp_servers-Eintraege innerhalb ~1 min"
