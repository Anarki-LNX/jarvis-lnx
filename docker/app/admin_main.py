#!/usr/bin/env python3
"""NuOrb (Docker): Start des Admin-Panels (nuorb-admin) im Container.

Lädt nuorb-admin/server.py unverändert als Modul und passt es an den Container an:
  * Dienste: s6 statt systemd (Status über s6-svstat, Neustart über s6-svc), Protokolle aus Dateien.
  * Kein Xiaomi-Handy (Seite „Handy“ ausgeblendet, kein SSH).
  * Neu: Ersteinrichtung (LLM wählen, Claude-Schlüssel) und „Gerät koppeln“ (QR-Code, Geräteliste).
Die neuen Seiten sind eigenständige HTML-Dateien unter /static/docker/, ihre API liegt hinter dem Admin-Login.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.routing import APIRoute
from starlette.routing import Route

sys.path.insert(0, "/opt/nuorb/admin")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nuorb_common as jc  # noqa: E402
import server as adm  # noqa: E402  (nuorb-admin/server.py)

app = adm.app
PAGES = jc.APP / "pages"
SVC = {"hermes": None, "stt": "nuorb-stt", "ui": "nuorb-ui", "admin": "nuorb-admin"}
LOGS = jc.J / "logs"

# ------------------------------------------------------------------ Dienste über s6
adm.UNITS.clear()
adm.UNITS.update({"hermes": "hermes-gateway", "stt": "nuorb-stt", "ui": "nuorb-ui", "admin": "nuorb-admin"})
adm.UNIT_LABELS["ui"] = "NuOrb-Oberfläche (Web/App)"


def gateway_slot() -> Path | None:
    """Hermes registriert sein Gateway dynamisch unter /run/hermes-service/<name>."""
    root = Path("/run/hermes-service")
    with_sup = [p for p in sorted(root.glob("*")) if (p / "supervise").exists() and "gateway" in p.name] if root.is_dir() else []
    return with_sup[0] if with_sup else None


def svc_dir(name: str) -> Path | None:
    if name == "hermes":
        return gateway_slot()
    p = Path("/run/service") / SVC[name]
    return p if p.exists() else None


async def unit_state(name: str) -> dict:
    d = svc_dir(name)
    out = ""
    if d:
        p = await asyncio.create_subprocess_exec("s6-svstat", "-o", "up,pid,updownfor,normallyup", str(d),
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out = (await p.communicate())[0].decode().strip()
    parts = out.split()
    up = parts[:1] == ["true"]
    since = None
    if len(parts) >= 3 and parts[2].isdigit():
        since = f"seit {int(parts[2]) // 60} min"
    return {"id": name, "unit": adm.UNITS[name], "label": adm.UNIT_LABELS[name],
            "active": "active" if up else ("inactive" if d else "unknown"), "sub": "running" if up else "dead",
            "since": since, "memory": None, "restarts": None}


adm.unit_state = unit_state
adm.CTL_DIR = jc.J / "ctl"  # Verzeichnis existiert -> Admin-Seite bietet Neustarts an


async def service_restart(request: Request):
    name = request.path_params["name"]
    if name not in adm.UNITS:
        raise HTTPException(404, "Unbekannter Dienst.")
    d = svc_dir(name)
    if not d:
        raise HTTPException(503, "Dienst nicht gefunden.")
    adm.audit(adm.who(request), f"Neustart angefordert: {adm.UNITS[name]}")
    if name == "admin":  # sich selbst: Antwort zuerst, dann Neustart
        asyncio.get_running_loop().call_later(0.5, lambda: subprocess.Popen(["s6-svc", "-r", str(d)]))
        return {"ok": True, "self": True}
    p = await asyncio.create_subprocess_exec("s6-svc", "-r", str(d), stderr=asyncio.subprocess.PIPE)
    err = (await p.communicate())[1].decode()[:200]
    ok = p.returncode == 0
    res = {"id": "s6", "action": "restart", "unit": adm.UNITS[name], "ok": ok,
           "message": "neu gestartet" if ok else f"Neustart fehlgeschlagen {err}", "time": adm.now_iso()}
    adm.atomic_write(adm.CTL_DIR / "result.json", json.dumps(res), 0o600)
    return {"ok": ok, "result": res}


# Protokolle: Dateien statt journald
for key, fname, label in (("j-hermes", None, "Dienst: Hermes-Gateway"), ("j-stt", "stt", "Dienst: Spracherkennung"),
                          ("j-ui", "ui", "Dienst: Oberfläche"), ("j-admin", "admin", "Dienst: Verwaltung")):
    if fname:
        adm.LOG_SOURCES[key] = ("file", LOGS / fname / "current", label)
    else:
        adm.LOG_SOURCES.pop(key, None)

# ------------------------------------------------------------------ Aufrufe an die Oberfläche mit internem Token
_orig_probe = adm.probe


def _internal_headers() -> dict:
    try:
        return {"X-NuOrb-Internal": adm.INTERNAL_TOKEN_FILE.read_text().strip()}
    except OSError:
        return {}


async def probe(url: str, timeout: float = 1.5, headers: dict | None = None, verify=True):
    if url.startswith(adm.UI_URL):
        headers = {**(headers or {}), **_internal_headers()}
    if jc.tls_mode() == "custom" and url.startswith(adm.UI_URL):
        verify = False  # eigenes Zertifikat passt nicht auf 127.0.0.1; Aufruf bleibt im Container
    return await _orig_probe(url, timeout, headers, verify)


adm.probe = probe


async def tts_test(request: Request):
    d = await adm.body(request)
    text = str(d.get("text", "Guten Tag. Alle Systeme sind bereit."))[:300]
    try:
        async with httpx.AsyncClient(timeout=20, verify=adm.ui_ssl_ctx() if jc.tls_mode() == "selfsigned" else False) as c:
            r = await c.post(f"{adm.UI_URL}/api/tts", json={"text": text}, headers=_internal_headers())
        if r.status_code >= 400:
            raise HTTPException(502, "Sprachausgabe nicht erreichbar.")
        return Response(r.content, media_type=r.headers.get("content-type", "audio/wav"))
    except httpx.HTTPError:
        raise HTTPException(502, "Sprachausgabe nicht erreichbar.")


# ------------------------------------------------------------------ kein Xiaomi-Handy im generischen Image


async def phone_status(cached: bool = False) -> dict:
    return {"reachable": False, "host": "", "configured": False, "status": None, "error": None, "disabled": True}


adm.phone_status = phone_status


# ------------------------------------------------------------------ Einrichtungscode: Hinweis für Docker
async def auth_state(request: Request):
    return {"configured": adm.auth_configured(), "loggedIn": adm.session_of(request) is not None,
            "setupHint": None if adm.auth_configured() else
            f"docker compose exec nuorb cat {adm.SETUP_FILE}\n# oder: docker compose logs nuorb | grep -i einrichtungscode"}


# ------------------------------------------------------------------ Ersteinrichtung (LLM + Schlüssel)
SETUP_DONE = jc.CONF / "setup-done.json"
OLLAMA_PROVIDER = "lan-ollama"


def setup_state() -> dict:
    cfg = adm.to_plain(adm.load_config_rt())
    model = cfg.get("model") or {}
    prov = (cfg.get("providers") or {}).get(OLLAMA_PROVIDER) or {}
    return {"done": SETUP_DONE.exists(), "lang": jc.lang(), "name": jc.server_name(),
            "ollama_url": (prov.get("api") or jc.env("NUORB_INIT_OLLAMA_URL")).removesuffix("/v1"),
            "ollama_model": (model.get("default") if str(model.get("provider", "")).startswith("custom:") else "")
            or jc.env("NUORB_INIT_OLLAMA_MODEL"),
            "anthropic_key": adm.mask(adm.env_value("ANTHROPIC_API_KEY")),
            "brain": adm.brain_state()["mode"], "claude_models": adm.CLAUDE_MODELS,
            "remote_model": adm.brain_state()["remote_model"],
            "voice": jc.voice_name(), "voice_choices": jc.VOICE_CHOICES,
            "voices_installed": sorted(p.stem for p in (jc.MODELS / "voices").glob("*.onnx")),
            "models": models_info(), **assistant_state()}


def models_info() -> dict:
    st = jc.models_status()
    stt_ok = (jc.MODELS / "stt/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/encoder.int8.onnx").exists()
    return {**st, "stt_ready": stt_ok, "voice_ready": (jc.MODELS / "voices" / f"{jc.voice_name()}.onnx.json").exists()}


async def setup_models(request: Request):
    return models_info()


PERSONA_DEFAULTS = None


async def setup_language(request: Request):
    """Sprache und Stimme: ui.json (lang, piper_voice, Persona falls unverändert), Hermes stt/tts; Stimme laden."""
    import personas
    d = await adm.body(request)
    lg = d.get("lang")
    voice = str(d.get("voice") or "")
    if lg not in ("de", "en"):
        raise HTTPException(400, "Sprache de oder en.")
    if not re.fullmatch(r"[a-z]{2}_[A-Z]{2}-[a-z0-9_]+-(x_low|low|medium|high)", voice):
        raise HTTPException(400, "Ungültiger Stimmenname (z. B. de_DE-thorsten-medium).")
    ui = adm.read_ui_settings()
    fields = {"lang": lg, "piper_voice": voice}
    if not ui.get("persona") or ui.get("persona") in personas.PERSONA.values():
        fields["persona"] = personas.PERSONA[lg]   # eigene Persona bleibt unangetastet
    adm.write_ui_fields(fields, f"Einrichtung: Sprache {lg}, Stimme {voice}")
    for k, v in (("stt.language", lg), ("stt.openai.language", lg), ("tts.piper.voice", str(jc.MODELS / "voices" / f"{voice}.onnx"))):
        await adm.run_hermes("config", "set", k, v, timeout=60)
    adm.audit(adm.who(request), f"Einrichtung: Sprache {lg}, Stimme {voice}")
    if not (jc.MODELS / "voices" / f"{voice}.onnx.json").exists():
        subprocess.Popen(["/opt/nuorb/venv/bin/python", "-I", "/opt/nuorb/app/fetch_models.py", "voice", voice],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return {"ok": True, "downloading": voice}
    return {"ok": True}


async def setup_get(request: Request):
    return setup_state()


async def setup_ollama_probe(request: Request):
    d = await adm.body(request)
    url = str(d.get("url", "")).strip().rstrip("/").removesuffix("/v1")
    if not re.fullmatch(r"https?://[A-Za-z0-9.\-\[\]:]{1,200}(:\d{1,5})?", url):
        raise HTTPException(400, "Ungültige Adresse (z. B. http://192.0.2.30:11434).")
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            v = (await c.get(f"{url}/api/version")).json()
            tags = (await c.get(f"{url}/api/tags")).json()
    except Exception as exc:
        raise HTTPException(502, f"Ollama unter {url} nicht erreichbar ({exc.__class__.__name__}).")
    return {"ok": True, "version": v.get("version"), "models": sorted(m.get("name") for m in tags.get("models", []))}


def _env_set(name: str, value: str | None) -> None:
    lines, found = [], False
    for n, v, raw in adm.read_env():
        if n == name:
            found = True
            if value:
                lines.append(f"{name}={value}")
        else:
            lines.append(raw)
    if not found and value:
        lines.append(f"{name}={value}")
    path = adm.FILES["env"][0]
    adm.backup("env", adm.read_text(path), f"Einrichtung: {name}")
    adm.atomic_write(path, "\n".join(lines) + "\n", 0o600)


async def setup_apply(request: Request):
    """Schreibt LLM-Wahl: Ollama-Provider, Claude-Schlüssel, Gehirn-Modus. Danach Gateway-Neustart."""
    d = await adm.body(request)
    mode = d.get("mode")
    if mode not in ("local", "auto", "remote"):
        raise HTTPException(400, "Modus fehlt (local, auto oder remote).")
    url = str(d.get("ollama_url") or "").strip().rstrip("/").removesuffix("/v1")
    model = str(d.get("ollama_model") or "").strip()
    key = str(d.get("anthropic_key") or "").strip()
    ctx = int(d.get("context") or 65536)
    if mode in ("local", "auto") and not (url and re.fullmatch(r"[A-Za-z0-9._:/\-]{1,120}", model)):
        raise HTTPException(400, "Für Lokal/Automatisch braucht es Ollama-Adresse und Modell.")
    if key and not re.fullmatch(r"sk-ant-[A-Za-z0-9_\-]{20,300}", key):
        raise HTTPException(400, "Das sieht nicht wie ein Anthropic-Schlüssel aus (sk-ant-…).")
    if not 64000 <= ctx <= 1048576:
        raise HTTPException(400, "Hermes braucht mindestens 64k Kontext (64000 bis 1048576).")
    who = adm.who(request)
    if key:
        _env_set("ANTHROPIC_API_KEY", key)
        adm.audit(who, "Einrichtung: Anthropic-Schlüssel gesetzt")
    if mode != "local" and not adm.env_value("ANTHROPIC_API_KEY"):
        raise HTTPException(400, "Für Claude fehlt der Anthropic-Schlüssel.")
    path = adm.FILES["config"][0]
    old = adm.read_text(path)
    data = adm.load_config_rt()
    if url:
        adm.cfg_set(data, f"providers.{OLLAMA_PROVIDER}.api", f"{url}/v1")
        adm.cfg_set(data, f"providers.{OLLAMA_PROVIDER}.name", "Ollama")
        adm.cfg_set(data, f"providers.{OLLAMA_PROVIDER}.models", {model: {"context_length": ctx}} if model else {})
        adm.cfg_set(data, "model.provider", f"custom:{OLLAMA_PROVIDER}")
        adm.cfg_set(data, "model.base_url", f"{url}/v1")
        adm.cfg_set(data, "model.default", model)
        adm.cfg_set(data, "model.context_length", ctx)
        adm.cfg_set(data, "model.ollama_num_ctx", ctx)
        saved = adm.load_brain_saved()
        saved["local"] = {"provider": f"custom:{OLLAMA_PROVIDER}", "base_url": f"{url}/v1", "default": model}
        adm.save_brain_saved(saved)
    adm.backup("config", old, "Einrichtung: LLM")
    adm.atomic_write(path, adm.dump_rt(data))
    # Gehirn-Modus mit derselben Logik wie Admin-Seite und Handy-Schalter
    remote = d.get("remote_model") if d.get("remote_model") in adm.CLAUDE_MODELS else None
    ch = adm.build_brain_change(mode, remote, remote)
    adm.atomic_write(path, ch["text"])
    code, out = await adm.run_hermes("config", "check", timeout=90)
    if code != 0:
        adm.atomic_write(path, old)
        raise HTTPException(500, "Hermes lehnt die Konfiguration ab, alte Einstellung wiederhergestellt: " + out[-400:])
    adm.save_brain_saved(ch["saved"])
    adm.write_ui_fields(ch["ui"], "Einrichtung: Gehirn-Modus")
    adm.audit(who, f"Einrichtung: {ch['desc']}")
    jc._write_json(SETUP_DONE, {"time": adm.now_iso(), "mode": mode})
    gw = gateway_slot()
    if gw:  # Schlüssel aus .env liest Hermes beim Start
        await (await asyncio.create_subprocess_exec("s6-svc", "-r", str(gw))).wait()
    return {"ok": True, "desc": ch["desc"], "privacy": ch["privacy"]}


# ------------------------------------------------------------------ Gerät koppeln
def public_url(request: Request) -> str:
    """Adresse der Oberfläche, wie Geräte sie erreichen: NUORB_PUBLIC_URL, sonst Host aus dem Browser-Aufruf."""
    pub = jc.env("NUORB_PUBLIC_URL")
    if pub:
        return pub.rstrip("/")
    host = request.headers.get("host", "localhost").rsplit(":", 1)[0] if not request.headers.get("host", "").startswith("[") \
        else request.headers.get("host", "").rsplit("]:", 1)[0] + "]"
    scheme = "http" if jc.tls_mode() == "off" else "https"  # off ohne NUORB_PUBLIC_URL: nur zum lokalen Testen
    return f"{scheme}://{host}:{jc.env('NUORB_UI_PORT_PUBLIC', jc.env('UI_PORT', '8443'))}"


def qr_svg_data(text: str) -> str:
    import segno
    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="svg", scale=6, border=2, dark="#000", light="#fff")
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


async def pairing_new(request: Request):
    code = jc.new_pairing_code(adm.who(request))
    url = public_url(request)
    fp = jc.ca_fingerprint()
    q = {"v": "1", "url": url, "code": code["code"], "name": jc.server_name()}
    if fp:
        q["fp"] = fp
    uri = "nuorb://pair?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    browser = f"{url}/pair?code={code['code']}"
    host = urllib.parse.urlparse(url).hostname or ""
    adm.audit(adm.who(request), "Kopplungscode erzeugt")
    return {**code, "url": url, "fingerprint": fp, "uri": uri, "browser_url": browser,
            "qr": qr_svg_data(uri), "qr_browser": qr_svg_data(browser),
            "host_in_cert": jc.tls_mode() != "selfsigned" or host in jc.cert_names(), "cert_names": jc.cert_names()}


async def pairing_devices(request: Request):
    out = [{"id": k, **{x: v.get(x) for x in ("name", "platform", "created", "last_seen", "ip")}}
           for k, v in jc.devices().items()]
    out.sort(key=lambda x: x.get("last_seen") or "", reverse=True)
    return {"devices": out, "pairing_required": jc.pairing_required(), "fingerprint": jc.ca_fingerprint(),
            "tls": jc.tls_mode()}


async def pairing_revoke(request: Request):
    d = await adm.body(request)
    did = str(d.get("id", ""))
    if not jc.revoke_device(did):
        raise HTTPException(404, "Gerät nicht gefunden.")
    adm.audit(adm.who(request), f"Gerät entkoppelt: {did}")
    return {"ok": True}


# ------------------------------------------------------------------ Name des Assistenten, Nutzername, Kennenlernen
NAME_RE = re.compile(r"[\w .'\-]{1,40}")
USER_MEM_PREFIX = ("Name des Nutzers:", "User's name:")


def _remember_user(name: str) -> None:
    path = adm.FILES["user"][0]
    old = adm.read_text(path)
    parts = [x for x in old.split(adm.MEM_SEP) if x.strip() and not x.strip().startswith(USER_MEM_PREFIX)]
    parts.append(f"{USER_MEM_PREFIX[0 if jc.lang() == 'de' else 1]} {name}")
    adm.backup("user", old, "Nutzername gemerkt")
    adm.atomic_write(path, adm.MEM_SEP.join(p.strip() for p in parts) + "\n")


def assistant_state() -> dict:
    import personas
    return {"assistant_name": jc.assistant_name(), "brand": jc.brand(), "user_name": jc.user_name(),
            "onboarded": jc.onboarded(), "greeting": personas.GREETING[jc.lang()].replace("{brand}", jc.brand())}


def assistant_update(d: dict, who: str) -> dict:
    fields, notes = {}, []
    for key in ("assistant_name", "user_name"):
        if key in d and d[key] is not None:
            v = re.sub(r"\s+", " ", str(d[key])).strip()
            if v and not NAME_RE.fullmatch(v):
                raise HTTPException(400, "Name: 1–40 Zeichen, Buchstaben, Ziffern, Leerzeichen, . ' -")
            fields[key] = v or None   # leer = zurück auf Standard
            notes.append(f"{key}={v or '(Standard)'}")
    if "onboarded" in d:
        if not isinstance(d["onboarded"], bool):
            raise HTTPException(400, "onboarded muss true/false sein.")
        fields["onboarded"] = d["onboarded"]
        notes.append(f"onboarded={d['onboarded']}")
    if not fields:
        raise HTTPException(400, "Nichts zu ändern.")
    adm.write_ui_fields(fields, "Name/Kennenlernen")
    if fields.get("user_name"):
        _remember_user(fields["user_name"])
    adm.audit(who, "Assistent: " + ", ".join(notes))
    return {"ok": True, **assistant_state()}


async def internal_assistant(request: Request):
    if request.method == "GET":
        return assistant_state()
    d = await adm.body(request)
    src = re.sub(r"[^a-z0-9\-]", "", str(d.pop("source", "intern")))[:20] or "intern"
    return assistant_update(d, f"internal:{src}")


async def api_assistant(request: Request):
    if request.method == "GET":
        return assistant_state()
    return assistant_update(await adm.body(request), adm.who(request))


# ------------------------------------------------------------------ Seiten und Zusatz-Skript
async def docker_page(request: Request):
    name = request.path_params["name"]
    if not re.fullmatch(r"[a-z\-]+\.(html|js|css)", name) or not (PAGES / name).is_file():
        raise HTTPException(404)
    return FileResponse(PAGES / name, headers={"Cache-Control": "no-cache"})


async def index_plus(request: Request):
    html = (adm.STATIC / "index.html").read_text(encoding="utf-8")
    html = html.replace("</body>", '<script src="/static/docker/admin-extra.js"></script>\n</body>', 1)
    return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})


NEW = [
    APIRoute("/api/auth/state", auth_state, methods=["GET"]),
    APIRoute("/api/services/{name}/restart", service_restart, methods=["POST"]),
    APIRoute("/api/tts-test", tts_test, methods=["POST"]),
    APIRoute("/api/setup", setup_get, methods=["GET"]),
    APIRoute("/internal/assistant", internal_assistant, methods=["GET", "POST"]),
    APIRoute("/api/assistant", api_assistant, methods=["GET", "POST"]),
    APIRoute("/api/setup/ollama", setup_ollama_probe, methods=["POST"]),
    APIRoute("/api/setup/apply", setup_apply, methods=["POST"]),
    APIRoute("/api/setup/language", setup_language, methods=["POST"]),
    APIRoute("/api/setup/models", setup_models, methods=["GET"]),
    APIRoute("/api/pairing/new", pairing_new, methods=["POST"]),
    APIRoute("/api/pairing/devices", pairing_devices, methods=["GET"]),
    APIRoute("/api/pairing/revoke", pairing_revoke, methods=["POST"]),
    APIRoute("/static/docker/{name}", docker_page, methods=["GET"]),
    APIRoute("/", index_plus, methods=["GET"]),
]
app.router.routes[0:0] = NEW


if __name__ == "__main__":
    import uvicorn
    jc.ensure_certs()
    adm.CTL_DIR.mkdir(parents=True, exist_ok=True)
    adm.load_sessions()
    adm.ensure_setup_code()
    if not adm.auth_configured():
        try:
            code = adm.SETUP_FILE.read_text().strip()
            print(f"[nuorb-admin] ===== Einrichtungscode / setup code: {code} =====", flush=True)
        except OSError:
            pass
    adm.ensure_internal_token()
    uvicorn.run(app, host=jc.env("ADMIN_HOST", "0.0.0.0"), port=int(jc.env("ADMIN_PORT", "8444")),
                log_level="warning", proxy_headers=False, server_header=False, **jc.ssl_kwargs())
