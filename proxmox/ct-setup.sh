#!/usr/bin/env bash
# Prepares Debian 12 for NuOrb inside a Proxmox LXC container.
#
# Used in two places, so both ways end with the same system:
#   * proxmox/nuorb-lxc.sh runs it in a freshly created container (as root).
#   * proxmox/build-template.sh runs it with --template in a chroot to build the
#     ready made template nuorb-lxc-<version>-amd64.tar.zst.
#
# It installs Docker Engine and Compose from download.docker.com, the command
# `update` (pulls the newest NuOrb image, keeps settings and data) and a short
# notice with the addresses at login. With --template it also installs a first
# boot service that runs the NuOrb installer once the container has network.
#
# NuOrb itself is installed by install.sh from the repository root, with the
# same questions, ports and volumes as a plain Docker installation.
set -Eeuo pipefail

export DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8
unset LANGUAGE

TEMPLATE=0
case "${1:-}" in
  --template) TEMPLATE=1 ;;
  "") ;;
  *) echo "usage: ct-setup.sh [--template]" >&2; exit 2 ;;
esac

[ "$(id -u)" -eq 0 ] || { echo "ct-setup.sh: run as root" >&2; exit 1; }
# shellcheck disable=SC1091
. /etc/os-release
[ "${ID:-}" = debian ] || { echo "ct-setup.sh: Debian is needed, found ${ID:-unknown}" >&2; exit 1; }
CODENAME="${VERSION_CODENAME:-bookworm}"
ARCH="$(dpkg --print-architecture)"

say() { printf ':: %s\n' "$*"; }

# ------------------------------------------------------------------ Debian
say "updating Debian ${VERSION_ID:-} (${CODENAME})"
apt-get update -qq
apt-get -y -qq -o Dpkg::Options::=--force-confold dist-upgrade >/dev/null
apt-get install -y -qq --no-install-recommends ca-certificates curl gnupg iproute2 >/dev/null

# ------------------------------------------------------------------ Docker
say "installing Docker Engine and Compose (download.docker.com)"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL --retry 3 https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian %s stable\n' \
  "$ARCH" "$CODENAME" > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin >/dev/null
# small logs, the NuOrb compose file limits its own logs as well
if [ ! -s /etc/docker/daemon.json ]; then
  mkdir -p /etc/docker
  printf '{\n  "log-driver": "json-file",\n  "log-opts": { "max-size": "10m", "max-file": "3" }\n}\n' > /etc/docker/daemon.json
fi
if [ "$TEMPLATE" = 1 ]; then
  systemctl enable docker.service containerd.service >/dev/null 2>&1 || true
else
  systemctl enable --now docker >/dev/null 2>&1 || true
  if ! docker info >/dev/null 2>&1; then
    echo "Docker does not start in this container." >&2
    echo "On the Proxmox host: pct set <ID> -features nesting=1,keyctl=1 and restart the container." >&2
    exit 1
  fi
fi

# ------------------------------------------------------------------ update command
say "installing the command: update"
cat > /usr/local/bin/update <<'EOF'
#!/usr/bin/env bash
# NuOrb update inside the Proxmox container: updates Debian and Docker, pulls
# the newest NuOrb image and restarts it. Settings and data stay.
set -Eeuo pipefail
[ "$(id -u)" -eq 0 ] || { echo "update: run as root" >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8 HOME=/root
REF="${NUORB_REF:-main}"
echo ":: updating Debian and Docker"
apt-get update -qq
apt-get -y -qq -o Dpkg::Options::=--force-confold dist-upgrade >/dev/null
echo ":: updating NuOrb"
curl -fsSL --retry 3 "https://raw.githubusercontent.com/Anarki-LNX/nuorb/${REF}/install.sh" \
  | bash -s -- --yes --no-firewall "$@"
docker image prune -f >/dev/null 2>&1 || true
EOF
chmod 0755 /usr/local/bin/update

# ------------------------------------------------------------------ login notice
cat > /etc/profile.d/nuorb.sh <<'EOF'
# NuOrb: addresses and setup code at login (written by proxmox/ct-setup.sh)
nuorb_notice() {
  local ip env=/root/nuorb/.env ui=8443 admin=8444 code=""
  ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  if [ -r "$env" ]; then
    ui=$(sed -n 's/^JARVIS_UI_PORT_PUBLIC=//p' "$env" | tail -1); ui=${ui:-8443}
    admin=$(sed -n 's/^JARVIS_ADMIN_PORT_PUBLIC=//p' "$env" | tail -1); admin=${admin:-8444}
  fi
  echo
  if [ -f /var/lib/nuorb/firstboot-running ]; then
    echo "  NuOrb is being installed. Progress: tail -f /var/log/nuorb-firstboot.log"
  elif [ -f /var/lib/nuorb/firstboot-failed ]; then
    echo "  NuOrb installation failed. Details: /var/log/nuorb-firstboot.log, try again: update"
  fi
  echo "  NuOrb admin panel  https://${ip:-<IP>}:${admin}"
  echo "  NuOrb app          https://${ip:-<IP>}:${ui}"
  code=$(docker exec nuorb cat /opt/data/jarvis/admin/setup-code.txt 2>/dev/null || true)
  [ -n "$code" ] && echo "  Setup code         ${code}"
  echo "  Update             update"
  echo
}
[ "$(id -u)" -eq 0 ] && case "$-" in *i*) nuorb_notice ;; esac
unset -f nuorb_notice
EOF

# ------------------------------------------------------------------ first boot (template only)
if [ "$TEMPLATE" = 1 ]; then
  say "installing the first boot service"
  mkdir -p /var/lib/nuorb
  cat > /usr/local/sbin/nuorb-firstboot <<'EOF'
#!/usr/bin/env bash
# Runs once at the first start of a container made from the NuOrb template:
# waits for network and Docker, then installs NuOrb with install.sh.
set -uo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8 HOME=/root
REF="${NUORB_REF:-main}"
STATE=/var/lib/nuorb
mkdir -p "$STATE"; rm -f "$STATE/firstboot-failed"; touch "$STATE/firstboot-running"
failed() { echo "NuOrb first boot: $*"; rm -f "$STATE/firstboot-running"; touch "$STATE/firstboot-failed"; exit 1; }
for _ in $(seq 1 150); do getent hosts raw.githubusercontent.com >/dev/null 2>&1 && break; sleep 2; done
getent hosts raw.githubusercontent.com >/dev/null 2>&1 || failed "no network or DNS after 5 minutes"
for _ in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 2; done
docker info >/dev/null 2>&1 || failed "Docker does not run. On the Proxmox host: pct set <ID> -features nesting=1,keyctl=1, then restart the container."
LANG_ARG=()
[ -r /etc/nuorb/lang ] && LANG_ARG=(--lang "$(tr -cd 'a-z' < /etc/nuorb/lang)")
curl -fsSL --retry 5 "https://raw.githubusercontent.com/Anarki-LNX/nuorb/${REF}/install.sh" -o /root/nuorb-install.sh \
  || failed "could not download install.sh"
bash /root/nuorb-install.sh --yes --no-firewall --llm none "${LANG_ARG[@]}" || failed "install.sh failed"
rm -f /root/nuorb-install.sh "$STATE/firstboot-running"
touch "$STATE/firstboot-done"
EOF
  chmod 0755 /usr/local/sbin/nuorb-firstboot
  cat > /etc/systemd/system/nuorb-firstboot.service <<'EOF'
[Unit]
Description=NuOrb: install on first start
Wants=network-online.target docker.service
After=network-online.target docker.service
ConditionPathExists=!/var/lib/nuorb/firstboot-done

[Service]
# simple, not oneshot: the image download takes minutes and must not hold up the boot
Type=simple
ExecStart=/usr/local/sbin/nuorb-firstboot
StandardOutput=append:/var/log/nuorb-firstboot.log
StandardError=append:/var/log/nuorb-firstboot.log
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF
  systemctl enable nuorb-firstboot.service >/dev/null 2>&1 \
    || ln -sf /etc/systemd/system/nuorb-firstboot.service /etc/systemd/system/multi-user.target.wants/nuorb-firstboot.service
fi

apt-get clean
rm -rf /var/lib/apt/lists/*
say "done"
