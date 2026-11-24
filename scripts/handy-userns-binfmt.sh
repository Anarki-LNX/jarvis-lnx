#!/bin/sh
# Laeuft IM Container (privileged). Erzeugt eigenen User-Namespace mit eigener binfmt_misc-Instanz
# (Linux >= 6.7) und registriert qemu-aarch64 nur dort. Der Host bleibt unveraendert.
set -e
Q=$(readlink -f /nix/var/qemu-user-static)/bin/qemu-aarch64
exec unshare --user --map-users=0:0:65536 --map-groups=0:0:65536 --setuid 0 --setgid 0 --mount --fork sh -c '
  set -e
  mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
  printf "%s" ":qemu-aarch64:M::\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\xb7\x00:\xff\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff:'"$Q"':FP" > /proc/sys/fs/binfmt_misc/register
  exec "$@"
' sh "$@"
