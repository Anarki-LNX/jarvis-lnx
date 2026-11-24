#!/usr/bin/env bash
# XIAOMI REBIRTH – Phase 1: rein lesende Diagnose per ADB.
# Verändert nichts am Gerät: nur getprop, cat, ls, df, dumpsys, pm list, wm size/density (ohne Argumente).
# Aufruf: scripts/phase1-diagnose.sh [SERIAL]
set -u
SERIAL="${1:?usage: phase1-diagnose.sh <adb-serial>}"
OUT="$(dirname "$0")/../diagnose/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
A=(adb -s "$SERIAL")

run() { # run <datei> <befehl...>
  local f="$1"; shift
  { echo "\$ $*"; "${A[@]}" shell "$@" 2>&1; } > "$OUT/$f.txt"
}

"${A[@]}" get-state > "$OUT/state.txt" 2>&1
run getprop          getprop
run uname            uname -a
run id               id
run su-check         'command -v su || echo "kein su im PATH"'
run cpuinfo          cat /proc/cpuinfo
run meminfo          cat /proc/meminfo
run cpufreq          'for c in /sys/devices/system/cpu/cpu[0-9]*; do echo "$c $(cat $c/cpufreq/cpuinfo_min_freq 2>/dev/null) $(cat $c/cpufreq/cpuinfo_max_freq 2>/dev/null) $(cat $c/cpufreq/scaling_governor 2>/dev/null)"; done'
run partitions       cat /proc/partitions
run by-name          'ls -l /dev/block/by-name/ 2>&1 || ls -l /dev/block/bootdevice/by-name/ 2>&1'
run mounts           cat /proc/mounts
run df               df -h
run display          'wm size; wm density; dumpsys display | grep -iE "mDisplayInfos|PhysicalDisplayInfo|refreshRate|supportedModes|mBaseDisplayInfo" | head -20'
run gpu              'dumpsys SurfaceFlinger | grep -iE "GLES|EGL|Vulkan" | head -10'
run battery          dumpsys battery
run battery-sysfs    'for f in capacity charge_full charge_full_design cycle_count health status temp voltage_now technology; do echo "$f=$(cat /sys/class/power_supply/battery/$f 2>&1)"; done'
run sensors          'dumpsys sensorservice | sed -n "/Sensor List/,/^$/p" | head -80'
run camera           'dumpsys media.camera | grep -iE "Camera [0-9]|Facing|Resource cost|android.sensor.info.pixelArraySize|Device [0-9]" | head -40'
run features         pm list features
run packages-system  pm list packages -s
run wifi             'getprop | grep -iE "wifi|wlan|wcnss"; ls /sys/class/net/'
run bt               'getprop | grep -iE "bluetooth|bt\."'
run modem            'getprop | grep -iE "baseband|ril|radio|modem|gsm\.version"'
run thermal          'for z in /sys/class/thermal/thermal_zone*; do echo "$(cat $z/type 2>/dev/null) $(cat $z/temp 2>/dev/null)"; done | head -40'
run selinux          getenforce

echo "Rohdaten gespeichert in: $OUT"
