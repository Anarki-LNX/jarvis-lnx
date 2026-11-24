#!/usr/bin/env bash
: "${JARVIS_HOST:?set JARVIS_HOST (see config.env.example)}"
# Kopiert jarvis-admin nach jarvis, richtet venv/Helfer ein und startet den Dienst neu (vom PC aus).
set -euo pipefail
cd "$(dirname "$0")"
KEY=~/.ssh/id_ed25519_jarvis; H=root@${JARVIS_HOST}
rsync -a --delete --exclude venv --exclude data --exclude keys --exclude screenshots --exclude '__pycache__' \
  --exclude deploy.sh -e "ssh -i $KEY" ./ $H:/home/jarvis/jarvis-admin/
ssh -i $KEY $H bash -s <<'REMOTE'
set -e
A=/home/jarvis/jarvis-admin
chown -R jarvis:jarvis $A
su - jarvis -c "test -x $A/venv/bin/python || python3 -m venv $A/venv; $A/venv/bin/pip -q install --disable-pip-version-check -r $A/requirements.txt"
# Handy-Schluessel (nur jarvis lesbar)
su - jarvis -c "mkdir -p -m700 $A/keys $A/data; test -f $A/keys/handy_ed25519 || ssh-keygen -q -t ed25519 -N '' -C jarvis-admin@jarvis -f $A/keys/handy_ed25519"
# root-Helfer
install -d -o jarvis -g jarvis -m 0750 /var/lib/jarvis-admin-ctl
install -m 0755 -o root -g root $A/ctl/jarvis-admin-ctl.sh /usr/local/sbin/jarvis-admin-ctl
install -m 0644 $A/ctl/jarvis-admin-ctl.path $A/ctl/jarvis-admin-ctl.service /etc/systemd/system/
install -m 0644 $A/jarvis-admin.service /etc/systemd/system/jarvis-admin.service
systemctl daemon-reload
systemctl enable -q --now jarvis-admin-ctl.path
systemctl enable -q jarvis-admin
systemctl restart jarvis-admin
sleep 2; systemctl is-active jarvis-admin
REMOTE
