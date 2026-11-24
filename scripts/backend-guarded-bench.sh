#!/usr/bin/env bash
# backend-guarded-bench.sh – backend-ollama-bench.sh mit Wächter (PC, ohne sudo).
# Nutzung: scripts/backend-guarded-bench.sh <modell> [vram_limit_gib=14.0] [ladefrist_s=90]
# Bricht ab und entlädt (ollama stop), wenn
#   - der Gesamt-VRAM (inkl. Desktop) über vram_limit_gib steigt, oder
#   - das Modell nach ladefrist_s Sekunden noch nicht in `ollama ps` als geladen erscheint
#     (genauer: noch keine Antwort auf den ersten Lauf vorliegt).
set -uo pipefail
MODEL=${1:?Modell angeben}
LIMIT=${2:-14.0}
LOADWAIT=${3:-90}
DIR=$(cd "$(dirname "$0")" && pwd)
OUT=$(mktemp)

vram_gib() { rocm-smi --showmeminfo vram 2>/dev/null | awk -F': ' '/Total Used/{printf "%.2f", $3/1073741824}'; }
abort() {
  echo "!! ABBRUCH: $1"
  kill "$BENCH" 2>/dev/null; pkill -P "$BENCH" 2>/dev/null
  ollama stop "$MODEL" >/dev/null 2>&1
  for i in $(seq 1 15); do [ -z "$(ollama ps | tail -n +2)" ] && break; sleep 2; done
  echo "nach Abbruch: VRAM $(vram_gib) GiB | ollama ps: $(ollama ps | tail -n +2 | wc -l) Modell(e)"
  exit 2
}

"$DIR/backend-ollama-bench.sh" "$MODEL" >"$OUT" 2>&1 &
BENCH=$!
start=$(date +%s); peak=0
while kill -0 "$BENCH" 2>/dev/null; do
  v=$(vram_gib); peak=$(awk -v a="$v" -v b="$peak" 'BEGIN{print (a>b)?a:b}')
  awk -v v="$v" -v l="$LIMIT" 'BEGIN{exit !(v>l)}' && { cat "$OUT"; abort "VRAM ${v} GiB > Limit ${LIMIT} GiB"; }
  if ! grep -q "gesamt" "$OUT" && [ $(( $(date +%s) - start )) -gt "$LOADWAIT" ]; then
    cat "$OUT"; abort "nach ${LOADWAIT}s noch nicht geladen"
  fi
  sleep 2
done
cat "$OUT"
echo "VRAM-Spitze während der Messung: ${peak} GiB (Limit ${LIMIT})"
rm -f "$OUT"
