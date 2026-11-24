#!/usr/bin/env bash
: "${NUORB_SERVER_IP:?set NUORB_SERVER_IP (see config.env.example)}"
# Kopiert nuorb-admin nach nuorb, richtet venv/Helfer ein und startet den Dienst neu (vom PC aus).
set -euo pipefail
cd "$(dirname "$0")"
KEY=~/.ssh/id_ed25519_nuorb; H=root@${NUORB_SERVER_IP}
rsync -a --delete --exclude venv --exclude data --exclude keys --exclude screenshots --exclude '__pycache__' \
  --exclude deploy.sh -e "ssh -i $KEY" ./ $H:/home/nuorb/nuorb-admin/
ssh -i $KEY $H bash -s <<'REMOTE'
set -e
A=/home/nuorb/nuorb-admin
chown -R nuorb:nuorb $A
su - nuorb -c "test -x $A/venv/bin/python || python3 -m venv $A/venv; $A/venv/bin/pip -q install --disable-pip-version-check -r $A/requirements.txt"
# Handy-Schluessel (nur nuorb lesbar)
su - nuorb -c "mkdir -p -m700 $A/keys $A/data; test -f $A/keys/handy_ed25519 || ssh-keygen -q -t ed25519 -N '' -C nuorb-admin@nuorb -f $A/keys/handy_ed25519"
# root-Helfer
install -d -o nuorb -g nuorb -m 0750 /var/lib/nuorb-admin-ctl
install -m 0755 -o root -g root $A/ctl/nuorb-admin-ctl.sh /usr/local/sbin/nuorb-admin-ctl
install -m 0644 $A/ctl/nuorb-admin-ctl.path $A/ctl/nuorb-admin-ctl.service /etc/systemd/system/
install -m 0644 $A/nuorb-admin.service /etc/systemd/system/nuorb-admin.service
systemctl daemon-reload
systemctl enable -q --now nuorb-admin-ctl.path
systemctl enable -q nuorb-admin
systemctl restart nuorb-admin
sleep 2; systemctl is-active nuorb-admin
REMOTE
