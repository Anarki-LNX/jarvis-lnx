#!/usr/bin/env python3
"""Ende-zu-Ende-Test des Docker-Servers – spielt den Ablauf einer App durch.

  1. Admin: Einrichtungscode (aus dem Container) -> Passwort setzen -> Anmeldung
  2. Admin: Kopplungscode erzeugen (QR-Inhalt jarvislnx://pair?...)
  3. App: /jarvis-ca.crt holen, SHA-256 mit dem Fingerabdruck aus dem QR vergleichen, ab dann TLS gegen diese CA prüfen
  4. App: ohne Token -> 401; koppeln -> Token; Status; Frage stellen (Run + SSE bis run.completed)
  5. Sprache: TTS liefert WAV, das WAV zurück durch die Spracherkennung (wenn die Modelle schon geladen sind)
  6. Browser: Startseite ohne Kopplung = Kopplungsseite, falscher Code = 403

Aufruf: python3 docker/tools/e2e-test.py --ui https://127.0.0.1:18443 --admin https://127.0.0.1:18444 \
           --setup-code XXXX-XXXX-XXXX   (oder --password, wenn schon eingerichtet)
Nichts wird außerhalb des Test-Containers verändert. Das Passwort ist ein Wegwerf-Testwert.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

OK, FAIL = "\033[32mOK\033[0m", "\033[31mFEHLER\033[0m"
results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, info: str = "") -> bool:
    results.append((name, cond, info))
    print(f"[{OK if cond else FAIL}] {name}{' – ' + info if info else ''}", flush=True)
    return cond


class Client:
    def __init__(self, base: str, ctx: ssl.SSLContext):
        self.base, self.ctx, self.cookies, self.headers = base.rstrip("/"), ctx, {}, {}

    def req(self, method: str, path: str, body=None, raw: bytes | None = None, ctype: str | None = None,
            timeout: float = 30, stream: bool = False):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = dict(self.headers)
        if data is not None:
            h["Content-Type"] = ctype or "application/json"
        if self.cookies:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        h["Origin"] = self.base
        r = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            resp = urllib.request.urlopen(r, context=self.ctx, timeout=timeout)
        except urllib.error.HTTPError as e:
            resp = e
        for c in resp.headers.get_all("Set-Cookie") or []:
            k, v = c.split(";", 1)[0].split("=", 1)
            self.cookies[k] = v
        if stream:
            return resp
        b = resp.read()
        try:
            return resp.status, json.loads(b)
        except ValueError:
            return resp.status, b


def multipart(field: str, filename: str, data: bytes, ctype: str) -> tuple[bytes, str]:
    bd = "----jarvis" + secrets.token_hex(8)
    body = (f"--{bd}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode() + data + f"\r\n--{bd}--\r\n".encode()
    return body, f"multipart/form-data; boundary={bd}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="https://127.0.0.1:18443")
    ap.add_argument("--admin", default="https://127.0.0.1:18444")
    ap.add_argument("--setup-code")
    ap.add_argument("--password", default=os.environ.get("E2E_PASSWORD", "Test-" + secrets.token_hex(8)))
    ap.add_argument("--question", default="Hallo Jarvis, wie geht es dir?")
    a = ap.parse_args()

    insecure = ssl.create_default_context()
    insecure.check_hostname, insecure.verify_mode = False, ssl.CERT_NONE

    # ---------------------------------------------------------------- Admin
    adm = Client(a.admin, insecure)
    adm.headers["X-Jarvis"] = "1"
    st, d = adm.req("GET", "/api/auth/state")
    check("Admin erreichbar", st == 200, f"configured={d.get('configured')}")
    if not d.get("configured"):
        check("Einrichtungshinweis für Docker", "docker compose" in (d.get("setupHint") or ""), d.get("setupHint", "")[:60])
        st, d = adm.req("POST", "/api/auth/setup", {"code": a.setup_code, "password": a.password})
        check("Passwort mit Einrichtungscode gesetzt", st == 200, str(d)[:80])
    else:
        st, d = adm.req("POST", "/api/auth/login", {"password": a.password})
        check("Admin-Anmeldung", st == 200, str(d)[:80])
    st, s = adm.req("GET", "/api/setup")
    check("Einrichtung abrufbar", st == 200, f"done={s.get('done')} brain={s.get('brain')} lang={s.get('lang')}")
    st, html = adm.req("GET", "/")
    check("Admin-Startseite lädt Zusatz-Skript", st == 200 and b"admin-extra.js" in html)
    st, dev = adm.req("GET", "/api/services")
    check("Dienste-Status über s6", st == 200, ", ".join(f"{u['id']}={u['active']}" for u in dev.get("units", [])))
    st, pc = adm.req("POST", "/api/pairing/new", {})
    check("Kopplungscode erzeugt", st == 200 and len(pc.get("code", "")) == 9, pc.get("uri", "")[:90])
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(pc.get("uri", "")).query))
    check("QR enthält URL, Fingerabdruck, Code", all(q.get(k) for k in ("url", "fp", "code")), json.dumps(q)[:120])

    # ---------------------------------------------------------------- App: Vertrauen über Fingerabdruck
    st, ca_pem = Client(a.ui, insecure).req("GET", "/jarvis-ca.crt")
    der = ssl.PEM_cert_to_DER_cert(ca_pem.decode())
    fp = hashlib.sha256(der).hexdigest().upper()
    check("CA-Fingerabdruck passt zum QR-Code", fp == q.get("fp"), fp[:16] + "…")
    pinned = ssl.create_default_context(cadata=ca_pem.decode())
    pinned.check_hostname = True
    app = Client(a.ui, pinned)
    try:
        st, info = app.req("GET", "/api/info")
        check("TLS gegen die Heim-CA (Name im Zertifikat)", st == 200, json.dumps(info)[:120])
    except Exception as exc:
        check("TLS gegen die Heim-CA (Name im Zertifikat)", False, str(exc)[:120])
        app = Client(a.ui, insecure)
    st, _ = app.req("GET", "/api/status")
    check("Ohne Token: 401", st == 401)
    st, d = app.req("POST", "/api/pair", {"code": "AAAA-BBBB", "device": "Test", "platform": "android"})
    check("Falscher Code: 403", st == 403)
    st, d = app.req("POST", "/api/pair", {"code": pc["code"], "device": "E2E-Test", "platform": "android"})
    check("Koppeln mit Einmal-Code", st == 200 and bool(d.get("token")), f"device_id={d.get('device_id')}")
    token = d.get("token", "")
    st, d2 = app.req("POST", "/api/pair", {"code": pc["code"], "device": "Zweitversuch", "platform": "android"})
    check("Code ist einmalig", st == 403)
    app.headers["Authorization"] = f"Bearer {token}"

    st, s = app.req("GET", "/api/status")
    check("Status mit Token", st == 200, f"hermes={s.get('hermes')} brain={s.get('brain')} stt={s.get('stt')} tts={s.get('tts')} lang={s.get('lang')}")
    for _ in range(30):  # Gateway braucht nach dem Start etwas
        if s.get("hermes"):
            break
        time.sleep(4)
        st, s = app.req("GET", "/api/status")
    check("Hermes läuft", bool(s.get("hermes")))
    check("Gehirn (Ollama/Mock) erreichbar", bool(s.get("brain_ok")), f"mode={s.get('brain_mode')} model={s.get('brain_model')}")

    # ---------------------------------------------------------------- Frage
    t0 = time.time()
    st, r = app.req("POST", "/api/ask", {"text": a.question, "client": "android"})
    check("Frage gestartet", st == 200 and bool(r.get("run_id")), str(r)[:100])
    answer, events = "", []
    if r.get("run_id"):
        resp = app.req("GET", f"/api/runs/{r['run_id']}/events", stream=True, timeout=180)
        for line in resp:
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            ev = json.loads(line[5:])
            events.append(ev.get("event"))
            if ev.get("event") == "run.completed":
                answer = ev.get("output") or ""
                break
            if ev.get("event") in ("run.failed", "run.cancelled"):
                answer = "FEHLER " + str(ev)[:300]
                break
    check("Antwort vom Gehirn", bool(answer) and not answer.startswith("FEHLER"),
          f"{time.time() - t0:.1f} s: {answer[:120]!r} (Ereignisse: {', '.join(dict.fromkeys(e for e in events if e))})")

    # ---------------------------------------------------------------- Sprache
    st, wav = app.req("POST", "/api/tts", {"text": "Guten Abend. Alle Systeme laufen."}, timeout=60)
    tts_ok = st == 200 and isinstance(wav, bytes) and wav[:4] == b"RIFF"
    check("Sprachausgabe (Piper) liefert WAV", tts_ok, f"{len(wav) if isinstance(wav, bytes) else wav} Bytes")
    if tts_ok:
        body, ct = multipart("audio", "test.wav", wav, "audio/wav")
        st, t = app.req("POST", "/api/stt", raw=body, ctype=ct, timeout=60)
        check("Spracherkennung (Parakeet) erkennt TTS-Satz", st == 200 and "systeme" in str(t.get("text", "")).lower(),
              str(t)[:100])

    # ---------------------------------------------------------------- Browser
    br = Client(a.ui, insecure)
    st, page = br.req("GET", "/")
    check("Browser ohne Kopplung: 401 mit Kopplungsseite", st == 401 and b"pair.js" in page)
    st, _ = br.req("GET", "/app.js")
    check("Dateien der Oberfläche nur gekoppelt (401)", st == 401)
    st, _ = br.req("GET", "/tokens.css")
    check("Kopplungsseite lädt ihr Design (tokens.css frei)", st == 200)
    br.cookies["jarvis_device"] = token
    st, page = br.req("GET", "/")
    check("Browser mit Cookie sieht JARVIS-Oberfläche", st == 200 and b"app.js" in page and b"data-build" in page)

    # ---------------------------------------------------------------- Entkoppeln
    st, devs = adm.req("GET", "/api/pairing/devices")
    check("Gerät im Admin gelistet", any(x["name"] == "E2E-Test" for x in devs.get("devices", [])))
    st, _ = app.req("POST", "/api/unpair")
    st2, _ = app.req("GET", "/api/status")
    check("Nach Entkoppeln: 401", st == 200 and st2 == 401)

    bad = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} Prüfungen bestanden." + (f" Fehlgeschlagen: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
