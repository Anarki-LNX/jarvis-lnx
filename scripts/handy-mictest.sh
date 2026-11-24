#!/bin/sh
: "${NUORB_SERVER_IP:?set NUORB_SERVER_IP (see config.env.example)}"
# Mikrofon-Schleifentest: TTS-Satz über Lautsprecher abspielen, gleichzeitig aufnehmen, an NuOrb-STT schicken.
# Aufruf: handy-mictest.sh <name> "<Befehle auf dem Handy vor der Aufnahme>" [raw|pw]
cd "$(dirname "$0")/.."
name=$1; pre=$2; mode=${3:-raw}
K="-i $HOME/.ssh/id_ed25519_nuorb -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"
if [ "$mode" = raw ]; then REC="arecord -q -D hw:0,1 -f S16_LE -r 48000 -c 1 -d 5 /tmp/t.wav"; else REC="systemd-run --user -M nuorb@ --pipe --wait --quiet /run/current-system/sw/bin/pw-record --rate 48000 --channels 1 --format s16 /tmp/t.wav"; fi
./scripts/handy-ssh.sh "$pre; rm -f /tmp/t.wav; ($REC) & sleep 1; systemd-run --user -M nuorb@ --pipe --wait --quiet /run/current-system/sw/bin/pw-play /tmp/tts.wav; sleep 1; pkill -x pw-record; wait; true" >/dev/null 2>&1
scp -q $K root@172.16.42.1:/tmp/t.wav diagnose/audio/$name.wav
printf "%-14s " "$name"; curl -sk -X POST https://${NUORB_SERVER_IP}:8443/api/stt -F "audio=@diagnose/audio/$name.wav" | head -c 120; echo
