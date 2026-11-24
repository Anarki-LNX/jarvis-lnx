#!/usr/bin/env bash
: "${JARVIS_HOST:?set JARVIS_HOST (see config.env.example)}"
# Kopiert jarvis-ui nach jarvis und startet den Dienst neu (vom PC aus).
set -euo pipefail
cd "$(dirname "$0")"
KEY=~/.ssh/id_ed25519_jarvis; H=root@${JARVIS_HOST}
rsync -a --delete --exclude venv --exclude certs --exclude screenshots --exclude '__pycache__' \
  -e "ssh -i $KEY" ./ $H:/home/jarvis/jarvis-ui/
ssh -i $KEY $H 'chown -R jarvis:jarvis /home/jarvis/jarvis-ui && install -m644 /home/jarvis/jarvis-ui/jarvis-ui.service /etc/systemd/system/jarvis-ui.service && systemctl daemon-reload && systemctl enable -q jarvis-ui && systemctl restart jarvis-ui && sleep 2 && systemctl is-active jarvis-ui'
