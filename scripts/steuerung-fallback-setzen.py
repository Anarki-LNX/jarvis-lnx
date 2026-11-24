#!/usr/bin/env python3
"""Schnittstelle fuer nuorb-admin: Fallback-Modell von Hermes lesen/umstellen (auf nuorb als Benutzer nuorb).
Installiert als ~/.hermes/projekt-claude/fallback_setzen.py

  fallback_setzen.py status                 -> JSON {"fallback": "<modell>"|null, "erlaubt": [...]}
  fallback_setzen.py setzen <modell-id>     -> traegt ein (Sicherung von config.yaml), prueft statisch
  fallback_setzen.py entfernen              -> Fallback aus
  fallback_setzen.py pruefen                -> hermes fallback check --live (eine Mini-Anfrage, < 0,1 Cent)

Kein Gateway-Neustart noetig: die Aenderung gilt ab der naechsten Frage (getestet 2026-11-24 13:34).
Ausgabe immer als eine JSON-Zeile; Exit-Code 0 = ok."""
import json, os, re, shutil, subprocess, sys, time

ERLAUBT = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
PFAD = os.path.expanduser("~/.hermes/config.yaml")
HERMES = os.path.expanduser("~/.local/bin/hermes")
BLOCK = re.compile(r"# >>> nuorb-claude-fallback.*?# <<< nuorb-claude-fallback\n", re.S)


def aus(d, rc=0):
    print(json.dumps(d, ensure_ascii=False)); sys.exit(rc)


def aktuell(txt):
    m = BLOCK.search(txt)
    return re.search(r"model:\s*(\S+)", m.group(0)).group(1) if m else None


def schreiben(modell):
    txt = open(PFAD).read()
    ohne = BLOCK.sub("", txt)
    if re.search(r"^fallback_providers:", ohne, re.M):
        aus({"ok": False, "fehler": "fallback_providers ausserhalb des markierten Blocks vorhanden"}, 2)
    neu = ohne.rstrip("\n") + "\n"
    if modell:
        neu += ("# >>> nuorb-claude-fallback (scripts/steuerung-claude-fallback.sh)\n"
                f"fallback_providers:\n  - provider: anthropic\n    model: {modell}\n# <<< nuorb-claude-fallback\n")
    if neu != txt:
        shutil.copy2(PFAD, f"{PFAD}.vor-claude-fallback.{time.strftime('%Y%m%d-%H%M%S')}")
        tmp = PFAD + ".neu"
        open(tmp, "w").write(neu)
        os.replace(tmp, PFAD)


def check(live):
    cmd = [HERMES, "fallback", "check", "--json"] + (["--live"] if live else [])
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    try:
        start = p.stdout.index("{")
        return json.loads(p.stdout[start:]), p.returncode
    except ValueError:
        return {"roh": p.stdout[-500:]}, p.returncode


if len(sys.argv) < 2:
    aus({"ok": False, "fehler": "Befehl fehlt: status|setzen|entfernen|pruefen"}, 2)
befehl = sys.argv[1]
if befehl == "status":
    aus({"ok": True, "fallback": aktuell(open(PFAD).read()), "erlaubt": ERLAUBT})
if befehl == "setzen":
    modell = sys.argv[2] if len(sys.argv) > 2 else ""
    if modell not in ERLAUBT:
        aus({"ok": False, "fehler": f"Modell nicht erlaubt: {modell}", "erlaubt": ERLAUBT}, 2)
    schreiben(modell)
    erg, rc = check(False)
    aus({"ok": rc == 0, "fallback": modell, "check": erg}, 0 if rc == 0 else 1)
if befehl == "entfernen":
    schreiben(None)
    aus({"ok": True, "fallback": None})
if befehl == "pruefen":
    erg, rc = check(True)
    aus({"ok": rc == 0, "check": erg}, 0 if rc == 0 else 1)
aus({"ok": False, "fehler": f"unbekannter Befehl {befehl}"}, 2)
