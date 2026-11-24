#!/bin/sh
# SSH aufs JARVIS-Handy über USB-Netz
exec ssh -i ~/.ssh/id_ed25519_jarvis -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=10 "${HANDY_USER:-root}@${HANDY_IP:-${PHONE_HOST:?set PHONE_HOST}}" "$@"
