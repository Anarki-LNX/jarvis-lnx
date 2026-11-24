#!/bin/sh
# Innerer Teil von handy-nixos-build.sh (laeuft im Container, im eigenen User-Namespace mit qemu-binfmt).
set -e
nixc() {
  nix --extra-experimental-features "nix-command flakes" --option sandbox false \
    --option extra-platforms aarch64-linux --option max-jobs auto --option cores 0 \
    --option stalled-download-timeout 60 --option connect-timeout 20 --option download-attempts 10 "$@"
}
cd /work/handy-nixos
if [ "$ATTRS" = eval ]; then
  nixc eval --raw .#packages.x86_64-linux.toplevel.drvPath --show-trace; echo
  chown "$HUID" flake.lock 2>/dev/null || true
  exit 0
fi
mkdir -p out
for a in $ATTRS; do
  nixc build ".#$a" --out-link "/tmp/res-$a" -L --show-trace
  p=$(readlink -f "/tmp/res-$a")
  rm -rf "out/$a"
  if [ -f "$p" ]; then cp "$p" "out/$a"; else echo "$p" > "out/$a.path"; fi
  echo "BUILT $a $p"
done
chown -R "$HUID" out flake.lock 2>/dev/null || true
