#!/usr/bin/env bash
: "${NUORB_SERVER_IP:?set NUORB_SERVER_IP (see config.env.example)}"
# backend-ollama-firewall.sh – Ollama-Port 11434 auf dem PC absichern (ufw).
#
# Ausgangslage (gelesen 2026-11-24):
#   - ufw aktiv, Default INPUT = DROP
#   - Regel "allow 11434/tcp from anywhere" -> jeder im LAN (und jedes Gerät im
#     Gast-/IoT-Netz, falls nicht getrennt) kann Modelle laden, löschen, pullen.
#   - Ollama lauscht auf 0.0.0.0:11434 (systemd-Override), hat keine Auth.
#
# Ziel: nur localhost (ufw filtert lo nicht) und NuOrb-LXC ${NUORB_SERVER_IP}.
# Ollama bleibt an 0.0.0.0 gebunden, damit `ollama` auf dem PC selbst weiter
# über 127.0.0.1 funktioniert; die Firewall macht die Einschränkung.
#
# Ausführen:  sudo NUORB_SERVER_IP=<ip> bash scripts/backend-ollama-firewall.sh
# Rückgängig: sudo ufw delete allow proto tcp from ${NUORB_SERVER_IP} to any port 11434
#             sudo ufw allow 11434/tcp
set -euo pipefail


[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }

echo "== Vorher =="
ufw status numbered | grep -E "11434|Status" || true

# 1) Erst die neue, enge Regel anlegen (kein Moment ohne NuOrb-Zugang) …
ufw allow proto tcp from "$NUORB_SERVER_IP" to any port 11434 comment 'Ollama nur fuer NuOrb-LXC'

# 2) … dann die offene Regel entfernen (entfernt v4 und v6).
ufw delete allow 11434/tcp || echo "Offene Regel war nicht (mehr) vorhanden."

echo "== Nachher =="
ufw status numbered | grep -E "11434|Status" || true
