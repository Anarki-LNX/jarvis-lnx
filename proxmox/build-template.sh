#!/usr/bin/env bash
# Builds the ready made Proxmox LXC template nuorb-lxc-<version>-amd64.tar.zst.
#
#   sudo proxmox/build-template.sh <version> [output folder, default: dist]
#
# Used by .github/workflows/lxc-template.yml on every tag v*. Needs root,
# debootstrap, debian-archive-keyring and zstd (Debian or Ubuntu).
#
# The template is Debian 12 (bookworm, amd64) with Docker Engine, Compose and
# the NuOrb tools from proxmox/ct-setup.sh. The NuOrb image itself is not in
# the template: it is about 3.5 GB unpacked and changes with every release.
# A first boot service pulls it and runs install.sh as soon as the container
# has network, so the template stays small (about 150 MB) and the container
# always starts with the newest NuOrb.
#
# Output: the template, a .sha256 file and a list of the Debian packages with
# their versions (sources: https://snapshot.debian.org).
set -Eeuo pipefail

VERSION="${1:-}"
OUT="${2:-dist}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.+~-][0-9A-Za-z.]+)?$ ]] || { echo "usage: build-template.sh <version, e.g. 0.6.6> [output folder]" >&2; exit 2; }
[ "$(id -u)" -eq 0 ] || { echo "build-template.sh: run as root" >&2; exit 1; }
for c in debootstrap zstd chroot mount; do command -v "$c" >/dev/null || { echo "build-template.sh: $c is missing" >&2; exit 1; }; done

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SUITE=bookworm
MIRROR="${DEBIAN_MIRROR:-http://deb.debian.org/debian}"
KEYRING=/usr/share/keyrings/debian-archive-keyring.gpg
NAME="nuorb-lxc-${VERSION}-amd64"
mkdir -p "$OUT"
OUT=$(cd -- "$OUT" && pwd)
WORK=$(mktemp -d -p "${BUILD_DIR:-$OUT}" .build.XXXXXX)
ROOT="$WORK/rootfs"

say() { printf '\n== %s\n' "$*"; }
umount_all() {
  local m
  for m in dev/pts dev proc sys; do mountpoint -q "$ROOT/$m" 2>/dev/null && umount -l "$ROOT/$m"; done
  return 0
}
cleanup() { umount_all; rm -rf "$WORK"; }
trap cleanup EXIT

# ------------------------------------------------------------------ base system
say "debootstrap Debian 12 ($SUITE, amd64)"
PKGS=systemd,systemd-sysv,dbus,ifupdown,isc-dhcp-client,iproute2,iputils-ping,ca-certificates,curl,gnupg,locales,tzdata,less,nano,procps,cron,logrotate
KEYOPT=()
[ -r "$KEYRING" ] && KEYOPT=(--keyring "$KEYRING")
debootstrap --arch=amd64 --variant=minbase "${KEYOPT[@]}" --include="$PKGS" "$SUITE" "$ROOT" "$MIRROR"

cat > "$ROOT/etc/apt/sources.list" <<EOF
deb http://deb.debian.org/debian ${SUITE} main
deb http://deb.debian.org/debian ${SUITE}-updates main
deb http://security.debian.org/debian-security ${SUITE}-security main
EOF
echo nuorb > "$ROOT/etc/hostname"
printf 'C.UTF-8 UTF-8\nen_US.UTF-8 UTF-8\nde_DE.UTF-8 UTF-8\n' > "$ROOT/etc/locale.gen"
echo 'LANG=C.UTF-8' > "$ROOT/etc/default/locale"
cp /etc/resolv.conf "$ROOT/etc/resolv.conf" 2>/dev/null || echo 'nameserver 1.1.1.1' > "$ROOT/etc/resolv.conf"
printf '#!/bin/sh\nexit 101\n' > "$ROOT/usr/sbin/policy-rc.d"; chmod 0755 "$ROOT/usr/sbin/policy-rc.d"

mount --bind /dev "$ROOT/dev"
mount --bind /dev/pts "$ROOT/dev/pts"
mount -t proc proc "$ROOT/proc"
mount -t sysfs sys "$ROOT/sys"

# ------------------------------------------------------------------ NuOrb tools (same script as nuorb-lxc.sh uses)
say "ct-setup.sh --template"
chroot "$ROOT" /usr/sbin/locale-gen >/dev/null
install -m 0755 "$HERE/ct-setup.sh" "$ROOT/root/ct-setup.sh"
chroot "$ROOT" /usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root \
  NUORB_REF="${NUORB_REF:-main}" bash /root/ct-setup.sh --template
rm -f "$ROOT/root/ct-setup.sh"

mkdir -p "$ROOT/etc/nuorb"
printf 'NUORB_TEMPLATE_VERSION=%s\nNUORB_TEMPLATE_BUILT=%s\n' "$VERSION" "$(date -u +%FT%TZ)" > "$ROOT/etc/nuorb/template"
# shellcheck disable=SC2016  # dpkg-query format, not shell
chroot "$ROOT" dpkg-query -W -f '${Package} ${Version}\n' > "$OUT/$NAME.packages.txt"

# ------------------------------------------------------------------ checks
say "checking the root file system"
fail=0
for f in sbin/init usr/bin/dockerd usr/bin/containerd usr/libexec/docker/cli-plugins/docker-compose \
         usr/local/bin/update usr/local/sbin/nuorb-firstboot etc/profile.d/nuorb.sh \
         etc/systemd/system/multi-user.target.wants/nuorb-firstboot.service \
         etc/systemd/system/multi-user.target.wants/docker.service; do
  if [ -e "$ROOT/$f" ] || [ -L "$ROOT/$f" ]; then echo "  ok $f"; else echo "  MISSING $f"; fail=1; fi
done
chroot "$ROOT" docker --version
chroot "$ROOT" docker compose version
[ "$fail" = 0 ] || { echo "build-template.sh: the template is incomplete" >&2; exit 1; }

# ------------------------------------------------------------------ clean up (Proxmox writes these at the first start)
umount_all
rm -f "$ROOT/usr/sbin/policy-rc.d"
: > "$ROOT/etc/resolv.conf"
: > "$ROOT/etc/machine-id"
rm -f "$ROOT/var/lib/dbus/machine-id"
rm -f "$ROOT"/etc/ssh/ssh_host_* "$ROOT/root/.bash_history"
rm -rf "$ROOT"/var/lib/apt/lists/* "$ROOT"/var/cache/apt/*.bin "$ROOT"/var/cache/debconf/*-old "$ROOT"/tmp/* "$ROOT"/var/tmp/*
find "$ROOT/var/log" -type f -exec truncate -s 0 {} +

# ------------------------------------------------------------------ pack
say "packing $NAME.tar.zst"
tar --numeric-owner --xattrs --xattrs-include='*' -C "$ROOT" -cf - . | zstd -q -19 -T0 -o "$OUT/$NAME.tar.zst" -f
(cd "$OUT" && sha256sum "$NAME.tar.zst" > "$NAME.tar.zst.sha256")
size=$(stat -c %s "$OUT/$NAME.tar.zst")
echo "  $NAME.tar.zst: $((size / 1048576)) MB"
[ "$size" -lt 2000000000 ] || { echo "build-template.sh: larger than the 2 GB limit for release assets" >&2; exit 1; }
cat "$OUT/$NAME.tar.zst.sha256"
