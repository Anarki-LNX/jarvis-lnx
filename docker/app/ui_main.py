#!/usr/bin/env python3
"""NuOrb (Docker): Start der Web-Oberfläche (nuorb-ui) mit Kopplung.

Lädt nuorb-ui/server.py unverändert als Modul und ergänzt nur:
  * Kopplung: GET /api/info, POST /api/pair, POST /api/unpair, Seite /pair
  * Pflicht-Token für alle übrigen /api/*-Aufrufe (Bearer-Header oder Cookie nuorb_device);
    Aufrufe aus dem Container selbst (Loopback, z. B. nuorb-admin) brauchen keinen.
  * Generisch: keine Haus-/Geräte-Weiche zu Claude, solange die Plugins aus sind (sonst gingen Sätze trotz
    „Lokal“ an die Cloud), Status mit Sprache und Servername.
"""
from __future__ import annotations

import ipaddress
import re
import sys
import time
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.routing import APIRoute
from starlette.routing import Route

sys.path.insert(0, "/opt/nuorb/ui")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nuorb_common as jc  # noqa: E402
import server as ui  # noqa: E402  (nuorb-ui/server.py)

app = ui.app
COOKIE = "nuorb_device"
PAGES = jc.APP / "pages"

# Generisch: Haus-, Geräte- und Cloud-Weiche sind über Feature-Flags von nuorb-ui aus (nuorb-env:
# NUORB_FEATURE_ZUHAUSE=0, NUORB_FEATURE_GERAET=0, NUORB_FEATURE_CLOUD_WEICHE=0) – im Modus „Lokal“ geht nichts an Claude.

# Persona als Vorlage: {assistant_name}, {brand}, {user_name}; vor dem Kennenlernen mit Begrüßungsregel
import personas  # noqa: E402

_orig_persona = ui.cur_persona


def _persona() -> str:
    return personas.render(_orig_persona(), jc.lang(), jc.assistant_name(), jc.brand(), jc.user_name(), jc.onboarded())


ui.cur_persona = _persona

if jc.tls_mode() != "selfsigned":
    # Eigenes Zertifikat passt nicht auf 127.0.0.1: interne Aufrufe UI -> Admin im Container ohne CA-Prüfung
    import httpx

    async def _admin_intern(method: str, path: str, payload: dict | None = None):
        try:
            token = ui.ADMIN_TOKEN_FILE.read_text().strip()
        except OSError:
            return 503, {"detail": "Admin-Schnittstelle noch nicht bereit."}
        try:
            async with httpx.AsyncClient(verify=False, timeout=httpx.Timeout(60, connect=3)) as c:
                r = await c.request(method, ui.ADMIN_URL + path, json=payload, headers={"X-NuOrb-Internal": token})
            try:
                data = r.json()
            except Exception:
                data = {"detail": r.text[:300]}
            return r.status_code, data if isinstance(data, dict) else {"data": data}
        except Exception as exc:
            return 503, {"detail": f"Admin nicht erreichbar ({exc.__class__.__name__})."}
    ui._admin = _admin_intern

# ------------------------------------------------------------------ Hilfen
_fails: dict[str, list[float]] = {}


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _limited(ip: str) -> bool:
    now = time.time()
    arr = [t for t in _fails.get(ip, []) if now - t < 900]
    _fails[ip] = arr
    return len(arr) >= 5


def _token(request: Request) -> str:
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return request.cookies.get(COOKIE, "")


def _device(request: Request) -> str | None:
    return jc.device_for_token(_token(request), _ip(request))


def _internal(request: Request) -> bool:
    """Server-zu-Server im Container (nuorb-admin): nur Loopback UND gemeinsames internes Token.
    Loopback allein reicht nicht – ein Reverse-Proxy auf demselben Host sähe sonst aus wie „intern“."""
    given = request.headers.get("x-nuorb-internal", "")
    if not given or not jc.is_loopback(_ip(request)):
        return False
    try:
        tok = ui.ADMIN_TOKEN_FILE.read_text().strip()
    except OSError:
        return False
    import hmac
    return bool(tok) and hmac.compare_digest(given.strip(), tok)


# nuorb-ui prüft die Kopplung inzwischen auch selbst (lan_only -> device_for_request). Interne Aufrufe des Admin-Panels
# (Loopback + internes Token) zählen dort als gekoppelt, sonst sieht die Übersicht die Oberfläche als „aus“.
_orig_device_for_request = getattr(ui, "device_for_request", None)
if _orig_device_for_request:
    def _device_for_request(request: Request):
        if _internal(request):
            return {"id": "internal", "name": "admin", "platform": "internal"}
        return _orig_device_for_request(request)
    ui.device_for_request = _device_for_request


def _set_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(COOKIE, token, max_age=10 * 365 * 86400, httponly=True, secure=True,
                    samesite="strict", path="/")


NETS = jc.allowed_nets()
PUBLIC_API = {"/api/info", "/api/pair"}
# Für die Kopplungsseite nötig (ohne Inhalt über den Nutzer)
PUBLIC_PAGES = {"/pair", "/pair.js", "/nuorb-ca.crt", "/tokens.css", "/icon.svg", "/favicon.ico"}


@app.middleware("http")
async def pairing_guard(request: Request, call_next):
    path = request.url.path
    try:
        ip = ipaddress.ip_address(_ip(request).split("%")[0])
        ip = getattr(ip, "ipv4_mapped", None) or ip
        lan = any(ip in n for n in NETS)
    except ValueError:
        lan = False
    if not lan:
        return JSONResponse({"error": "only reachable from the home network/VPN", "detail": "home_network_only"}, status_code=403)
    if jc.pairing_required() and not _internal(request):
        authed = _device(request) is not None
        if path.startswith("/api/") and path not in PUBLIC_API and not authed:
            return JSONResponse({"detail": "pairing_required"}, status_code=401)
        if not authed and not path.startswith("/api/") and path not in PUBLIC_PAGES \
                and not path.startswith("/fonts/"):
            # Hauptdokument und alle übrigen Dateien nur gekoppelt; 401 erkennt die App, der Browser sieht die Kopplungsseite
            if path in ("/", "/index.html"):
                return FileResponse(PAGES / "pair.html", status_code=401, headers={"Cache-Control": "no-store"})
            return JSONResponse({"detail": "pairing_required"}, status_code=401)
    return await call_next(request)


# ------------------------------------------------------------------ neue Endpunkte (vor dem Static-Mount einhängen)
async def info(request: Request):
    return {"product": jc.PRODUCT, "api": jc.API_VERSION, "name": jc.server_name(), "lang": jc.lang(),
            "assistant_name": jc.assistant_name(), "brand": jc.brand(),
            "ui_lang": jc.env("UI_LANG", "auto").lower() or "auto", "pairing_required": jc.pairing_required(), "build": ui.build_id(),
            "paired": _device(request) is not None}


async def pair(request: Request):
    ip = _ip(request)
    if _limited(ip):
        return JSONResponse({"detail": "too_many_attempts"}, status_code=429)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict) or not jc.redeem_pairing_code(str(body.get("code", ""))):
        _fails.setdefault(ip, []).append(time.time())
        print(f"[pair] wrong or expired code from {ip}", flush=True)
        return JSONResponse({"detail": "invalid_or_expired_code"}, status_code=403)
    name = re.sub(r"[\x00-\x1f<>]", "", str(body.get("device") or "Device"))[:60]
    platform = re.sub(r"[^a-z0-9_-]", "", str(body.get("platform") or "web").lower())[:20]
    did, token = jc.add_device(name, platform, ip)
    print(f"[pair] device paired: {did} {name!r} ({platform}) from {ip}", flush=True)
    resp = JSONResponse({"token": token, "device_id": did, "name": jc.server_name(), "api": jc.API_VERSION,
                         "lang": jc.lang()})
    if body.get("cookie") is True:  # Browser-Kopplung über /pair
        _set_cookie(resp, token)
    return resp


async def unpair(request: Request):
    did = _device(request)
    if did:
        jc.revoke_device(did)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


async def pair_page(request: Request):
    return FileResponse(PAGES / "pair.html", headers={"Cache-Control": "no-store"})


async def pair_asset(request: Request):
    return FileResponse(PAGES / "pair.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


_orig_status = None
for r in app.router.routes:
    if isinstance(r, Route) and r.path == "/api/status":
        _orig_status = r.endpoint


_brain_url = {"mtime": None}


def _sync_brain_url() -> None:
    """„Gehirn online“-Probe folgt der Ollama-Adresse aus Hermes' config.yaml (Einrichtung kann sie ändern)."""
    p = jc.DATA / "config.yaml"
    try:
        mt = p.stat().st_mtime_ns
    except OSError:
        return
    if mt == _brain_url["mtime"]:
        return
    _brain_url["mtime"] = mt
    try:
        from ruamel.yaml import YAML
        cfg = YAML(typ="safe").load(p.read_text(encoding="utf-8")) or {}
        api = ((cfg.get("providers") or {}).get("lan-ollama") or {}).get("api") or ""
        if api:
            ui.BRAIN_URL = api.rstrip("/").removesuffix("/v1") + "/api/version"
    except Exception as exc:
        print(f"config.yaml unreadable for brain probe: {exc}", flush=True)


async def status_plus(request: Request):
    _sync_brain_url()
    data = dict(await _orig_status())
    data.setdefault("lang", jc.lang())
    data.update(assistant_name=jc.assistant_name(), user_name=jc.user_name() or None, onboarded=jc.onboarded(),
                greeting=personas.GREETING[jc.lang()].replace("{brand}", jc.brand()))
    data.setdefault("server_name", jc.server_name())
    return data


_orig_index = None
for r in app.router.routes:
    if isinstance(r, Route) and r.path == "/":
        _orig_index = r.endpoint


async def index_plus(request: Request):
    resp = await _orig_index()
    html = resp.body.decode("utf-8")
    if jc.lang() == "en":
        html = html.replace('<html lang="de"', '<html lang="en"', 1)
    return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache, no-store"})


SETUP_DONE = jc.CONF / "setup-done.json"
WAKE_DIR = jc.J / "wakeword"
WAKE_FILES = {"melspectrogram.tflite", "embedding_model.tflite", "hey_nuorb_v0.1.tflite"}
NO_BRAIN = {"de": "{brand} hat noch kein Gehirn. Bitte im Admin-Panel unter „Einrichtung“ Ollama oder einen Claude-Schlüssel eintragen.",
            "en": "{brand} has no brain yet. Please set up Ollama or a Claude key under “Setup” in the admin panel."}


async def wakeword(request: Request):
    """openWakeWord-Dateien für die App, nur wenn der Betreiber sie unter /opt/data/nuorb/wakeword/ abgelegt hat."""
    name = request.path_params["name"]
    p = WAKE_DIR / name
    if name not in WAKE_FILES or not p.is_file():
        return JSONResponse({"detail": "not_found"}, status_code=404)
    return FileResponse(p, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


_orig_ask = None
for r in app.router.routes:
    if isinstance(r, Route) and r.path == "/api/ask":
        _orig_ask = r.endpoint


async def ask_guard(request: Request):
    if not SETUP_DONE.exists() and ui.cur_mode() == "live":
        return JSONResponse({"detail": NO_BRAIN[jc.lang()].replace("{brand}", jc.brand()), "code": "no_brain"}, status_code=503)
    return await _orig_ask(request)


async def assistant(request: Request):
    """Name/Kennenlernen für Oberfläche und App. Schreiben läuft über das Admin-Panel (Sicherung, Audit)."""
    if request.method == "GET":
        return {"assistant_name": jc.assistant_name(), "brand": jc.brand(), "user_name": jc.user_name() or None,
                "onboarded": jc.onboarded(), "greeting": personas.GREETING[jc.lang()].replace("{brand}", jc.brand())}
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict) or set(body) - {"assistant_name", "user_name", "onboarded"}:
        return JSONResponse({"detail": "Erlaubt: assistant_name, user_name, onboarded"}, status_code=400)
    code, data = await ui._admin("POST", "/internal/assistant", {**body, "source": "ui"})
    ui._status_cache["t"] = 0
    return JSONResponse(data, status_code=code)


NEW = [
    APIRoute("/api/assistant", assistant, methods=["GET", "POST"]),
    APIRoute("/api/ask", ask_guard, methods=["POST"]),
    APIRoute("/api/wakeword/{name}", wakeword, methods=["GET"]),
    APIRoute("/api/info", info, methods=["GET"]),
    APIRoute("/api/pair", pair, methods=["POST"]),
    APIRoute("/api/unpair", unpair, methods=["POST"]),
    APIRoute("/api/status", status_plus, methods=["GET"]),
    APIRoute("/pair", pair_page, methods=["GET"]),
    APIRoute("/pair.js", pair_asset, methods=["GET"]),
    APIRoute("/", index_plus, methods=["GET"]),
]
app.router.routes[0:0] = NEW  # zuerst passend gewinnt -> vor den Originalen und dem Static-Mount


def mdns_start() -> None:
    """mDNS-Ankündigung _nuorb._tcp (nur sinnvoll mit network_mode: host; im Bridge-Netz kommt Multicast nicht ins LAN)."""
    if jc.env("NUORB_MDNS", "0") != "1":
        return
    try:
        import socket
        from zeroconf import ServiceInfo, Zeroconf
        port = int(jc.env("NUORB_UI_PORT_PUBLIC", jc.env("UI_PORT", "8443")))
        name = jc.server_name()
        info = ServiceInfo("_nuorb._tcp.local.", f"{name}._nuorb._tcp.local.", port=port,
                           properties={"v": "1", "api": str(jc.API_VERSION), "name": name, "fp": jc.ca_fingerprint()},
                           server=f"{socket.gethostname()}.local.")
        zc = Zeroconf()
        zc.register_service(info, allow_name_change=True)
        print(f"[mdns] _nuorb._tcp announced: {name} port {port}", flush=True)
    except Exception as exc:
        print(f"[mdns] announcement failed: {exc}", flush=True)


if __name__ == "__main__":
    import uvicorn
    jc.ensure_certs()
    mdns_start()
    uvicorn.run(app, host=jc.env("UI_HOST", "0.0.0.0"), port=int(jc.env("UI_PORT", "8443")), log_level="info",
                proxy_headers=False, server_header=False, **jc.ssl_kwargs())
