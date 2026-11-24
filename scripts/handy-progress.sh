#!/bin/sh
# Gibt jede Minute den Build-Fortschritt aus (gewichtet: squeekboard = 80 %, die übrigen 16 Pakete = 20 %).
cd "$(dirname "$0")/.."
while true; do
  c=$(docker ps -q --filter ancestor=nixos/nix:latest | head -1)
  if [ -z "$c" ]; then echo "Fortschritt: kein Build-Container mehr – $(grep -E '^== exit' build/handy-nixos-build.log | tail -1)"; exit 0; fi
  res=$(docker exec -i "$c" sh -c 'done=0; sq=0; while read d; do o=$(nix-store -q --outputs "$d" 2>/dev/null | head -1); if [ -n "$o" ] && [ -e "$o" ]; then done=$((done+1)); case "$d" in *squeekboard*) sq=1;; esac; fi; done; echo "$done $sq"' < build/handy-todo-drvs.txt 2>/dev/null)
  set -- $res; d=${1:-0}; sq=${2:-0}
  other=$((d - sq)); pct=$(( sq*80 + other*20/16 ))
  cur=$(grep -oE "^building '/nix/store/[a-z0-9]+-[^']+" build/handy-nixos-build.log | tail -1 | sed 's|.*/[a-z0-9]*-||; s|\.drv||')
  echo "Fortschritt: ${pct}% ($d/17 Pakete fertig, squeekboard $( [ "$sq" = 1 ] && echo fertig || echo läuft)) – zuletzt gestartet: $cur – $(date +%H:%M)"
  sleep 60
done
