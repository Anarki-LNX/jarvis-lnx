#!/usr/bin/env bash
: "${NUORB_SERVER_IP:?set NUORB_SERVER_IP (see config.env.example)}"
# Kopiert nuorb-ui nach nuorb und startet den Dienst neu (vom PC aus).
set -euo pipefail
cd "$(dirname "$0")"
KEY=~/.ssh/id_ed25519_nuorb; H=root@${NUORB_SERVER_IP}
rsync -a --delete --exclude venv --exclude certs --exclude screenshots --exclude '__pycache__' \
  -e "ssh -i $KEY" ./ $H:/home/nuorb/nuorb-ui/
ssh -i $KEY $H 'chown -R nuorb:nuorb /home/nuorb/nuorb-ui && install -m644 /home/nuorb/nuorb-ui/nuorb-ui.service /etc/systemd/system/nuorb-ui.service && systemctl daemon-reload && systemctl enable -q nuorb-ui && systemctl restart nuorb-ui && sleep 2 && systemctl is-active nuorb-ui'
