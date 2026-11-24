#!/usr/bin/env bash
# Baut das JARVIS-Handy-NixOS (build/handy-nixos) im Container.
# aarch64-Schritte laufen ueber qemu-user, registriert NUR in einem eigenen User-Namespace
# (scripts/handy-userns-binfmt.sh) – am Host wird nichts registriert/installiert.
# Aufruf: scripts/handy-nixos-build.sh <attr...>   z.B. toplevel boot-img rootfs   (oder: eval)
set -euo pipefail
cd "$(dirname "$0")/.."
LOG=build/handy-nixos-build.log
echo "== Start $(date -Is) $*" | tee -a "$LOG"
docker run --rm --privileged --network host \
  -v xiaomi-nix:/nix -v "$PWD/build:/work" -v "$PWD/scripts:/scripts:ro" -w /work/handy-nixos \
  -e ATTRS="$*" -e HUID="$(id -u):$(id -g)" \
  nixos/nix:latest sh -c '
    set -e
    git config --global --add safe.directory "*"
    export PATH=$(readlink -f /nix/var/util-linux-bin)/bin:$PATH
    /scripts/handy-userns-binfmt.sh /scripts/handy-nixos-build-inner.sh
  ' 2>&1 | grep --line-buffered -v "^WARNING: IPv4" | tee -a "$LOG"
echo "== exit=${PIPESTATUS[0]} $(date -Is)" | tee -a "$LOG"
