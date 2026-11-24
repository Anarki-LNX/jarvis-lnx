#!/usr/bin/env bash
# RAM-Boot-Test des courbet-Bringup-Images. Schreibt NICHTS auf das Handy:
# `fastboot boot` laedt das Image nur in den RAM. Jede Phase wird einzeln aufgerufen.
#
#   ./scripts/handy-ramboot-test.sh check     # Image + Geraet pruefen (kein Neustart)
#   ./scripts/handy-ramboot-test.sh bootloader # adb reboot bootloader   (NEUSTART!)
#   ./scripts/handy-ramboot-test.sh ramboot    # fastboot boot <img>     (NEUSTART in RAM-Linux)
#   ./scripts/handy-ramboot-test.sh collect    # per USB-Netz/telnet Daten einsammeln (nur lesend)
#   ./scripts/handy-ramboot-test.sh reboot     # Bringup -> normaler Neustart in PixelOS
#
set -uo pipefail
cd "$(dirname "$0")/.."
IMG=build/courbet-bringup-boot.img
SERIAL="${SERIAL:?set SERIAL to your device serial (adb devices)}"
DEV_IP=172.16.42.1
OUT=${OUT:-diagnose/ramboot-$(date +%Y%m%d-%H%M%S)}

log() { printf '[%s] %s\n' "$(date +%T)" "$*"; }

tn() { # Befehle per telnet an das Bringup-System, Ausgabe auf stdout
    { sleep 2; printf '%s\n' "$@"; printf 'echo __ENDE__\n'; sleep "${TN_WAIT:-8}"; } |
        telnet "$DEV_IP" 23 2>/dev/null | tr -d '\r'
}

case "${1:-}" in
check)
    ls -l "$IMG" && sha256sum "$IMG"
    unpack_bootimg --boot_img "$IMG" --format=info 2>/dev/null | head -20 || unpack_bootimg --boot_img "$IMG" | head -20
    adb devices -l
    ;;
bootloader)
    adb -s "$SERIAL" reboot bootloader
    log "warte auf fastboot ..."
    for _ in $(seq 60); do fastboot devices | grep -q "$SERIAL" && break; sleep 1; done
    fastboot -s "$SERIAL" getvar product 2>&1 | grep -q 'product: courbet' \
        && log "fastboot: courbet erkannt" || { log "FEHLER: kein courbet in fastboot"; exit 1; }
    ;;
ramboot)
    fastboot -s "$SERIAL" getvar product 2>&1 | grep -q 'product: courbet' || { log "kein courbet in fastboot"; exit 1; }
    log "fastboot boot $IMG  (nur RAM, kein Flash)"
    fastboot -s "$SERIAL" boot "$IMG"
    log "warte bis zu 120 s auf USB-Geraet 18d1:d001 / $DEV_IP ..."
    for i in $(seq 120); do
        if lsusb | grep -qi '18d1:d001'; then log "USB-Gadget da nach ${i}s"; break; fi; sleep 1
    done
    lsusb | grep -i 18d1 || true
    ip -br addr | grep -E '172\.16\.42' || log "Host hat (noch) keine 172.16.42.x-Adresse (NetworkManager/DHCP pruefen)"
    ;;
collect)
    mkdir -p "$OUT"
    log "Ziel: $OUT"
    ping -c 3 -W 2 "$DEV_IP" >"$OUT/ping.txt" 2>&1; cat "$OUT/ping.txt" | tail -2
    lsusb >"$OUT/host-lsusb.txt"; ip -br addr >"$OUT/host-ip.txt"
    TN_WAIT=10 tn 'uname -a' 'cat /proc/cmdline' 'uptime' >"$OUT/basis.txt"
    TN_WAIT=15 tn 'dmesg' >"$OUT/dmesg.txt"
    TN_WAIT=10 tn 'lsmod' 'cat /proc/modules | wc -l' >"$OUT/lsmod.txt"
    TN_WAIT=10 tn 'cat /proc/bus/input/devices' 'ls -l /sys/class/input/' >"$OUT/input.txt"
    TN_WAIT=10 tn 'cat /proc/asound/cards' 'ls -l /sys/class/sound/ /dev/snd 2>&1' >"$OUT/sound.txt"
    TN_WAIT=10 tn 'ls -l /sys/class/net/' 'ip -br link' 'ls /sys/class/ieee80211/ 2>&1' >"$OUT/net.txt"
    TN_WAIT=10 tn 'for p in /sys/class/power_supply/*; do echo "== $p"; cat $p/uevent; done' >"$OUT/power.txt"
    TN_WAIT=10 tn 'ls -l /sys/class/drm/ /sys/class/backlight/ /dev/dri /dev/fb* 2>&1' \
        'for c in /sys/class/drm/card*-*; do echo "$c $(cat $c/status 2>/dev/null)"; done' \
        'cat /sys/class/graphics/fb0/virtual_size 2>&1' >"$OUT/display.txt"
    TN_WAIT=10 tn 'for r in /sys/class/remoteproc/*; do echo "$r $(cat $r/name) $(cat $r/state)"; done' \
        'ls -l /lib/firmware/qcom/sm7150/xiaomi/courbet/' 'mount' >"$OUT/remoteproc.txt"
    TN_WAIT=10 tn 'cat /proc/partitions' 'ls /sys/class/udc' 'free' 'cat /sys/class/thermal/thermal_zone*/temp' >"$OUT/system.txt"
    log "Kurzauswertung (grep dmesg):"
    grep -iE 'goodix|gt9897|touch|tfa98|wcd93|snd|sound|asoc|ath10k|wlan|qcom_qg|smbx|smb5|battery|charger|panel|dsi|msm_dpu|drm|adreno|remoteproc|error|fail' \
        "$OUT/dmesg.txt" >"$OUT/dmesg-auszug.txt"
    wc -l "$OUT"/*.txt
    ;;
reboot)
    log "Bringup -> reboot -f (Handy startet normal PixelOS, nichts wurde geflasht)"
    TN_WAIT=3 tn 'sync' 'reboot -f' || true
    ;;
*) sed -n '2,12p' "$0"; exit 1 ;;
esac
