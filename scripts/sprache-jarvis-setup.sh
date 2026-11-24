#!/usr/bin/env bash
# XIAOMI REBIRTH / JARVIS: lokale deutsche Sprachkette fuer Hermes in LXC 100 "jarvis" (nur CPU).
#   TTS: Piper + thorsten (CC0)
#   STT: Parakeet-TDT-0.6B-v3 int8 (sherpa-onnx) im residenten STT-Router (127.0.0.1:8178, OpenAI-kompatibel)
#        Reserve: faster-whisper small im Hermes-Prozess (STT_WEG=whisper)
#   Edge TTS: aus
# Laeuft als Benutzer jarvis (kein root, kein sudo), idempotent. Die systemd-Unit des Routers
# installiert root einmalig (siehe scripts/sprache-stt-router.service).
# Aufruf vom PC:
#   scp -i ~/.ssh/id_ed25519_jarvis scripts/sprache-jarvis-setup.sh scripts/sprache-stt-router.py root@${JARVIS_HOST}:/tmp/
#   ssh -i ~/.ssh/id_ed25519_jarvis root@${JARVIS_HOST} 'su - jarvis -c "bash /tmp/sprache-jarvis-setup.sh"'
# Variablen (optional): STIMME=de_DE-thorsten-medium|high  STT_MODELL=whisper-small  STT_WEG=router|whisper
set -euo pipefail
STIMME=${STIMME:-de_DE-thorsten-medium}
STT_MODELL=${STT_MODELL:-whisper-small}
STT_WEG=${STT_WEG:-router}
HF=https://huggingface.co
H=$HOME/.hermes
V=$H/cache/piper-voices
M=$H/models

# 1) Python-Pakete ueber Hermes' eigenen Paketmanager (PM): piper-tts, faster-whisper (+ onnxruntime, ctranslate2, av)
#    NICHT scripts/run-in-hermes-env benutzen: das baut die komplette Test-Umgebung ([all]+dev+test).
hermes pm install --extra piper --extra stt-whisper

# 2) Stimmen (rhasspy/piper-voices, thorsten = CC0) – medium ~60 MB, high ~109 MB
mkdir -p "$V"
for q in medium high; do for e in onnx onnx.json; do
  f=$V/de_DE-thorsten-$q.$e
  [ -s "$f" ] || curl -sfL -o "$f" "$HF/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/$q/de_DE-thorsten-$q.$e"
done; done

# 3) Whisper-Modelle (CTranslate2-Format) direkt als Ordner, damit Hermes offline laedt
#    small: Systran/faster-whisper-small (MIT, ~461 MB)
#    (turbo-german int8 braucht auf dieser CPU ~15 s pro Aeusserung -> nur fuer die PC-GPU, hier nicht geladen)
hole_repo() {  # $1 = HF-Repo, $2 = Zielordner
  mkdir -p "$2"
  for f in $(curl -sf "$HF/api/models/$1" | jq -r '.siblings[].rfilename' | grep -v -e '^\.git' -e README); do
    [ -s "$2/$f" ] || curl -sfL -o "$2/$f" "$HF/$1/resolve/main/$f"
  done
}
hole_repo Systran/faster-whisper-small "$M/whisper-small"

# 3b) Parakeet (k2-fsa/sherpa-onnx, Modell CC-BY-4.0, 464 MB Download / 641 MB entpackt) + eigenes venv
P=sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8
[ -s "$M/$P/encoder.int8.onnx" ] || curl -sfL "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/$P.tar.bz2" | tar xj -C "$M"
mkdir -p ~/sprache
[ -x ~/sprache/venv/bin/python ] || python3 -m venv ~/sprache/venv
~/sprache/venv/bin/pip install -q sherpa-onnx==2.0.3 numpy
[ -f /tmp/sprache-stt-router.py ] && cp /tmp/sprache-stt-router.py ~/sprache/

# 4) Hermes konfigurieren (Edge TTS wird damit nicht mehr benutzt)
hermes config set tts.provider piper
hermes config set tts.piper.voice "$V/$STIMME.onnx"
hermes config set stt.language de
hermes config set stt.local.model "$M/$STT_MODELL"
hermes config set stt.openai.base_url http://127.0.0.1:8178/v1   # lokale URL -> kein Key noetig
hermes config set stt.openai.model parakeet                     # != whisper-1 -> JSON-Antwort
hermes config set stt.openai.language de
if [ "$STT_WEG" = router ]; then hermes config set stt.provider openai; else hermes config set stt.provider local; fi
hermes config set voice.stop_phrases '["stopp", "stop", "danke jarvis"]'

echo "--- aktiv:"
for k in tts.provider tts.piper.voice stt.provider stt.language stt.local.model stt.openai.base_url; do
  printf '%-18s %s\n' "$k" "$(hermes config get "$k")"
done
