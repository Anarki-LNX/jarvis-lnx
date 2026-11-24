#!/usr/bin/env python3
"""Traegt den MCP-Server 'handy' in ~/.hermes/config.yaml ein (Block zwischen Markierungen, wiederholbar).
Aufruf auf jarvis als Benutzer jarvis:  python3 steuerung-hermes-config.py <Handy-IP>"""
import os, re, shutil, sys, time

ip = sys.argv[1]
if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip):
    sys.exit("ungueltige IP")
pfad = os.path.expanduser("~/.hermes/config.yaml")
txt = open(pfad).read()
block = f"""# >>> jarvis-steuerung (scripts/steuerung-install-jarvis.sh)
mcp_servers:
  handy:
    command: /usr/bin/python3
    args: [/home/jarvis/.hermes/steuerung/handy_mcp.py]
    env:
      HANDY_HOST: "{ip}"
    trust: untrusted
    timeout: 90
    tools:
      resources: false
      prompts: false
# <<< jarvis-steuerung
"""
ohne = re.sub(r"# >>> jarvis-steuerung.*?# <<< jarvis-steuerung\n", "", txt, flags=re.S)
if re.search(r"^mcp_servers:", ohne, flags=re.M):
    sys.exit("mcp_servers existiert schon ausserhalb des Blocks - bitte von Hand zusammenfuehren")
neu = ohne.rstrip("\n") + "\n" + block
if neu != txt:
    shutil.copy2(pfad, f"{pfad}.vor-steuerung.{time.strftime('%Y%m%d-%H%M%S')}")
    open(pfad, "w").write(neu)
    print("config.yaml aktualisiert")
else:
    print("config.yaml unveraendert")
