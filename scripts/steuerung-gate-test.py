#!/usr/bin/env python3
"""Prueft die Bestaetigungspflicht eines Hermes-Werkzeugs ueber die Runs-API (wie jarvis-ui).
Startet einen Run, zeigt die approval.request-Daten und antwortet mit 'deny' (Standard) -> es passiert nichts.
Aufruf auf jarvis als jarvis:  python3 steuerung-gate-test.py "Frag Claude: ..." [deny|once]
Der API-Schluessel wird aus ~/.hermes/.env gelesen und nie ausgegeben."""
import json, os, sys, urllib.request

frage = sys.argv[1]
wahl = sys.argv[2] if len(sys.argv) > 2 else "deny"
key = next(l.split("=", 1)[1].strip() for l in open(os.path.expanduser("~/.hermes/.env")) if l.startswith("API_SERVER_KEY="))
BASE = "http://127.0.0.1:8642"
H = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def post(pfad, daten):
    r = urllib.request.Request(BASE + pfad, data=json.dumps(daten).encode(), headers=H, method="POST")
    with urllib.request.urlopen(r, timeout=30) as a:
        return a.status, json.loads(a.read() or b"{}")


koerper = {"input": frage, "session_id": "gate-test-" + os.urandom(4).hex()}
if os.environ.get("WIE_UI"):  # wie jarvis-ui: Denken aus + kurze Persona
    koerper["instructions"] = open(os.environ["WIE_UI"]).read() if os.path.isfile(os.environ["WIE_UI"]) else "Du bist JARVIS. Antworte kurz."
    koerper["model_options"] = {"reasoning": {"enabled": False}}
_, run = post("/v1/runs", koerper)
rid = run["run_id"]
print("run", rid)
req = urllib.request.Request(f"{BASE}/v1/runs/{rid}/events", headers=H)
with urllib.request.urlopen(req, timeout=400) as s:
    for roh in s:
        zeile = roh.decode().strip()
        if not zeile.startswith("data:"):
            continue
        ev = json.loads(zeile[5:])
        typ = ev.get("event") or ev.get("type")
        if typ in ("tool.started", "tool.completed"):
            print(typ, ev.get("tool"), "error=", ev.get("error"), (ev.get("preview") or "")[:300])
        elif typ == "approval.request":
            print("APPROVAL title:", ev.get("title"))
            print("  command:", (ev.get("command") or "")[:600])
            print("  description:", ev.get("description"))
            print("  choices:", ev.get("choices"), "pattern_key:", ev.get("pattern_key"))
            rid_ = ev.get("request_id") or ev.get("prompt_id")
            st, res = post(f"/v1/runs/{rid}/approval", {"request_id": rid_, "execution_generation": ev.get("execution_generation"), "choice": wahl})
            print("  ->", wahl, st, res)
        elif typ in ("run.completed", "run.failed", "run.cancelled"):
            out = ev.get("output") or ev.get("final_response") or ev.get("error") or ""
            print(typ, str(out)[:800])
            break
