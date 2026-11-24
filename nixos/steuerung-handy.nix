# JARVIS-Sprachsteuerung: eng begrenzter Fernzugang fuer jarvis (JARVIS_HOST).
# Optionales Modul (nicht standardmäßig importiert): in configuration.nix zu imports hinzufügen.
#
# Der Schluessel jarvis-steuerung@jarvis darf NUR von JARVIS_HOST kommen und NUR das
# Wrapper-Skript ausfuehren (command=, restrict: kein PTY, keine Weiterleitungen).
# Erlaubte Auftraege (SSH_ORIGINAL_COMMAND): status | generationen | neustart | rollback
# Jeder Aufruf landet im Journal: journalctl -t jarvis-steuerung
{ pkgs, ... }:
let
  site = import ./site.nix;
  steuerung = pkgs.writeShellScriptBin "jarvis-steuerung" ''
    set -u
    export PATH=${pkgs.lib.makeBinPath (with pkgs; [ coreutils gnugrep gawk util-linux networkmanager systemd iproute2 nix ])}
    cmd="''${SSH_ORIGINAL_COMMAND:-}"
    logger -t jarvis-steuerung "Auftrag: '$cmd' von ''${SSH_CLIENT%% *}"
    PROFIL=/nix/var/nix/profiles/system

    case "$cmd" in
      status)
        for d in /sys/class/power_supply/*; do
          [ "$(cat "$d/type" 2>/dev/null)" = Battery ] || continue
          echo "akku_prozent=$(cat "$d/capacity" 2>/dev/null)"
          echo "akku_zustand=$(cat "$d/status" 2>/dev/null)"
          t=$(cat "$d/temp" 2>/dev/null) && echo "akku_temp_c=$((t / 10))"
          break
        done
        max=0; maxname=""
        for z in /sys/class/thermal/thermal_zone*; do
          t=$(cat "$z/temp" 2>/dev/null) || continue
          [ "$t" -gt "$max" ] 2>/dev/null && { max=$t; maxname=$(cat "$z/type"); }
        done
        echo "temp_max_c=$((max / 1000))"
        echo "temp_max_zone=$maxname"
        wlan=$(nmcli -t -f ACTIVE,SSID,SIGNAL dev wifi 2>/dev/null | grep '^yes' | head -1)
        echo "wlan_ssid=$(echo "$wlan" | cut -d: -f2)"
        echo "wlan_signal=$(echo "$wlan" | cut -d: -f3)"
        echo "wlan_ip=$(ip -4 -o addr show wld0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"
        echo "uptime_s=$(cut -d. -f1 /proc/uptime)"
        echo "last=$(cut -d' ' -f1-3 /proc/loadavg)"
        echo "generation=$(readlink $PROFIL | grep -o '[0-9]*')"
        echo "kiosk_aktiv=$(pgrep -x epiphany >/dev/null && echo ja || echo nein)"
        ;;
      generationen)
        nix-env -p $PROFIL --list-generations | tail -n 5
        ;;
      neustart)
        systemd-run --quiet --collect --unit=jarvis-steuerung-neustart --on-active=3 systemctl reboot
        echo "neustart_in_s=3"
        ;;
      rollback)
        vorher=$(readlink $PROFIL)
        nix-env -p $PROFIL --rollback >/dev/null 2>&1 || { echo "fehler=keine vorherige Generation"; exit 2; }
        nachher=$(readlink $PROFIL)
        # abgekoppelt ausfuehren, damit ein Neustart von sshd/Phosh den Auftrag nicht abbricht
        systemd-run --quiet --collect --unit=jarvis-steuerung-rollback $PROFIL/bin/switch-to-configuration switch
        echo "von=$vorher"
        echo "auf=$nachher"
        ;;
      *)
        logger -t jarvis-steuerung "abgelehnt: '$cmd'"
        echo "fehler=Auftrag nicht erlaubt"
        exit 1
        ;;
    esac
  '';
in {
  users.users.root.openssh.authorizedKeys.keys = [
    ''from="${site.jarvisHost}",restrict,command="${steuerung}/bin/jarvis-steuerung" ssh-ed25519 REPLACE_WITH_PUBLIC_KEY_OF_jarvis-steuerung jarvis-steuerung@jarvis''
  ];
}
