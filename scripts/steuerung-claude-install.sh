#!/usr/bin/env bash
: "${JARVIS_HOST:?set JARVIS_HOST (see config.env.example)}"
# Installiert den MCP-Server "claude" (Projekt-Claude per Sprache) auf jarvis und traegt ihn in Hermes ein.
# Voraussetzungen auf jarvis: ~/.local/bin/claude (native Claude Code), ANTHROPIC_API_KEY in ~/.hermes/.env,
# Git-Arbeitskopie ~/projekte/jarvis-ui.
# Aufruf vom PC:  scripts/steuerung-claude-install.sh [installieren|entfernen] [modell-id]
# Fuehrt zusammen: andere Server unter mcp_servers (z. B. aus jarvis-admin) bleiben erhalten; ohne
# Modellangabe bleibt ein vorhandenes CLAUDE_MODELL bestehen (Logik: steuerung-claude-config.py).
set -euo pipefail
cd "$(dirname "$0")"
J="ssh -i $HOME/.ssh/id_ed25519_jarvis -o BatchMode=yes root@${JARVIS_HOST}"
D=/home/jarvis/.hermes/projekt-claude
MODUS=${1:-installieren}
MODELL=${2:-}
$J "install -d -o jarvis -g jarvis -m 700 $D"
for f in steuerung-claude-mcp.py:claude_mcp.py steuerung-claude-config.py:claude_config.py steuerung-fallback-setzen.py:fallback_setzen.py; do
  $J "cat > $D/${f#*:} && chown jarvis:jarvis $D/${f#*:} && chmod 700 $D/${f#*:}" < "${f%%:*}"
done
$J "su - jarvis -c 'python3 $D/claude_config.py $MODUS $MODELL'"
echo "== Gateway uebernimmt mcp_servers-Aenderungen laut Doku innerhalb ~1 min (Log: 'MCP servers reconciled')"
