#!/usr/bin/env bash
# backend-ollama-bench.sh – Latenz/Durchsatz/VRAM/Swap eines Ollama-Modells messen (PC, ohne sudo).
# Nutzung: scripts/backend-ollama-bench.sh <modell>
# Läufe über die native API (/api/chat, Streaming), num_ctx kommt aus dem Modelfile:
#   1) kalt, kurzer Prompt  -> Ladezeit
#   2) warm, ~8k-Token-Prompt (Größe eines Hermes-Aufrufs) -> Prefill-Tempo, Zeit bis 1. Token
#   3) warm, kurzer Prompt mit ~200 Token Antwort -> Generierungstempo
# Misst VRAM (rocm-smi) und Swap vorher/geladen/nachher, zeigt `ollama ps`,
# entlädt danach mit `ollama stop` (VRAM frei für Desktop und Sprachkette).
set -euo pipefail
MODEL=${1:?Modell angeben}
HOST=${OLLAMA_URL:-http://127.0.0.1:11434}

vram() { rocm-smi --showmeminfo vram 2>/dev/null | awk -F': ' '/Total Used/{printf "%.2f GiB", $3/1073741824}'; }
swap() { free -m | awk '/^Swap|^Auslager/{printf "%.2f GiB", $3/1024}'; }

echo "### $MODEL"
echo "vorher:  VRAM $(vram) | Swap $(swap)"

run() {
  python3 -I - "$HOST" "$MODEL" "$1" "$2" <<'PY'
import json, sys, time, urllib.request
host, model, prompt, npred = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
body = json.dumps({"model": model, "stream": True, "think": False,
    "options": {"temperature": 0.3, "num_predict": npred},
    "messages": [{"role": "user", "content": prompt}]}).encode()
req = urllib.request.Request(host + "/api/chat", body, {"Content-Type": "application/json"})
t0 = time.time(); ttft = None; last = None; text = []
with urllib.request.urlopen(req, timeout=900) as r:
    for line in r:
        d = json.loads(line); msg = d.get("message", {})
        if ttft is None and (msg.get("content") or msg.get("thinking")):
            ttft = time.time() - t0
        text.append(msg.get("content", ""))
        if d.get("done"): last = d
ns = 1e9
pe = last.get("prompt_eval_duration") or 1
print(f"  gesamt {time.time()-t0:6.1f}s | 1. Token {ttft or 0:6.2f}s | Laden {last.get('load_duration',0)/ns:5.1f}s"
      f" | Prefill {last.get('prompt_eval_count',0)} tok @ {last.get('prompt_eval_count',0)/(pe/ns):7.0f} tok/s"
      f" | Gen {last['eval_count']} tok @ {last['eval_count']/(last['eval_duration']/ns):5.1f} tok/s")
print("  Antwort:", "".join(text).strip().replace("\n", " ")[:120])
PY
}

LONG=$(python3 -I -c "print(' '.join(f'Absatz {i}: Der Assistent NuOrb läuft in einem Proxmox-Container, spricht Deutsch, liest Dateien, merkt sich Notizen und legt Erinnerungen an.' for i in range(260)))")

echo "Lauf 1 (kalt):";            run "Sag in einem deutschen Satz, wer du bist." 40
echo "Lauf 2 (warm, ~8k Prompt):"; run "$LONG Fasse den Text oben in einem deutschen Satz zusammen." 60
echo "Lauf 3 (warm, Generierung):"; run "Erkläre in etwa 150 Wörtern auf Deutsch, warum ein lokaler Sprachassistent sinnvoll ist." 220

echo "geladen: VRAM $(vram) | Swap $(swap)"
ollama ps | sed 's/^/  /'
ollama stop "$MODEL" >/dev/null 2>&1 || true
for i in $(seq 1 12); do [ -z "$(ollama ps | tail -n +2)" ] && break; sleep 2; done
echo "nachher: VRAM $(vram) | Swap $(swap) | ollama ps: $(ollama ps | tail -n +2 | wc -l) Modell(e)"
