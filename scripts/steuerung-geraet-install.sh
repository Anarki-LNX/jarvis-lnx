#!/usr/bin/env bash
: "${JARVIS_HOST:?set JARVIS_HOST (see config.env.example)}"
# Traegt den MCP-Server "geraet" (Geraeteabsicht, fuehrt selbst nichts aus) in Hermes ein bzw. entfernt ihn.
# Aufruf vom PC:  scripts/steuerung-geraet-install.sh [installieren|entfernen]
# Eintrag als eingerueckter, markierter Unterblock in mcp_servers (wie jarvis-projekt-claude); andere Server bleiben.
set -euo pipefail
cd "$(dirname "$0")"
J="ssh -i $HOME/.ssh/id_ed25519_jarvis -o BatchMode=yes root@${JARVIS_HOST}"
D=/home/jarvis/.hermes/projekt-claude
MODUS=${1:-installieren}
$J "install -d -o jarvis -g jarvis -m 700 $D"
$J "cat > $D/geraet_mcp.py && chown jarvis:jarvis $D/geraet_mcp.py && chmod 700 $D/geraet_mcp.py" < steuerung-geraet-mcp.py
$J "su - jarvis -c 'python3 - $MODUS'" <<'PY'
import os, re, shutil, sys, time
modus = sys.argv[1]
pfad = os.path.expanduser("~/.hermes/config.yaml")
txt = open(pfad).read()
UNTER = re.compile(r"^  # >>> jarvis-geraet[^\n]*\n.*?^  # <<< jarvis-geraet[^\n]*\n", re.S | re.M)
KOPF = re.compile(r"^mcp_servers:[ \t]*(\{\}|null|~)?[ \t]*$", re.M)
neu = UNTER.sub("", txt)
if len(re.findall(r"^mcp_servers:", neu, re.M)) > 1:
    sys.exit("mcp_servers mehrfach vorhanden - nichts geaendert")
if modus == "installieren":
    block = """  # >>> jarvis-geraet (scripts/steuerung-geraet-install.sh)
  geraet:
    command: /usr/bin/python3
    args: [/home/jarvis/.hermes/projekt-claude/geraet_mcp.py]
    trust: full
    timeout: 10
    tools:
      resources: false
      prompts: false
  # <<< jarvis-geraet
"""
    k = KOPF.search(neu)
    if k:
        neu = neu[:k.start()] + "mcp_servers:\n" + block + neu[k.end() + 1:]
    elif re.search(r"^mcp_servers:", neu, re.M):
        sys.exit("mcp_servers hat eine ungewohnte Form - nichts geaendert")
    else:
        neu = neu.rstrip("\n") + "\nmcp_servers:\n" + block
if neu != txt:
    shutil.copy2(pfad, f"{pfad}.vor-geraet.{time.strftime('%Y%m%d-%H%M%S')}")
    open(pfad + ".neu", "w").write(neu)
    os.replace(pfad + ".neu", pfad)
    print("config.yaml aktualisiert:", modus)
else:
    print("config.yaml unveraendert")
PY
