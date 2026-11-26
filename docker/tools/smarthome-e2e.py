#!/usr/bin/env python3
"""Smart-Home-Test für das NuOrb-Server-Image gegen echte Home-Assistant- und ioBroker-Testinstanzen.

Voraussetzungen (alles lokal, nur 127.0.0.1):
  * NuOrb-Testcontainer läuft (compose.test.yaml, Ports 19443/19444), Admin-Passwort gesetzt (z. B. nach e2e-test.py)
  * HA + ioBroker laufen und sind eingerichtet: scripts/backend-smarthome-test.sh up && … einrichten
    -> Zugangsdatei ~/.cache/nuorb-smarthome-test/smarthome.env
Ablauf: Zugang in den Container (600), NUORB_SMARTHOME=1, MCP direkt (lesen), dann über Hermes mit einem Mock-Gehirn,
das gezielt Werkzeuge aufruft: Lesen ohne Rückfrage, Schalten mit Bestätigungskarte (ablehnen -> nichts passiert,
freigeben -> HA/ioBroker schalten). Danach alles zurück (Smart Home aus, Zugang gelöscht, Gehirn wieder wie vorher).
Aufruf: E2E_PASSWORD=… python3 docker/tools/smarthome-e2e.py [--zugang ~/.cache/nuorb-smarthome-test/smarthome.env]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HIER = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("e2e", HIER / "e2e-test.py")
e2e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2e)
check, Client = e2e.check, e2e.Client


def dexec(c: str, cmd: str, user: str = "hermes", stdin: bytes | None = None, timeout: int = 60) -> str:
    r = subprocess.run(["docker", "exec", "-i", "-u", user, c, "sh", "-c", cmd], input=stdin, capture_output=True, timeout=timeout)
    return (r.stdout + r.stderr).decode("utf-8", "replace")


def env_datei(p: Path) -> dict:
    return dict(l.split("=", 1) for l in p.read_text().splitlines() if "=" in l and not l.startswith("#"))


def ha_state(z: dict, eid: str) -> str:
    r = urllib.request.Request(z["HA_URL"] + "/api/states/" + eid, headers={"Authorization": "Bearer " + z["HA_TOKEN"]})
    return json.loads(urllib.request.urlopen(r, timeout=10).read())["state"]


def ha_call(z: dict, domain: str, service: str, eid: str) -> None:
    r = urllib.request.Request(f"{z['HA_URL']}/api/services/{domain}/{service}", data=json.dumps({"entity_id": eid}).encode(),
                               headers={"Authorization": "Bearer " + z["HA_TOKEN"], "Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(r, timeout=10).read()


def iob_val(z: dict, oid: str):
    import base64
    auth = base64.b64encode(f"{z['IOB_USER']}:{z['IOB_PASS']}".encode()).decode()
    r = urllib.request.Request(f"{z['IOB_URL']}/v1/state/{oid}", headers={"Authorization": "Basic " + auth})
    return json.loads(urllib.request.urlopen(r, timeout=10).read()).get("val")


def mcp(c: str, teil: str, calls: list[tuple[str, dict]]) -> list:
    """MCP-Server im Container über stdio ansprechen: initialize, tools/list, dann tools/call."""
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "e2e", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    for i, (name, args) in enumerate(calls, 3):
        msgs.append({"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}})
    out = dexec(c, f"/opt/jarvis/venv/bin/python -I /opt/jarvis/smarthome/smarthome_mcp.py {teil} "
                   f"--zugang /opt/data/smarthome.env",
                stdin=("\n".join(json.dumps(m) for m in msgs) + "\n").encode())
    res = {}
    for line in out.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if "id" in d:
            res[d["id"]] = d
    return [res.get(i) for i in range(2, 3 + len(calls))]


def text_of(r) -> str:
    try:
        return " ".join(x.get("text", "") for x in r["result"]["content"])
    except (TypeError, KeyError):
        return str(r)[:200]


def run(app: Client, frage: str, entscheidung: str | None) -> tuple[str, list]:
    """Frage stellen; bei einer Bestätigungskarte mit once/deny antworten. Liefert (Antwort, Ereignisse)."""
    st, r = app.req("POST", "/api/ask", {"text": frage, "client": "android"})
    if st != 200 or not r.get("run_id"):
        return f"FEHLER {st} {r}", []
    rid, events, answer = r["run_id"], [], ""
    resp = app.req("GET", f"/api/runs/{rid}/events", stream=True, timeout=180)
    for line in resp:
        line = line.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        ev = json.loads(line[5:])
        events.append(ev.get("event"))
        if ev.get("event") == "approval.request":
            st2, d2 = app.req("POST", f"/api/runs/{rid}/approval", {"choice": entscheidung or "deny"})
            events.append(f"approval->{entscheidung or 'deny'}:{st2}")
        if ev.get("event") == "run.completed":
            answer = ev.get("output") or ""
            break
        if ev.get("event") in ("run.failed", "run.cancelled"):
            answer = "FEHLER " + str(ev)[:300]
            break
    return answer, events


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="https://127.0.0.1:19443")
    ap.add_argument("--admin", default="https://127.0.0.1:19444")
    ap.add_argument("--container", default="nuorb-test")
    ap.add_argument("--zugang", default=str(Path.home() / ".cache/nuorb-smarthome-test/smarthome.env"))
    ap.add_argument("--mock-port", type=int, default=18436)
    ap.add_argument("--password", default=os.environ.get("E2E_PASSWORD", ""))
    a = ap.parse_args()
    C, zpfad = a.container, Path(a.zugang)
    z = env_datei(zpfad)
    insecure = ssl.create_default_context()
    insecure.check_hostname, insecure.verify_mode = False, ssl.CERT_NONE
    adm = Client(a.admin, insecure); adm.headers["X-Jarvis"] = "1"
    st, _ = adm.req("POST", "/api/auth/login", {"password": a.password})
    if not check("Admin-Anmeldung", st == 200):
        return 1

    # ------------------------------------------------ Standard: aus
    cfg = dexec(C, "cat /opt/data/config.yaml")
    check("Smart Home ist standardmäßig aus", "smarthome_mcp.py" in cfg and "enabled: true" not in
          cfg.split("smarthome:", 1)[-1].split("trust:", 1)[0])
    check("Skill smart-home/smarthome installiert", "name: smarthome" in dexec(C, "cat /opt/data/skills/smart-home/smarthome/SKILL.md"))

    # ------------------------------------------------ Zugang + Einschalten
    dexec(C, "umask 077; cat > /opt/data/smarthome.env", stdin=zpfad.read_bytes())
    out = dexec(C, ". /opt/jarvis/bin/jarvis-env; NUORB_SMARTHOME=1 $PY -I /opt/jarvis/app/first_run.py 2>&1 | grep -i smart")
    cfg = dexec(C, "cat /opt/data/config.yaml")
    an = [b.split("trust:", 1)[0] for b in cfg.split("  smarthome")[1:]]
    check("NUORB_SMARTHOME=1 schaltet beide Einträge ein", len(an) >= 2 and all("enabled: true" in b for b in an[:2]), out.strip()[:120])
    check("Zugangsdatei nur für den Besitzer (600)", dexec(C, "stat -c %a /opt/data/smarthome.env").strip() == "600")

    # ------------------------------------------------ MCP direkt gegen HA und ioBroker
    tl, raeume, geraete = mcp(C, "lesen", [("raeume", {}), ("geraete", {"art": "licht"})])
    namen = [t["name"] for t in (tl or {}).get("result", {}).get("tools", [])]
    check("MCP lesen: Werkzeuge geraete/zustand/raeume", {"geraete", "zustand", "raeume"} <= set(namen), str(namen))
    check("MCP lesen: Räume aus HA und ioBroker", "Küche" in text_of(raeume) and "Esszimmer" in text_of(raeume), text_of(raeume)[:140])
    check("MCP lesen: Lichter aus HA und ioBroker", "Küchenlicht" in text_of(geraete) and "Esstischlampe" in text_of(geraete),
          text_of(geraete)[:140])
    tl2, = mcp(C, "schalten", [])
    check("MCP schalten: Werkzeuge schalten/szene", {"schalten", "szene"} <= {t["name"] for t in (tl2 or {}).get("result", {}).get("tools", [])})

    # ------------------------------------------------ Über Hermes mit Mock-Gehirn (ruft Werkzeuge gezielt auf)
    _, setup0 = adm.req("GET", "/api/setup")
    old_url, model = setup0.get("ollama_url", ""), setup0.get("ollama_model", "")
    log = Path(tempfile.mkdtemp(prefix="sh-mock-", dir=str(HIER.parent / ".work"))) / "mock.log"
    mock = subprocess.Popen([sys.executable, str(HIER / "mock-llm.py"), str(a.mock_port)], stdout=open(log, "w"), stderr=subprocess.STDOUT)
    app = Client(a.ui, insecure)
    try:
        time.sleep(1.5)
        # Werkzeugsuche aus (wie für lokale Modelle empfohlen), damit die MCP-Werkzeuge direkt im Angebot sind
        dexec(C, "hermes config set tools.tool_search.enabled false >/dev/null 2>&1; true")
        st, d = adm.req("POST", "/api/setup/apply", {"mode": "local", "ollama_url": f"127.0.0.1:{a.mock_port}",
                                                    "ollama_model": model, "context": 65536, "remote_model": ""}, timeout=150)
        check("Gehirn auf Werkzeug-Mock umgestellt (Gateway lädt die MCP-Server neu)", st == 200, str(d)[:80])
        st, pc = adm.req("POST", "/api/pairing/new", {})
        st, d = app.req("POST", "/api/pair", {"code": pc.get("code", ""), "device": "SmartHome-Test", "platform": "android"})
        app.headers["Authorization"] = f"Bearer {d.get('token', '')}"
        for _ in range(40):
            st, s = app.req("GET", "/api/status")
            if s.get("hermes") and s.get("brain_ok"):
                break
            time.sleep(3)
        time.sleep(15)  # MCP-Server starten im Gateway nach dem Neustart

        ans, ev = run(app, 'Welche Lichter sind an? [[tool:smarthome__geraete {"art":"licht"}]]', None)
        check("Lesen über Hermes ohne Bestätigungskarte", "approval.request" not in ev and ans.startswith("Erledigt:")
              and 'source="mcp__smarthome__geraete"' in ans, f"{ans[:120]!r} {ev[-4:]}")

        ha_call(z, "light", "turn_on", "light.kitchen_lights")
        ans, ev = run(app, 'Mach das Küchenlicht aus. [[tool:smarthome_schalten__schalten {"name":"Küchenlicht","aktion":"aus"}]]', "deny")
        check("Schalten zeigt eine Bestätigungskarte", "approval.request" in ev, str([e for e in ev if e and "approval" in e]))
        check("Abgelehnt: Küchenlicht bleibt an (HA)", ha_state(z, "light.kitchen_lights") == "on", ans[:80])

        ans, ev = run(app, 'Mach das Küchenlicht aus. [[tool:smarthome_schalten__schalten {"name":"Küchenlicht","aktion":"aus"}]]', "once")
        time.sleep(1)
        check("Freigegeben: Küchenlicht ist aus (HA)", "approval.request" in ev and ha_state(z, "light.kitchen_lights") == "off",
              f"{ans[:100]!r}")

        before = iob_val(z, "0_userdata.0.nuorbtest.esstischlampe")
        ziel = "aus" if before else "an"
        ans, ev = run(app, f'Esstischlampe {ziel}. [[tool:smarthome_schalten__schalten {{"name":"Esstischlampe","aktion":"{ziel}"}}]]', "once")
        time.sleep(1)
        after = iob_val(z, "0_userdata.0.nuorbtest.esstischlampe")
        check("Freigegeben: Esstischlampe geschaltet (ioBroker)", "approval.request" in ev and bool(after) != bool(before),
              f"{before} -> {after} {ans[:80]!r}")
    finally:
        mock.terminate()
        app.req("POST", "/api/unpair")
        adm.req("POST", "/api/setup/apply", {"mode": "local", "ollama_url": old_url, "ollama_model": model,
                                            "context": 65536, "remote_model": ""}, timeout=150)
        out = dexec(C, "rm -f /opt/data/smarthome.env; . /opt/jarvis/bin/jarvis-env; "
                       "NUORB_SMARTHOME=0 $PY -I /opt/jarvis/app/first_run.py 2>&1 | grep -i smart")
        cfg = dexec(C, "cat /opt/data/config.yaml")
        an = [b.split("trust:", 1)[0] for b in cfg.split("  smarthome")[1:]]
        check("Aufgeräumt: Smart Home wieder aus, Zugang gelöscht", an and not any("enabled: true" in b for b in an[:2]), out.strip()[:100])

    bad = [n for n, ok, _ in e2e.results if not ok]
    print(f"\n{len(e2e.results) - len(bad)}/{len(e2e.results)} Smart-Home-Prüfungen bestanden." + (f" Fehlgeschlagen: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
