#!/usr/bin/env python3
"""Traegt den MCP-Server 'claude' in ~/.hermes/config.yaml ein oder entfernt ihn - zusammenfuehrend.
Laeuft auf nuorb als Benutzer nuorb:  python3 claude_config.py installieren|entfernen [modell-id]

Der Eintrag steht als markierter Unterblock INNERHALB von mcp_servers:
    mcp_servers:
      # >>> nuorb-projekt-claude (...)
      claude:
        ...
      # <<< nuorb-projekt-claude
      <andere Server, z. B. aus dem Admin-Panel>
Andere Eintraege unter mcp_servers bleiben unangetastet. Ein frueherer Block auf oberster Ebene
(# >>> nuorb-projekt-claude ... mcp_servers: ... # <<<) wird umgewandelt, ohne dass nachfolgende
Server ihren Elternschluessel verlieren. Ein vorhandenes CLAUDE_MODELL (z. B. vom Admin-Panel
gesetzt) bleibt erhalten, wenn kein Modell angegeben wird."""
import os, re, shutil, sys, time

ERLAUBT = {"claude-haiku-5-5": "Haiku 5.5", "claude-sonnet-5-5": "Sonnet 5.5", "claude-opus-5-5": "Opus 5.5"}
PFAD = os.path.expanduser("~/.hermes/config.yaml")
ALT = re.compile(r"^# >>> nuorb-projekt-claude[^\n]*\n.*?^# <<< nuorb-projekt-claude[^\n]*\n", re.S | re.M)
UNTER = re.compile(r"^  # >>> nuorb-projekt-claude[^\n]*\n.*?^  # <<< nuorb-projekt-claude[^\n]*\n", re.S | re.M)
KOPF = re.compile(r"^mcp_servers:[ \t]*(\{\}|null|~)?[ \t]*$", re.M)

modus = sys.argv[1] if len(sys.argv) > 1 else ""
if modus not in ("installieren", "entfernen"):
    sys.exit("Aufruf: claude_config.py installieren|entfernen [modell-id]")
txt = open(PFAD).read()

alt_modell = None
for m in list(ALT.finditer(txt)) + list(UNTER.finditer(txt)):
    t = re.search(r"CLAUDE_MODELL:\s*['\"]?([\w.-]+)", m.group(0))
    if t:
        alt_modell = t.group(1)
modell = sys.argv[2] if len(sys.argv) > 2 else (alt_modell or "claude-sonnet-5-5")
if modell not in ERLAUBT:
    sys.exit(f"Modell nicht erlaubt: {modell} (erlaubt: {', '.join(ERLAUBT)})")

neu = ALT.sub("mcp_servers:\n", txt)   # alter Block auf oberster Ebene -> nur der Kopf bleibt
neu = UNTER.sub("", neu)
koepfe = list(KOPF.finditer(neu))
if len(re.findall(r"^mcp_servers:", neu, re.M)) > 1:
    sys.exit("mcp_servers kommt mehrfach vor - bitte von Hand zusammenfuehren, nichts geaendert")
if not koepfe and re.search(r"^mcp_servers:", neu, re.M):
    sys.exit("mcp_servers hat eine ungewohnte Form (z. B. Inline-Mapping) - bitte von Hand, nichts geaendert")

name = ERLAUBT[modell]
unterblock = f"""  # >>> nuorb-projekt-claude (scripts/steuerung-claude-install.sh)
  claude:
    command: /usr/bin/python3
    args: [/home/nuorb/.hermes/projekt-claude/claude_mcp.py]
    env:
      CLAUDE_PROJEKT: /home/nuorb/projekte/nuorb-ui
      CLAUDE_MODELL: {modell}
    trust: untrusted
    timeout: 660
    supports_parallel_tool_calls: false
    cost_unit: Cent
    tool_costs:
      fragen: {{credits: [1, 30], note: "Claude {name}, nur lesen"}}
      auftrag: {{credits: [5, 100], note: "Claude {name}, aendert Dateien"}}
    spend_limit: 100
    tools:
      resources: false
      prompts: false
  # <<< nuorb-projekt-claude
"""

if modus == "installieren":
    if koepfe:
        k = koepfe[0]
        neu = neu[:k.start()] + "mcp_servers:\n" + unterblock + neu[k.end() + 1:]
    else:
        neu = neu.rstrip("\n") + "\nmcp_servers:\n" + unterblock
else:
    k = KOPF.search(neu)
    if k:
        rest = neu[k.end() + 1:]
        # leer, wenn bis zur naechsten Zeile auf oberster Ebene nur Leerzeilen/Kommentare folgen
        naechste = re.search(r"^(?=[^ \t#\n])", rest, re.M)
        inhalt = rest[:naechste.start()] if naechste else rest
        if not re.search(r"^[ \t]+[^#\s]", inhalt, re.M):
            neu = neu[:k.start()] + "mcp_servers: {}\n" + rest

if neu != txt:
    shutil.copy2(PFAD, f"{PFAD}.vor-projekt-claude.{time.strftime('%Y%m%d-%H%M%S')}")
    tmp = PFAD + ".neu"
    open(tmp, "w").write(neu)
    os.replace(tmp, PFAD)
    print(f"config.yaml aktualisiert: {modus} ({modell})")
else:
    print("config.yaml unveraendert")
