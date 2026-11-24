#!/usr/bin/env python3
"""NuOrb: MCP-Server (stdio, nur Standardbibliothek) für Name und Kennenlernen.

Werkzeuge für Hermes:
  name_setzen {name}         – „Ab jetzt heißt du X“ (assistant_name)
  nutzername_setzen {name}   – der Nutzer nennt seinen Namen (ui.json user_name + Gedächtnis USER.md)
  kennenlernen_fertig {}     – Nutzer ist mit dem Namen zufrieden, Begrüßung abgeschlossen
Gespeichert wird über die interne Schnittstelle des Admin-Panels (Loopback + internes Token, mit Sicherung).
"""
import json
import os
import ssl
import sys
import urllib.request

ADMIN_URL = os.environ.get("ADMIN_URL", "https://127.0.0.1:8444")
TOKEN_FILE = os.environ.get("ADMIN_TOKEN_FILE", "/opt/data/jarvis/config/internal.token")
NAME = {"type": "string", "minLength": 1, "maxLength": 40}

TOOLS = [
    {"name": "name_setzen", "title": "Eigenen Namen ändern",
     "description": "Setzt den Namen, mit dem der Nutzer den Assistenten anspricht, z. B. nach 'Ab jetzt heißt du Max'. "
                    "Nur aufrufen, wenn der Nutzer das ausdrücklich will. Danach den neuen Namen kurz bestätigen.",
     "inputSchema": {"type": "object", "properties": {"name": NAME}, "required": ["name"], "additionalProperties": False},
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}},
    {"name": "nutzername_setzen", "title": "Namen des Nutzers merken",
     "description": "Merkt sich, wie der Nutzer heißt (wenn er es sagt, z. B. 'Ich heiße Anna').",
     "inputSchema": {"type": "object", "properties": {"name": NAME}, "required": ["name"], "additionalProperties": False},
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}},
    {"name": "kennenlernen_fertig", "title": "Begrüßung abschließen",
     "description": "Schließt das erste Kennenlernen ab, wenn der Nutzer mit dem Namen zufrieden ist.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}},
]


def admin(payload: dict) -> tuple[bool, str]:
    try:
        token = open(TOKEN_FILE, encoding="utf-8").read().strip()
    except OSError:
        return False, "Interne Schnittstelle nicht bereit."
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE  # nur Loopback im Container
    req = urllib.request.Request(ADMIN_URL + "/internal/assistant", data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Jarvis-Internal": token})
    try:
        with urllib.request.urlopen(req, context=ctx if ADMIN_URL.startswith("https") else None, timeout=10) as r:
            d = json.loads(r.read() or b"{}")
            return True, json.dumps(d, ensure_ascii=False)
    except urllib.error.HTTPError as e:
        return False, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:
        return False, f"{e.__class__.__name__}: {e}"


def call(name: str, args: dict) -> tuple[str, bool]:
    if name == "name_setzen":
        ok, out = admin({"assistant_name": str(args.get("name", "")).strip(), "onboarded": True, "source": "sprache"})
        return (f"Name gespeichert: {args.get('name')}. Bestätige ihn kurz." if ok else f"Fehler: {out}"), not ok
    if name == "nutzername_setzen":
        ok, out = admin({"user_name": str(args.get("name", "")).strip(), "source": "sprache"})
        return (f"Gemerkt: Der Nutzer heißt {args.get('name')}." if ok else f"Fehler: {out}"), not ok
    if name == "kennenlernen_fertig":
        ok, out = admin({"onboarded": True, "source": "sprache"})
        return ("Kennenlernen abgeschlossen." if ok else f"Fehler: {out}"), not ok
    return f"Unbekanntes Werkzeug: {name}", True


def send(mid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": mid}
    msg["error" if error is not None else "result"] = error if error is not None else result
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        try:
            req = json.loads(line)
        except ValueError:
            continue
        mid, method, params = req.get("id"), req.get("method", ""), req.get("params") or {}
        if mid is None:
            continue
        if method == "initialize":
            send(mid, {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                       "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": "nuorb", "version": "1.0.0"}})
        elif method == "ping":
            send(mid, {})
        elif method == "tools/list":
            send(mid, {"tools": TOOLS})
        elif method == "tools/call":
            text, err = call(params.get("name"), params.get("arguments") or {})
            send(mid, {"content": [{"type": "text", "text": text}], "isError": err})
        else:
            send(mid, error={"code": -32601, "message": f"Methode nicht unterstützt: {method}"})


if __name__ == "__main__":
    main()
