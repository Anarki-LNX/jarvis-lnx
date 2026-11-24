#!/usr/bin/env bash
# Baut das JARVIS-Handy-System und spielt es per USB-Netz ein (nix copy + switch-to-configuration).
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/handy-nixos-build.sh toplevel
SYS=$(cat build/handy-nixos/out/toplevel.path)
echo "== deploy $SYS"
docker run --rm --network host -v xiaomi-nix:/nix -v "$HOME/.ssh/id_ed25519_jarvis:/key:ro" nixos/nix:latest sh -c "
  export NIX_SSHOPTS='-i /key -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR'
  nix --extra-experimental-features nix-command copy --no-check-sigs --to ssh://root@${HANDY_IP:-${PHONE_HOST:?set PHONE_HOST}} $SYS
" 2>&1 | grep -v IPv4
MODE=${MODE:-switch}   # MODE=test: nur aktivieren, Boot/Profil bleiben unverändert (Neustart = alter Stand)
if [ "$MODE" = test ]; then
  ./scripts/handy-ssh.sh "$SYS/bin/switch-to-configuration test" 2>&1 | tail -15
else
  ./scripts/handy-ssh.sh "nix-env -p /nix/var/nix/profiles/system --set $SYS && $SYS/bin/switch-to-configuration switch" 2>&1 | tail -15
fi
echo "== deploy fertig $(date -Is)"
