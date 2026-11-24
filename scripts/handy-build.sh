#!/usr/bin/env bash
# Baut das courbet-Bringup-boot.img (ElXreno/nixos-courbet) in einem nixos/nix-Container.
# --network host, weil Docker auf diesem PC kein IPv4-Forwarding hat. Nichts wird am Host installiert.
set -euo pipefail
cd "$(dirname "$0")/.."
LOG=build/build-host.log
echo "== Start $(date -Is)" | tee "$LOG"
docker run --rm --network host \
  -v xiaomi-nix:/nix -v "$PWD/build:/work" -w /work/nixos-courbet \
  nixos/nix:latest sh -c '
    set -e
    nix --version
    git config --global --add safe.directory "*" 2>/dev/null || printf "[safe]\n\tdirectory = *\n" > /root/.gitconfig
    nix --extra-experimental-features "nix-command flakes" --option sandbox false \
        --option max-jobs auto --option cores 0 --option stalled-download-timeout 60 --option connect-timeout 20 --option download-attempts 10 \
        build .#boot-img --override-input linux path:/work/linux-c0f2fd4 --no-write-lock-file --out-link /tmp/result -L --show-trace
    cp -L /tmp/result /work/courbet-bringup-boot.img
    chown '"$(id -u):$(id -g)"' /work/courbet-bringup-boot.img
    readlink -f /tmp/result
  ' 2>&1 | tee -a "$LOG"
echo "== exit=${PIPESTATUS[0]} $(date -Is)" | tee -a "$LOG"
