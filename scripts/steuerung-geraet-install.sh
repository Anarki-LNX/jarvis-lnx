#!/usr/bin/env bash
: "${NUORB_SERVER_IP:?set NUORB_SERVER_IP (see config.env.example)}"
# Traegt den MCP-Server "geraet" (Geraeteabsicht, fuehrt selbst nichts aus) in Hermes ein bzw. entfernt ihn.
# Aufruf vom PC:  scripts/steuerung-geraet-install.sh [installieren|entfernen]
# Eintrag als eingerueckter, markierter Unterblock in mcp_servers (wie nuorb-projekt-claude); andere Server bleiben.
set -euo pipefail
cd "$(dirname "$0")"
J="ssh -i $HOME/.ssh/id_ed25519_nuorb -o BatchMode=yes root@${NUORB_SERVER_IP}"
D=/home/nuorb/.hermes/projekt-claude
MODUS=${1:-installieren}
$J "install -d -o nuorb -g nuorb -m 700 $D"
$J "cat > $D/geraet_mcp.py && chown nuorb:nuorb $D/geraet_mcp.py && chmod 700 $D/geraet_mcp.py" < steuerung-geraet-mcp.py
$J "su - nuorb -c 'python3 - $MODUS'" <<'PY'
import os, re, shutil, sys, time
modus = sys.argv[1]
pfad = os.path.expanduser("~/.hermes/config.yaml")
txt = open(pfad).read()
UNTER = re.compile(r"^  # >>> nuorb-geraet[^\n]*\n.*?^  # <<< nuorb-geraet[^\n]*\n", re.S | re.M)
KOPF = re.compile(r"^mcp_servers:[ \t]*(\{\}|null|~)?[ \t]*$", re.M)
neu = UNTER.sub("", txt)
if len(re.findall(r"^mcp_servers:", neu, re.M)) > 1:
    sys.exit("mcp_servers mehrfach vorhanden - nichts geaendert")
if modus == "installieren":
    block = """  # >>> nuorb-geraet (scripts/steuerung-geraet-install.sh)
  geraet:
    command: /usr/bin/python3
    args: [/home/nuorb/.hermes/projekt-claude/geraet_mcp.py]
    trust: full
    timeout: 10
    tools:
      resources: false
      prompts: false
  # <<< nuorb-geraet
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
