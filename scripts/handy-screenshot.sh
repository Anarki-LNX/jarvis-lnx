#!/bin/sh
# Screenshot vom NuOrb-Handy nach $1. cage: grim (wlr-screencopy) in der Wayland-Sitzung von nuorb;
# Phosh-Rückfall: org.gnome.Shell.Screenshot.
out=${1:-diagnose/nixos-erststart/screenshot.png}
"$(dirname "$0")/handy-ssh.sh" 'rm -f /tmp/.s.png
if systemctl is-active -q cage-tty1; then
  W=$(ls /run/user/1000/ | grep -m1 "^wayland-[0-9]$")
  runuser -u nuorb -- env XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=$W /opt/jt/grim /tmp/.s.png
else
  G=$(ls /nix/store/*-glib-*-bin/bin/gdbus | head -1)
  systemd-run --user -M nuorb@ --pipe --wait --quiet $G call --session --dest org.gnome.Shell.Screenshot --object-path /org/gnome/Shell/Screenshot --method org.gnome.Shell.Screenshot.Screenshot false false /tmp/.s.png >/dev/null
fi
cat /tmp/.s.png' > "$out" && echo "$out $(stat -c %s "$out") Bytes"
