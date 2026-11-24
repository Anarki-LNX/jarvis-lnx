#!/usr/bin/env bash
# XIAOMI REBIRTH / NuOrb: Grundausstattung fuer LXC 100 "nuorb" (Debian 13 trixie).
# Laeuft als root im Container, idempotent (mehrfach ausfuehrbar).
# Aufruf vom PC:  ssh root@$PROXMOX_HOST "pct exec 100 -- env APT_CACHE_HOST=<ip> bash -s" < scripts/nuorb-lxc-base.sh
# APT_CACHE_HOST optional (apt-cacher on :8080/apt); leer = Debian-Spiegel bleiben unverändert
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# 1) APT ueber den eigenen Cache & Carry (LXC 120) wie auf dem Proxmox-Host; Original bleibt als .bak
SRC=/etc/apt/sources.list.d/debian.sources
CACHE=http://${APT_CACHE_HOST:-}:8080/apt
if [ -n "${APT_CACHE_HOST:-}" ] && ! grep -q "$CACHE" "$SRC"; then
  cp -n "$SRC" "$SRC.bak"
  cat > "$SRC" <<EOF
Types: deb
URIs: $CACHE/debian
Suites: trixie trixie-updates
Components: main contrib non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: $CACHE/debian-security
Suites: trixie-security
Components: main contrib non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
fi

# 2) System aktualisieren
apt-get update
apt-get -y full-upgrade

# 3) Basiswerkzeuge (Agent-Framework, STT/TTS folgen erst nach der Analyse)
apt-get -y install --no-install-recommends \
  ca-certificates curl wget git jq sqlite3 htop tmux less nano \
  build-essential pkg-config \
  python3 python3-venv python3-pip python3-dev pipx \
  ffmpeg locales unattended-upgrades apt-listchanges openssh-server

# 4) Sprache: Deutsch + Englisch
sed -i 's/^# *\(de_DE.UTF-8 UTF-8\)/\1/; s/^# *\(en_US.UTF-8 UTF-8\)/\1/' /etc/locale.gen
locale-gen
update-locale LANG=de_DE.UTF-8

# 5) Automatische Sicherheitsupdates (Debian-Standard: nur Security)
cat > /etc/apt/apt.conf.d/20auto-upgrades <<EOF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

# 6) Eigener Dienstbenutzer fuer den Agenten, bewusst OHNE sudo
#    (der Agent darf keine Systemdateien aendern)
id nuorb >/dev/null 2>&1 || useradd -m -s /bin/bash -c "NuOrb Agent" nuorb

echo "== Fertig: $(. /etc/os-release; echo "$PRETTY_NAME"), Python $(python3 -V | cut -d' ' -f2), IP $(hostname -I)"
