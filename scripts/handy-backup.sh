#!/usr/bin/env bash
# ENTWURF – noch nicht ausgefuehrt. Sichert kritische Partitionen NUR LESEND,
# waehrend das courbet-Bringup-Linux per `fastboot boot` im RAM laeuft
# (USB-Netz 172.16.42.1, telnetd + busybox nc auf dem Handy).
#
# Ablauf je Partition: Handy: dd if=/dev/<blk> | nc -l -p PORT   ->   PC: nc 172.16.42.1 PORT > datei
# Danach sha256 auf beiden Seiten vergleichen.
set -uo pipefail
cd "$(dirname "$0")/.."
DEV_IP=172.16.42.1
PORT=5555
OUT=${OUT:-diagnose/backup-courbet-$(date +%Y%m%d-%H%M%S)}

# Pflicht (Funk/IMEI/Kalibrierung, Boot-Kette des aktuellen Systems)
PARTS=${PARTS:-"persist persistbak modemst1 modemst2 fsg fsc dtbo vbmeta vbmeta_system vbmeta_vendor boot recovery
devinfo keystore secdata frp misc bluetooth dsp modem logo"}

tn() { { sleep 2; printf '%s\n' "$@"; sleep "${TN_WAIT:-4}"; } | telnet "$DEV_IP" 23 2>/dev/null | tr -d '\r'; }

# Partition per PARTNAME im Bringup finden (gleiche Logik wie bringup/init)
PARTFN='part(){ for u in /sys/class/block/*/uevent; do grep -qx "PARTNAME=$1" "$u" && { basename "$(dirname "$u")"; return; }; done; }'

mkdir -p "$OUT"
tn "$PARTFN" 'for p in '"$(echo $PARTS)"'; do b=$(part $p); echo "MAP $p $b $(cat /sys/class/block/$b/size 2>/dev/null)"; done' \
    | grep '^MAP' | tee "$OUT/partmap.txt"

while read -r _ name blk sectors; do
    [ -n "$blk" ] || { echo "!! $name nicht gefunden"; continue; }
    echo "== $name (/dev/$blk, $((sectors * 512)) Bytes)"
    tn "setsid sh -c 'dd if=/dev/$blk bs=1M 2>/dev/null | nc -l -p $PORT' </dev/null >/dev/null 2>&1 &" >/dev/null
    sleep 1
    nc -w 30 "$DEV_IP" "$PORT" </dev/null >"$OUT/$name.img"
    TN_WAIT=$(( 3 + sectors / 400000 )) tn "sha256sum /dev/$blk" | grep -E '^[0-9a-f]{64} ' | awk -v n="$name" '{print $1"  "n".img"}' >>"$OUT/SHA256SUMS.device"
    ls -l "$OUT/$name.img"
done <"$OUT/partmap.txt"

(cd "$OUT" && sha256sum -- *.img >SHA256SUMS.host && diff <(sort -k2 SHA256SUMS.device) <(sort -k2 SHA256SUMS.host) && echo "ALLE PRUEFSUMMEN GLEICH")
