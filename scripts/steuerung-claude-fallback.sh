#!/usr/bin/env bash
: "${JARVIS_HOST:?set JARVIS_HOST (see config.env.example)}"
# Traegt Claude (Anthropic-API) als Fallback-Modell in Hermes ein, falls das PC-Ollama nicht antwortet.
# VORAUSSETZUNG: Der Nutzer hat ANTHROPIC_API_KEY selbst eingetragen (~/bin/claude-key-setzen.sh auf jarvis).
# Aufruf vom PC:  scripts/steuerung-claude-fallback.sh <modell-id>      z. B. claude-haiku-5-5
#                 scripts/steuerung-claude-fallback.sh --entfernen
# Wiederholbar; config.yaml wird vorher gesichert. Prueft danach statisch (ohne Anfrage, kostet nichts).
set -euo pipefail
MODELL=${1:?Modell-ID oder --entfernen angeben}
case "$MODELL" in
  --entfernen|claude-haiku-5-5|claude-sonnet-5-5|claude-opus-5-5|claude-fable-5-2) ;;
  *) echo "Unbekanntes Modell $MODELL"; exit 1 ;;
esac
ssh -i "$HOME/.ssh/id_ed25519_jarvis" -o BatchMode=yes root@${JARVIS_HOST} "su - jarvis -c 'python3 - $MODELL'" <<'PY'
import os, re, shutil, sys, time
modell = sys.argv[1]
pfad = os.path.expanduser("~/.hermes/config.yaml")
txt = open(pfad).read()
ohne = re.sub(r"# >>> jarvis-claude-fallback.*?# <<< jarvis-claude-fallback\n", "", txt, flags=re.S)
if re.search(r"^fallback_providers:", ohne, flags=re.M):
    sys.exit("fallback_providers existiert schon ausserhalb des Blocks - bitte von Hand zusammenfuehren")
neu = ohne.rstrip("\n") + "\n"
if modell != "--entfernen":
    neu += f"""# >>> jarvis-claude-fallback (scripts/steuerung-claude-fallback.sh)
fallback_providers:
  - provider: anthropic
    model: {modell}
# <<< jarvis-claude-fallback
"""
if neu != txt:
    shutil.copy2(pfad, f"{pfad}.vor-claude-fallback.{time.strftime('%Y%m%d-%H%M%S')}")
    open(pfad, "w").write(neu)
    print("config.yaml aktualisiert:", modell)
else:
    print("config.yaml unveraendert")
PY
ssh -i "$HOME/.ssh/id_ed25519_jarvis" -o BatchMode=yes root@${JARVIS_HOST} "su - jarvis -c 'hermes fallback list; hermes fallback check'" || true
echo "Live-Pruefung (eine kurze, kostenpflichtige Anfrage, Bruchteil eines Cents): hermes fallback check --live"
