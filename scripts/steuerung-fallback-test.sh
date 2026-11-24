#!/usr/bin/env bash
: "${OLLAMA_HOST:?set OLLAMA_HOST (see config.env.example)}"
# Simuliert "PC aus" fuer Hermes: sperrt auf nuorb (nur im LXC) kurz die Verbindung zu Ollama (${OLLAMA_HOST}:11434)
# und stellt eine Testfrage. Antwortet Claude, greift der Fallback. Die Sperre wird immer wieder entfernt.
# Aufruf auf nuorb als root:  bash steuerung-fallback-test.sh     (kostet eine Claude-Anfrage, ca. 2-3 Cent)
set -u
T=nuorb_fallbacktest
aufraeumen() { nft delete table inet $T 2>/dev/null; }
trap aufraeumen EXIT
nft add table inet $T
nft add chain inet $T out '{ type filter hook output priority 0; }'
nft add rule inet $T out ip daddr ${OLLAMA_HOST} tcp dport 11434 reject with tcp reset
echo "Sperre aktiv: $(date +%T)"
start=$(date +%s)
su - nuorb -c 'cd /tmp && timeout 150 hermes chat -q "Antworte in einem Satz: Welches Sprachmodell genau beantwortet gerade diese Frage?" --oneshot 2>&1' \
  | grep -v '^$' | grep -iv -e resume -e '^Session:' | tail -5
echo "Dauer: $(( $(date +%s) - start )) s"
aufraeumen; trap - EXIT
echo "Sperre entfernt: $(date +%T)"; nft list tables
