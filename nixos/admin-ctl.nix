# Eingeschränkter Fernzugang für das Admin-UI auf jarvis (JARVIS_HOST).
# Vom Nutzer im Handy-Chat ausdrücklich freigegeben (2026-11-24, „Ja, einrichten“).
#
# - eigener Benutzer jarvis-ctl (nicht root), nur Schlüsselanmeldung
# - Schlüssel nur von JARVIS_HOST, restrict (kein PTY/Weiterleitungen), erzwungener Befehl
# - erlaubte Aufträge (SSH_ORIGINAL_COMMAND):
#     status | reboot | kiosk-reload | helligkeit <0-100> | lautstaerke <0-100> | bildschirm an|aus
#   alles andere: exit 2 „nicht erlaubt“; jeder Aufruf im Journal (journalctl -t jarvis-ctl)
# - Root-Rechte nur über sudo für genau ein Helfer-Skript, das die Argumente selbst noch einmal prüft.
{ lib, pkgs, ... }:
let
  site = import ./site.nix;
  pubFile = ./admin-handy.pub;
  haveKey = builtins.pathExists pubFile;

  helfer = pkgs.writeShellScript "jarvis-ctl-root" ''
    set -u
    export PATH=${lib.makeBinPath (with pkgs; [ coreutils gnugrep gawk procps util-linux networkmanager iproute2 iw systemd wireplumber nix ])}
    BL=$(ls -d /sys/class/backlight/* 2>/dev/null | head -1)
    alsJarvis() { runuser -u jarvis -- env XDG_RUNTIME_DIR=/run/user/1000 "$@"; }
    zahl() { case "$1" in ""|*[!0-9]*) return 1;; esac; [ "$1" -le 100 ]; }
    json_str() { [ -n "$1" ] && printf '"%s"' "$(printf '%s' "$1" | tr -d '"\\')" || printf null; }
    json_num() { case "$1" in ""|*[!0-9.-]*) printf null;; *) printf '%s' "$1";; esac; }

    case "''${1:-}" in
      status)
        q=/sys/class/power_supply/qcom_qg
        cap=$(cat $q/capacity 2>/dev/null); st=$(cat $q/status 2>/dev/null); t=$(cat $q/temp 2>/dev/null)
        [ -n "$t" ] && t=$(awk "BEGIN{printf \"%.1f\", $t/10}")
        case "$st" in Charging) laedt=true;; "") laedt=null;; *) laedt=false;; esac
        export LC_ALL=C
        ssid=$(nmcli -t -f ACTIVE,SSID dev wifi 2>/dev/null | grep '^yes:' | head -1 | cut -d: -f2)
        dbm=$(iw dev wld0 link 2>/dev/null | awk '/signal:/{print $2}')
        ip=$(ip -4 -o addr show wld0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
        up=$(cut -d. -f1 /proc/uptime)
        if ps -eo comm | grep -q epiphany; then kiosk=true; else kiosk=false; fi
        hell=""; [ -n "$BL" ] && hell=$(( $(cat $BL/brightness) * 100 / $(cat $BL/max_brightness) ))
        vol=$(alsJarvis wpctl get-volume @DEFAULT_AUDIO_SINK@ 2>/dev/null | awk '{printf "%d", $2*100}')
        gen=$(readlink /nix/var/nix/profiles/system | grep -o '[0-9]*' | tail -1)
        printf '{"akku_prozent":%s,"laedt":%s,"akku_temp":%s,"wlan_ssid":%s,"wlan_signal_dbm":%s,"ip":%s,"uptime_s":%s,"kiosk_laeuft":%s,"helligkeit_prozent":%s,"lautstaerke_prozent":%s,"nixos_generation":%s}\n' \
          "$(json_num "$cap")" "$laedt" "$(json_num "$t")" "$(json_str "$ssid")" "$(json_num "$dbm")" \
          "$(json_str "$ip")" "$(json_num "$up")" "$kiosk" "$(json_num "$hell")" "$(json_num "$vol")" "$(json_num "$gen")"
        ;;
      reboot)
        systemd-run --quiet --collect --unit=jarvis-ctl-reboot --on-active=3 systemctl reboot
        echo '{"ok":true,"reboot_in_s":3}'
        ;;
      kiosk-reload)
        # Kiosk-Schleife startet Epiphany selbst neu und holt das Vollbild zurück
        for p in $(ps -eo pid,comm | awk '$2 ~ /epiphany/ {print $1}'); do kill "$p"; done
        echo '{"ok":true}'
        ;;
      helligkeit)
        zahl "''${2:-}" || { echo '{"ok":false,"fehler":"Wert 0-100"}'; exit 2; }
        [ -n "$BL" ] || { echo '{"ok":false,"fehler":"kein Backlight"}'; exit 1; }
        max=$(cat $BL/max_brightness); v=$(( $2 * max / 100 )); [ "$v" -lt 1 ] && v=1
        echo "$v" > $BL/brightness
        echo "{\"ok\":true,\"helligkeit_prozent\":$2}"
        ;;
      lautstaerke)
        zahl "''${2:-}" || { echo '{"ok":false,"fehler":"Wert 0-100"}'; exit 2; }
        alsJarvis wpctl set-volume @DEFAULT_AUDIO_SINK@ "$2%" && echo "{\"ok\":true,\"lautstaerke_prozent\":$2}"
        ;;
      bildschirm)
        [ -n "$BL" ] || { echo '{"ok":false,"fehler":"kein Backlight"}'; exit 1; }
        case "''${2:-}" in
          an)  echo 0 > $BL/bl_power; echo '{"ok":true,"bildschirm":"an"}';;
          aus) echo 4 > $BL/bl_power; echo '{"ok":true,"bildschirm":"aus"}';;
          *)   echo '{"ok":false,"fehler":"an|aus"}'; exit 2;;
        esac
        ;;
      *) echo '{"ok":false,"fehler":"nicht erlaubt"}'; exit 2;;
    esac
  '';

  wrapper = pkgs.writeShellScript "jarvis-ctl" ''
    set -u
    cmd="''${SSH_ORIGINAL_COMMAND:-}"
    ${pkgs.util-linux}/bin/logger -t jarvis-ctl "Auftrag: '$cmd' von ''${SSH_CLIENT%% *}"
    set -- $cmd
    case "''${1:-}" in
      status|reboot|kiosk-reload) [ $# -eq 1 ] || { echo '{"ok":false,"fehler":"nicht erlaubt"}'; exit 2; } ;;
      helligkeit|lautstaerke|bildschirm) [ $# -eq 2 ] || { echo '{"ok":false,"fehler":"nicht erlaubt"}'; exit 2; } ;;
      *) ${pkgs.util-linux}/bin/logger -t jarvis-ctl "abgelehnt: '$cmd'"; echo '{"ok":false,"fehler":"nicht erlaubt"}'; exit 2 ;;
    esac
    exec /run/wrappers/bin/sudo -n ${helfer} "$@"
  '';
in
{
  environment.etc."jarvis-ctl/wrapper".source = wrapper;  # zum lokalen Testen
  users.users.jarvis-ctl = {
    isSystemUser = true;
    group = "jarvis-ctl";
    shell = pkgs.bashInteractive;
    openssh.authorizedKeys.keys = lib.optional haveKey
      ''from="${site.jarvisHost}",restrict,command="${wrapper}" ${lib.removeSuffix "\n" (builtins.readFile pubFile)}'';
  };
  users.groups.jarvis-ctl = { };

  security.sudo.extraRules = [
    {
      users = [ "jarvis-ctl" ];
      commands = [ { command = "${helfer}"; options = [ "NOPASSWD" ]; } ];
    }
  ];
}
