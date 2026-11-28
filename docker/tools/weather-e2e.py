#!/usr/bin/env python3
"""Wetter-Test für das NuOrb-Server-Image, nur gegen den lokalen Wetter-Mock (keine echten Abfragen).

Voraussetzungen: NuOrb-Testcontainer läuft (compose.test.yaml, Ports 19443/19444), Admin-Passwort gesetzt
(z. B. nach e2e-test.py). Ablauf:
  1. Werkzeug und Skill sind nach dem Start registriert, ohne Ort sagt das Werkzeug „nicht eingerichtet“
  2. Mock starten, Ort setzen, MCP-Eintrag mit Mock-Adresse neu registrieren (first_run)
  3. MCP direkt im Container: jetzt, morgen, Woche, Warnungen (DE), Ausland über Open-Meteo
  4. Über Hermes mit Mock-Gehirn: Werkzeug ohne Bestätigungskarte, Antwort mit DWD-Quelle
  5. Aufräumen: Ort, Schlüssel und Zwischenspeicher löschen, Eintrag ohne Mock, Gehirn wie vorher
Aufruf: E2E_PASSWORD=… python3 docker/tools/weather-e2e.py
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("e2e", HIER / "e2e-test.py")
assert spec is not None and spec.loader is not None
e2e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2e)
check, Client = e2e.check, e2e.Client
PY = "/opt/nuorb/venv/bin/python"
CONF = "/opt/data/nuorb/config"
BERLIN = {"name": "Teststadt", "region": "Testland", "lat": 52.0, "lon": 13.0, "country_code": "DE", "timezone": "Europe/Berlin"}


def dexec(c: str, cmd: str, user: str = "hermes", stdin: bytes | None = None, timeout: int = 60, env: dict | None = None) -> str:
    e = [x for k, v in (env or {}).items() for x in ("-e", f"{k}={v}")]
    r = subprocess.run(["docker", "exec", "-i", *e, "-u", user, c, "sh", "-c", cmd], input=stdin, capture_output=True, timeout=timeout)
    return (r.stdout + r.stderr).decode("utf-8", "replace")


def satz(c: str, zeitraum: str, lang: str, mock: str) -> str:
    return dexec(c, f"{PY} -I /opt/nuorb/app/nuorb_weather_mcp.py --satz {zeitraum} {lang}", env={"NUORB_WEATHER_MOCK": mock}).strip()


def setze(c: str, settings: dict) -> None:
    dexec(c, f"umask 077; cat > {CONF}/weather.json; rm -rf /opt/data/nuorb/cache/weather",
          stdin=json.dumps(settings).encode())


def run(app: Client, frage: str) -> tuple[str, list]:
    st, r = app.req("POST", "/api/ask", {"text": frage, "client": "android"})
    if st != 200 or not r.get("run_id"):
        return f"FEHLER {st} {r}", []
    events, answer = [], ""
    resp = app.req("GET", f"/api/runs/{r['run_id']}/events", stream=True, timeout=180)
    for line in resp:
        line = line.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        ev = json.loads(line[5:])
        events.append(ev.get("event"))
        if ev.get("event") == "approval.request":
            app.req("POST", f"/api/runs/{r['run_id']}/approval", {"choice": "deny"})
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
    ap.add_argument("--weather-port", type=int, default=18440)
    ap.add_argument("--mock-port", type=int, default=18437)
    ap.add_argument("--password", default=os.environ.get("E2E_PASSWORD", ""))
    a = ap.parse_args()
    C, mock_url = a.container, f"http://127.0.0.1:{a.weather_port}"
    work = HIER.parent / ".work"
    work.mkdir(exist_ok=True)
    insecure = ssl.create_default_context()
    insecure.check_hostname, insecure.verify_mode = False, ssl.CERT_NONE
    adm = Client(a.admin, insecure)
    adm.headers["X-NuOrb"] = "1"
    st, _ = adm.req("POST", "/api/auth/login", {"password": a.password})
    if not check("Admin-Anmeldung", st == 200):
        return 1

    # ------------------------------------------------ 1. nach dem Start registriert
    cfg = dexec(C, "cat /opt/data/config.yaml")
    block = cfg.split("  wetter:", 1)[-1].split("\n  ", 1)[0] if "  wetter:" in cfg else ""
    check("MCP-Eintrag wetter registriert (nur lesend, trust full)", "nuorb_weather_mcp.py" in cfg and "trust: full" in
          cfg.split("  wetter:", 1)[-1][:600], block[:80])
    check("Skill nuorb/wetter installiert", "name: wetter" in dexec(C, "cat /opt/data/skills/nuorb/wetter/SKILL.md"))
    dexec(C, f"rm -f {CONF}/weather.json {CONF}/weather.env")
    out = dexec(C, f"{PY} -I /opt/nuorb/app/nuorb_weather_mcp.py --satz jetzt de")
    check("Ohne Ort: ehrlicher Hinweis", "noch nicht eingerichtet" in out, out.strip()[:90])

    wlog = Path(tempfile.mkdtemp(prefix="wx-mock-", dir=str(work))) / "weather.log"
    wmock = None
    with socket.socket() as so:
        frei = so.connect_ex(("127.0.0.1", a.weather_port)) != 0
    if frei:
        wmock = subprocess.Popen([sys.executable, str(HIER / "mock-weather.py"), str(a.weather_port)], stdout=open(wlog, "w"),
                                 stderr=subprocess.STDOUT)
    else:
        wlog = work / "ci-weather.log"   # von ci-e2e.sh gestartet
    llm_log = Path(tempfile.mkdtemp(prefix="wx-llm-", dir=str(work))) / "mock.log"
    llm = subprocess.Popen([sys.executable, str(HIER / "mock-llm.py"), str(a.mock_port)], stdout=open(llm_log, "w"),
                           stderr=subprocess.STDOUT)
    app = Client(a.ui, insecure)
    _, setup0 = adm.req("GET", "/api/setup")
    old_url, model = setup0.get("ollama_url", ""), setup0.get("ollama_model", "")
    try:
        time.sleep(1.5)
        # ------------------------------------------------ Verwaltung „Wetter“ (Abfragen laufen im Admin gegen den Mock)
        st, d = adm.req("GET", "/api/weather")
        check("Verwaltung: Wetter ohne Ort", st == 200 and d.get("place") is None and
              "Quelle: Deutscher Wetterdienst" in [x.get("notice") for x in d.get("credits", [])], str(d)[:90])
        ohne = Client(a.admin, insecure)
        ohne.cookies = dict(adm.cookies)   # angemeldet, aber ohne X-NuOrb
        st, _ = ohne.req("POST", "/api/weather/search", {"query": "Teststadt"})
        check("Verwaltung: POST ohne X-NuOrb abgelehnt (CSRF)", st == 403, str(st))
        st, html = adm.req("GET", "/static/docker/wetter.html")
        st2, js = adm.req("GET", "/static/docker/admin-extra.js")
        check("Verwaltung: Seite Wetter ausgeliefert und verlinkt", st == 200 and b"wetter.js" in html and st2 == 200
              and b"wetter.html" in js)
        st, d = adm.req("POST", "/api/weather/search", {"query": "Teststadt"})
        hits = d.get("results") or []
        check("Verwaltung: Ortssuche über den Server", st == 200 and hits and hits[0].get("name") == "Teststadt", str(d)[:90])
        st, d = adm.req("POST", "/api/weather/place", {"place": hits[0] if hits else {}})
        check("Verwaltung: Ort gespeichert, DWD automatisch", st == 200 and d.get("effective") == "dwd", str(d)[:90])
        st, d = adm.req("GET", "/api/weather/station")
        check("Verwaltung: nächste DWD-Station mit Entfernung", st == 200 and d.get("station") == "Teststation"
              and d.get("distance_km") == 3.2, str(d)[:90])
        st, d = adm.req("POST", "/api/weather/search", {"query": "10115"})
        check("Verwaltung: reine Postleitzahl ergibt nur den Hinweis auf den Ortsnamen", st == 400
              and any(t in str(d) for t in ("Ortsnamen", "name of the place")), str(d)[:90])
        st, d = adm.req("POST", "/api/weather/keys", {"openmeteo": "e2e-admin-key-98765"})
        check("Verwaltung: Schlüssel nur maskiert", st == 200 and "e2e-admin-key" not in json.dumps(d)
              and str((d.get("keys") or {}).get("openmeteo", "")).endswith("8765"), str(d.get("keys"))[:60])
        st, d = adm.req("POST", "/api/weather/keys", {"openmeteo": ""})
        st, d = adm.req("POST", "/api/weather/test", {"zeitraum": "jetzt", "lang": "de"})
        check("Verwaltung: Test-Knopf liefert den Sprechsatz", st == 200 and str(d.get("text", "")).startswith("Laut Deutschem Wetterdienst"),
              str(d)[:100])
        st, d = adm.req("GET", "/api/about")
        check("Über: Quellenhinweise Wetter", st == 200 and any(w.get("id") == "dwd" for w in d.get("weather", [])))

        # ------------------------------------------------ 2./3. MCP direkt
        setze(C, BERLIN)
        jetzt = satz(C, "jetzt", "de", mock_url)
        check("Jetzt: DWD-Station mit Entfernung, Zahlen ausgeschrieben",
              jetzt.startswith("Laut Deutschem Wetterdienst, Station Teststation in drei Kilometern Entfernung: vier Komma sechs Grad"),
              jetzt[:120])
        check("Jetzt: amtliche Warnung unverändert", "Amtliche WARNUNG vor WINDBÖEN" in jetzt, jetzt[-90:])
        check("Ohne Ziffern, Gedankenstriche und Semikolons", not any(ch.isdigit() or ch in "\u2013\u2014;" for ch in jetzt))
        morgen = satz(C, "morgen", "en", mock_url)
        check("Morgen (EN)", morgen.startswith("Tomorrow according to the German Weather Service: rain"), morgen[:100])
        woche = satz(C, "woche", "de", mock_url)
        check("Woche: sieben Tage", woche.startswith("Die nächsten Tage laut Deutschem Wetterdienst.") and woche.count(" bis ") == 7,
              woche[:100])
        warn = satz(C, "warnungen", "de", mock_url)
        check("Warnungen mit Gültigkeit", warn.startswith("Der Deutsche Wetterdienst meldet: Amtliche WARNUNG vor WINDBÖEN, gültig von"),
              warn[:110])
        setze(C, {**BERLIN, "name": "Wien", "country_code": "AT", "timezone": "Europe/Vienna"})
        aus = satz(C, "jetzt", "de", mock_url)
        check("Ausland automatisch über Open-Meteo", aus.startswith("Laut Open-Meteo für Wien: achtzehn Komma fünf Grad"), aus[:90])
        log = [json.loads(z) for z in wlog.read_text().splitlines() if z.startswith("{")]
        check("Alle Abfragen mit NuOrb-User-Agent, Koordinaten gerundet", log and all(e["ua"].startswith("NuOrb") for e in log)
              and all("52.0" in e["query"] or "52.00" in e["query"] or not e["query"] for e in log if "lat" in e["query"]),
              f"{len(log)} Abfragen")
        setze(C, BERLIN)

        # ------------------------------------------------ 4. über Hermes mit Mock-Gehirn
        out = dexec(C, "grep -A6 '  wetter:' /opt/data/config.yaml | grep -c NUORB_WEATHER_MOCK")
        dexec(C, "hermes config set tools.tool_search.enabled false >/dev/null 2>&1; true")
        st, d = adm.req("POST", "/api/setup/apply", {"mode": "local", "ollama_url": f"127.0.0.1:{a.mock_port}",
                                                    "ollama_model": model, "context": 65536, "remote_model": ""}, timeout=150)
        check("Gehirn auf Werkzeug-Mock umgestellt, MCP-Eintrag nutzt den Wetter-Mock", st == 200 and out.strip() == "1",
              f"{str(d)[:60]} {out.strip()[:20]}")
        st, pc = adm.req("POST", "/api/pairing/new", {})
        st, d = app.req("POST", "/api/pair", {"code": pc.get("code", ""), "device": "Wetter-Test", "platform": "android"})
        app.headers["Authorization"] = f"Bearer {d.get('token', '')}"
        for _ in range(40):
            st, s = app.req("GET", "/api/status")
            if s.get("hermes") and s.get("brain_ok"):
                break
            time.sleep(3)
        time.sleep(15)  # MCP-Server starten im Gateway nach dem Neustart
        ans, ev = run(app, 'Wie ist das Wetter? [[tool:wetter__wetter {"zeitraum":"jetzt"}]]')
        check("Über Hermes ohne Bestätigungskarte, Antwort mit DWD-Quelle", "approval.request" not in ev and ans.startswith("Erledigt:")
              and "Laut Deutschem Wetterdienst" in ans, f"{ans[:140]!r} {ev[-4:]}")
    finally:
        llm.terminate()
        app.req("POST", "/api/unpair")
        adm.req("POST", "/api/setup/apply", {"mode": "local", "ollama_url": old_url, "ollama_model": model,
                                            "context": 65536, "remote_model": ""}, timeout=150)
        dexec(C, f"rm -rf {CONF}/weather.json {CONF}/weather.env /opt/data/nuorb/cache/weather")
        check("Aufgeräumt: Ort und Schlüssel gelöscht",
              "nicht eingerichtet" in dexec(C, f"{PY} -I /opt/nuorb/app/nuorb_weather_mcp.py --satz jetzt de"))
        if wmock:
            wmock.terminate()

    bad = [n for n, ok, _ in e2e.results if not ok]
    print(f"\n{len(e2e.results) - len(bad)}/{len(e2e.results)} Wetter-Prüfungen bestanden." + (f" Fehlgeschlagen: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
