#!/usr/bin/env python3
"""NuOrb-Shell auf dem Handy: lokale Auslieferung der NuOrb-UI + Proxy zu nuorb und zum Geraetedienst.

Laeuft als User-Dienst auf dem Handy und lauscht NUR auf 127.0.0.1 (Standard :8765). Der Kiosk-Browser
(cage + WebKit) oeffnet http://127.0.0.1:8765/ – das ist ein sicherer Kontext (Mikrofon erlaubt), und die
Oberflaeche bleibt bedienbar, auch wenn WLAN aus oder nuorb nicht erreichbar ist.

  /                 -> lokale Kopie von nuorb' gerenderter index.html (mit ?v=<build>)
  /<datei>          -> lokale Kopie der statischen Dateien
  /api/version      -> Build der LOKALEN Kopie (die App laedt neu, sobald die Shell neu synchronisiert hat)
  /api/*            -> Proxy zu NUORB_URL (SSE und Audio-Upload werden durchgestreamt)
  /device/*         -> Proxy zu DEVICE_URL (Geraetedienst von handy-linux), mit Header X-NuOrb-Device: 1
  /shell/status     -> {"nuorb": bool, "build": str, "synced": iso|null, "device": bool}

Sync: beim Start und alle SYNC_S Sekunden /api/manifest von nuorb; bei neuem Build alles in ein neues
Verzeichnis laden, SHA-256 pruefen, dann atomar umschalten. Ohne jemals erfolgreichen Sync: eingebaute
Notseite mit WLAN-Knopf.

Nur Python-Standardbibliothek. Umgebung: NUORB_URL (https://$NUORB_SERVER_IP:8443), DEVICE_URL
(http://127.0.0.1:8766), DEVICE_PREFIX (/device/), DEVICE_ORIGIN (leer), SHELL_PORT (8765), SHELL_DATA (~/.local/share/nuorb-shell), NUORB_CA (optional,
PEM der Heim-CA; sonst System-Trust), SYNC_S (60).
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import ssl
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

NUORB_URL = os.environ.get("NUORB_URL", "https://" + os.environ.get("NUORB_SERVER_IP", "nuorb.local") + ":8443").rstrip("/")
DEVICE_URL = os.environ.get("DEVICE_URL", "http://127.0.0.1:8766").rstrip("/")
# Pfad-Praefix beim Geraetedienst: /device/<x> -> DEVICE_URL + DEVICE_PREFIX + <x>
# (Vertrag nuorb-ui: "/device/"; Dienst von handy-linux: "/api/")
DEVICE_PREFIX = os.environ.get("DEVICE_PREFIX", "/device/")
# Optional: Origin, den der Geraetedienst fuer POST verlangt (Dienst von handy-linux prueft den Origin)
DEVICE_ORIGIN = os.environ.get("DEVICE_ORIGIN", "")
PORT = int(os.environ.get("SHELL_PORT", "8765"))
DATA = Path(os.environ.get("SHELL_DATA", str(Path.home() / ".local/share/nuorb-shell")))
CA = os.environ.get("NUORB_CA", "")
SYNC_S = int(os.environ.get("SYNC_S", "60"))
ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
       "transfer-encoding", "upgrade", "host", "content-length"}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".svg": "image/svg+xml", ".woff2": "font/woff2", ".json": "application/json", ".txt": "text/plain; charset=utf-8",
         ".webmanifest": "application/manifest+json", ".png": "image/png", ".wav": "audio/wav"}

STATE = {"nuorb": False, "synced": None, "device": None, "lock": threading.Lock()}


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S} {msg}", file=sys.stderr, flush=True)


def ssl_ctx() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=CA) if CA else ssl.create_default_context()


def conn_for(base: str, timeout: float):
    u = urllib.parse.urlsplit(base)
    if u.scheme == "https":
        return http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=timeout, context=ssl_ctx())
    return http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)


def current_dir() -> Path:
    return DATA / "current"


def local_build() -> str:
    try:
        return json.loads((current_dir() / ".build.json").read_text())["build"]
    except Exception:
        return ""


# ------------------------------------------------------------------------------------------- Sync
def fetch(path: str, timeout: float = 15) -> bytes:
    c = conn_for(NUORB_URL, timeout)
    try:
        c.request("GET", path, headers={"User-Agent": "nuorb-shell", "Cache-Control": "no-cache"})
        r = c.getresponse()
        body = r.read()
        if r.status != 200:
            raise OSError(f"{path}: HTTP {r.status}")
        return body
    finally:
        c.close()


def sync_once() -> bool:
    try:
        man = json.loads(fetch("/api/manifest", 8))
    except Exception as exc:
        STATE["nuorb"] = False
        log(f"Sync: nuorb nicht erreichbar ({exc.__class__.__name__})")
        return False
    STATE["nuorb"] = True
    build = man.get("build", "")
    if build and build == local_build():
        return True
    tmp = DATA / f"neu-{build}-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        for rel, sha in man.get("files", {}).items():
            if ".." in rel or rel.startswith("/"):
                raise OSError(f"ungueltiger Pfad {rel}")
            data = fetch("/" + urllib.parse.quote(rel))
            if hashlib.sha256(data).hexdigest() != sha:
                raise OSError(f"Pruefsumme falsch: {rel} (nuorb hat waehrend des Syncs aktualisiert?)")
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / rel).write_bytes(data)
        (tmp / "index.html").write_bytes(fetch("/"))
        (tmp / ".build.json").write_text(json.dumps({"build": build, "synced": datetime.now().isoformat(timespec="seconds")}))
        with STATE["lock"]:
            old = DATA / "alt"
            shutil.rmtree(old, ignore_errors=True)
            if current_dir().exists():
                current_dir().rename(old)
            tmp.rename(current_dir())
            shutil.rmtree(old, ignore_errors=True)
        STATE["synced"] = datetime.now().isoformat(timespec="seconds")
        log(f"Sync: neue UI-Version {build} ({len(man.get('files', {}))} Dateien)")
        return True
    except Exception as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        log(f"Sync fehlgeschlagen: {exc}")
        return False


def sync_loop() -> None:
    while True:
        sync_once()
        time.sleep(SYNC_S)


# ------------------------------------------------------------------------------- Notseite (ohne Kopie)
NOTSEITE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>NuOrb</title>
<style>body{margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;
background:#040507;color:#e8f1f5;font:16px system-ui,sans-serif;text-align:center;padding:24px}
.o{width:140px;height:140px;border-radius:50%;box-shadow:0 0 0 2px #38d9ff,0 0 40px rgba(56,217,255,.4);
background:radial-gradient(circle at 50% 38%,rgba(56,217,255,.35),#02121a 65%)}
button{min-height:64px;padding:0 28px;border-radius:20px;border:0;font:600 18px system-ui;background:#38d9ff;color:#00151c}
p{color:#9aa8b2;max-width:320px}</style></head><body><div class="o"></div><h1>NuOrb</h1>
<p id="t">Noch keine Oberfläche geladen. Dafür muss nuorb einmal erreichbar sein.</p>
<button id="w">WLAN einschalten</button><script>
const t=document.getElementById("t");
document.getElementById("w").onclick=async()=>{t.textContent="Schalte WLAN ein …";
try{const r=await fetch("/device/wifi",{method:"POST",headers:{"Content-Type":"application/json"},body:'{"on":true}'});
t.textContent=r.ok?"WLAN ist an. Warte auf nuorb …":"WLAN ließ sich nicht einschalten.";}catch(e){t.textContent="Gerätedienst nicht erreichbar.";}};
setInterval(async()=>{try{const s=await(await fetch("/shell/status")).json();if(s.build)location.reload();}catch(e){}},3000);
</script></body></html>"""


# ------------------------------------------------------------------------------------------ Server
class Handler(BaseHTTPRequestHandler):
    server_version = "nuorb-shell"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # ruhig: nur Fehler
        pass

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if self.path.startswith(("/api/", "/shell/", "/device/")) else "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

    def _same_origin(self) -> bool:
        o = self.headers.get("Origin")
        return o is None or o in ORIGINS

    # -- statische Dateien
    def _static(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        rel = "index.html" if path in ("/", "/index.html") else urllib.parse.unquote(path.lstrip("/"))
        base = current_dir()
        f = (base / rel).resolve()
        if not base.exists():
            return self._send(200, NOTSEITE.encode(), "text/html; charset=utf-8")
        if not str(f).startswith(str(base.resolve()) + os.sep) or not f.is_file() or f.name.startswith("."):
            return self._send(404, b"nicht gefunden", "text/plain; charset=utf-8")
        self._send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))

    # -- Proxy (streamend)
    def _proxy(self, base: str, extra_headers: dict, timeout: float, target: str | None = None) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP and k.lower() != "origin"}
        headers.update(extra_headers)
        u = urllib.parse.urlsplit(base)
        c = conn_for(base, timeout)
        try:
            c.request(self.command, (u.path or "") + (target or self.path), body=body, headers=headers)
            r = c.getresponse()
        except Exception as exc:
            c.close()
            if base == NUORB_URL:
                STATE["nuorb"] = False
            name = "nuorb" if base == NUORB_URL else "Gerätedienst"
            return self._json(503, {"detail": f"{name} nicht erreichbar ({exc.__class__.__name__})", "offline": True})
        if base == NUORB_URL:
            STATE["nuorb"] = True
        self.send_response(r.status)
        for k, v in r.getheaders():
            if k.lower() not in HOP:
                self.send_header(k, v)
        stream = "text/event-stream" in (r.getheader("Content-Type") or "")
        clen = r.getheader("Content-Length")
        if clen is not None and not stream:
            self.send_header("Content-Length", clen)
            self.end_headers()
            self.wfile.write(r.read())
        else:  # SSE / unbekannte Laenge: chunked durchreichen
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                while True:
                    chunk = r.read1(8192) if hasattr(r, "read1") else r.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        c.close()

    def _route(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/version":
            return self._json(200, {"build": local_build(), "local": True})
        if path == "/shell/status":
            return self._json(200, {"nuorb": STATE["nuorb"], "build": local_build(), "synced": STATE["synced"],
                                    "nuorb_url": NUORB_URL})
        if path.startswith("/device/"):
            if self.command != "GET" and not self._same_origin():
                return self._json(403, {"detail": "Nur von der NuOrb-Oberfläche."})
            rest = self.path[len("/device/"):]
            extra = {"X-NuOrb-Device": "1"}
            if DEVICE_ORIGIN and self.command != "GET":
                extra["Origin"] = DEVICE_ORIGIN
            return self._proxy(DEVICE_URL, extra, 10, DEVICE_PREFIX + rest)
        if path.startswith("/api/"):
            if self.command != "GET" and not self._same_origin():
                return self._json(403, {"detail": "Nur von der NuOrb-Oberfläche."})
            sse = path.endswith("/events")
            return self._proxy(NUORB_URL, {}, 600 if sse else 60)
        if self.command in ("GET", "HEAD"):
            return self._static()
        self._json(405, {"detail": "nicht erlaubt"})

    do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = lambda self: self._route()


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=sync_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    log(f"nuorb-shell auf http://127.0.0.1:{PORT}/ – nuorb {NUORB_URL}, Geraete {DEVICE_URL}, lokale UI {local_build() or '(keine)'}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
