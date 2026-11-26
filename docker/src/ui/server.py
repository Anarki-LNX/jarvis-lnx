#!/usr/bin/env python3
"""JARVIS LNX – Web-Oberflaeche (Server).

Laeuft im Container als Benutzer hermes, HTTPS auf Port 8443, nur LAN.
Liefert die statische App aus und ist der einzige Weg des Browsers zu:
  * Hermes-API-Server (127.0.0.1:8642) – Runs, SSE-Events, Approvals. Der Bearer-Key
    wird aus ~/.hermes/.env gelesen und verlaesst den Server nie.
  * STT-Router (127.0.0.1:8178, OpenAI-kompatibel, Parakeet).
  * Piper-TTS (im Prozess, Stimme resident).
  * Ollama auf dem PC – nur als Erreichbarkeits-Probe („Gehirn online“).

Start: ~/jarvis-ui/venv/bin/python -I ~/jarvis-ui/server.py
"""
from __future__ import annotations

import asyncio
import io
import ipaddress
import json
import os
import re
import secrets
import sys
import time
import wave
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))  # python -I laesst das Skriptverzeichnis weg
import demo_runs  # noqa: E402
HOME = Path.home()
HERMES_URL = os.environ.get("HERMES_URL", "http://127.0.0.1:8642")
STT_URL = os.environ.get("STT_URL", "http://127.0.0.1:8178/v1/audio/transcriptions")
# Startwert (Env BRAIN_URL); massgeblich ist providers.pc-ollama.api in der Hermes-Konfiguration (siehe brain_url())
BRAIN_URL = os.environ.get("BRAIN_URL", "http://ollama:11434/api/version")
HERMES_CONFIG = Path(os.environ.get("HERMES_CONFIG", str(Path.home() / ".hermes/config.yaml")))
_brain_cache: dict = {"mtime": None, "url": BRAIN_URL, "api": ""}
_hcfg = {"mtime": None, "data": {}}


def hermes_cfg() -> dict:
    """Hermes-Konfiguration (YAML), bei geaenderter Dateizeit neu gelesen; Fehler -> letzter Stand."""
    try:
        mt = HERMES_CONFIG.stat().st_mtime_ns
        if mt != _hcfg["mtime"]:
            import yaml
            _hcfg["data"] = yaml.safe_load(HERMES_CONFIG.read_text(encoding="utf-8")) or {}
            _hcfg["mtime"] = mt
    except Exception as exc:
        if _hcfg["mtime"] != "fehler":
            print(f"config.yaml nicht lesbar ({exc.__class__.__name__}), nutze letzten Stand", flush=True)
        _hcfg["mtime"] = "fehler"
    return _hcfg["data"] if isinstance(_hcfg["data"], dict) else {}


def smarthome_enabled() -> bool:
    """Smart-Home-MCP (Sitzung ki-backend) ist nur aktiv, wenn mcp_servers.smarthome.enabled: true."""
    srv = (hermes_cfg().get("mcp_servers") or {}).get("smarthome")
    return isinstance(srv, dict) and srv.get("enabled") is True


def _start_api() -> str:
    """Startwert aus Env BRAIN_URL (alt: …/api/version, neu: …/v1) -> OpenAI-Basis …/v1."""
    u = BRAIN_URL.rstrip("/")
    return re.sub(r"/api/version$", "", u) + ("" if u.endswith("/v1") else "/v1")


BRAIN_SAVED_FILE = Path(os.environ.get("BRAIN_SAVED_FILE", str(HOME / "jarvis-admin/data/brain.json")))


def brain_provider() -> dict:
    """Lokales Gehirn nach Vertrag docs/llm-backends.md (§1.3/§1.6): Anbieter providers.pc-ollama in der Hermes-
    Konfiguration (api, name, api_key); Typ aus NuOrbs eigenen Daten brain_saved.local.type (Datei der Verwaltung,
    Env BRAIN_SAVED_FILE) – „ollama“ | „openai“, fehlt er: ollama. Env BRAIN_PROVIDER waehlt einen anderen Schluessel."""
    provs = hermes_cfg().get("providers") or {}
    key = os.environ.get("BRAIN_PROVIDER", "").strip() or "pc-ollama"
    p = provs.get(key) if isinstance(provs.get(key), dict) else {}
    saved = _read_json(BRAIN_SAVED_FILE, {}) if BRAIN_SAVED_FILE.exists() else {}
    local = saved.get("local") if isinstance(saved, dict) and isinstance(saved.get("local"), dict) else {}
    api = str(p.get("api") or p.get("base_url") or local.get("base_url") or "").strip().rstrip("/")
    if not re.fullmatch(r"https?://[\w.\-\[\]:]+(/[\w.\-/]*)?", api):
        api = _brain_cache.get("api") or _start_api()
    if not api.endswith("/v1"):
        api += "/v1"
    _brain_cache["api"] = api
    typ = str(local.get("type") or "ollama").strip().lower()
    typ = typ if typ in ("ollama", "openai") else "ollama"
    ak = p.get("api_key") if isinstance(p.get("api_key"), str) else ""
    if not ak and isinstance(p.get("key_env"), str):  # Vertrag §1.3: api_key oder key_env
        ak = hermes_env(p["key_env"].strip())
    name = str(p.get("name") or local.get("server") or "").strip()[:60]
    return {"key": key, "api": api, "type": typ, "api_key": ak, "name": "Ollama" if typ == "ollama" else (name or "OpenAI-kompatibel")}


def brain_url() -> str:
    """Pruefadresse des lokalen Gehirns: OpenAI-kompatibel {api}/models (gilt auch fuer Ollama)."""
    return brain_provider()["api"] + "/models"


async def brain_probe() -> tuple[bool, dict]:
    """§1.6: ollama -> online/Version ueber /api/version; openai -> online ueber {api}/models (mit Key), Version nur wo
    der Server sie verraet (llama.cpp /props.build_info, vLLM /version), sonst ausblenden. Ollama-Endpunkte werden bei
    openai nie aufgerufen."""
    bp = brain_provider()
    info = {"type": bp["type"], "provider": bp["key"], "server": bp["name"], "models": None, "version": None}
    root = re.sub(r"/v1$", "", bp["api"])
    if bp["type"] == "ollama":
        ok, vdata = await _probe(root + "/api/version")
        if ok and isinstance(vdata, dict):
            info["version"] = vdata.get("version")
        return ok, info
    hdr = {"Authorization": f"Bearer {bp['api_key']}"} if bp["api_key"] else None
    ok, data = await _probe(bp["api"] + "/models", headers=hdr)
    models = data.get("data") if isinstance(data, dict) else None
    ok = ok and isinstance(models, list)
    if ok:
        info["models"] = len(models)
        pok, props = await _probe(root + "/props", headers=hdr)                    # llama.cpp
        if pok and isinstance(props, dict) and props.get("build_info"):
            info["version"] = str(props["build_info"])[:40]
        else:
            vok, ver = await _probe(root + "/version", headers=hdr)                # vLLM
            if vok and isinstance(ver, dict) and ver.get("version"):
                info["version"] = str(ver["version"])[:40]
    return ok, info


PIPER_VOICE = os.environ.get(
    "PIPER_VOICE", str(HOME / ".hermes/cache/piper-voices/de_DE-thorsten-medium.onnx"))
HOST = os.environ.get("UI_HOST", "0.0.0.0")
PORT = int(os.environ.get("UI_PORT", "8443"))
# demo = simulierte Runs (kein LLM-Aufruf, Standard!), live = echte Hermes-Runs
MODE = "live" if os.environ.get("JARVIS_MODE", "demo").strip().lower() == "live" else "demo"
CERT_DIR = Path(os.environ.get("UI_CERT_DIR", str(BASE / "certs")))
MAX_AUDIO = 20 * 1024 * 1024
ALLOWED_NETS = [ipaddress.ip_network(n) for n in os.environ.get(
    "UI_ALLOWED_NETS", "127.0.0.0/8,::1/128,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12").split(",")]

PERSONA = (
    "Du sprichst ueber die JARVIS-Sprachoberflaeche auf dem Handy des Nutzers. "
    "Antworte immer auf Deutsch und duze den Nutzer, knapp, natuerlich und gesprochen: meist ein bis drei Saetze, "
    "kein Markdown, keine Tabellen, keine Aufzaehlungszeichen, keine Emojis, keine URLs vorlesen. "
    "Uhrzeiten exakt nennen, in der Form 'zwoelf Uhr siebenundzwanzig'. Ton: ruhig, kompetent, mit einer "
    "Prise trockenem Humor – wie ein britischer Butler mit Ingenieursdiplom. "
    "Vor gefaehrlichen oder unumkehrbaren Aktionen kurz sagen, was du vorhast. "
    "Jede Nachricht beginnt mit einer internen Systeminfo in eckigen Klammern (Uhrzeit, Datum, Geraet, Weckwort). "
    "Nutze sie, aber lies sie nie vor und zitiere sie nie, auch nicht teilweise. "
    "Geraeteaktionen am Handy (WLAN, Helligkeit, Lautstaerke, Bildschirm, Neustart, Ausschalten) fuehrst du NIE selbst aus "
    "und behauptest nie, sie seien erledigt: Rufe dafuer immer das Werkzeug mcp__geraet__anfordern auf (aktion und bei Helligkeit/Lautstaerke "
    "wert 0-100) und sage danach nur kurz, dass die Handy-Oberflaeche es ausfuehrt. "
    "Die Systeminfo nennt auch das Weckwort dieses Geraets und ob es an oder aus ist ('kein Weckwort' heisst: hier gibt es "
    "keins). Fragt der Nutzer danach oder wundert sich, dass es nicht reagiert, und es ist aus: erklaere, dass er es im "
    "Geraete-Panel (Zahnrad oben) mit dem Schalter 'Wecken mit …' einschaltet oder sagt: 'Schalte das Weckwort ein'. Das Mikro "
    "hoert dann staendig mit, aber nichts wird gespeichert oder gesendet, bevor das Wort erkannt ist. Gibt es kein "
    "Weckwort, sag, dass er zum Sprechen einfach den Orb antippt."
)


# --------------------------------------------------------------------------- Einstellungen (ui.json)
# Geschrieben von jarvis-admin (atomar). Wird bei Bedarf gelesen (mtime-Cache); fehlt die Datei oder ist ein Feld
# ungueltig, gelten die Konstanten/Umgebungsvariablen oben. Felder:
#   mode: "live"|"demo"   persona: str (<= 4000 Z.; jede Aenderung kostet einmal ~8 s Prompt-Cache)
#   piper_voice: Name in ~/.hermes/cache/piper-voices/ oder absoluter .onnx-Pfad   length_scale: 0.5–2.0
#   reasoning_voice: bool (Denkphase bei Sprach-Runs; Standard false)
#   brain_mode: "local"|"auto"|"remote", brain_model: str  (nur Anzeige/Status; die Umschaltung macht jarvis-admin)
UI_CONFIG = Path(os.environ.get("UI_CONFIG", str(HOME / ".config/jarvis/ui.json")))
_cfg_cache: dict = {"mtime": None, "data": {}}


def cfg() -> dict:
    try:
        mtime = UI_CONFIG.stat().st_mtime_ns
    except OSError:
        _cfg_cache.update(mtime=None, data={})
        return {}
    if mtime != _cfg_cache["mtime"]:
        try:
            raw = json.loads(UI_CONFIG.read_text(encoding="utf-8"))
            data = raw if isinstance(raw, dict) else {}
        except Exception as exc:
            print(f"ui.json unlesbar, nutze Standardwerte: {exc}", flush=True)
            data = {}
        _cfg_cache.update(mtime=mtime, data=data)
    return _cfg_cache["data"]


def cur_mode() -> str:
    m = str(cfg().get("mode", MODE)).strip().lower()
    return m if m in ("live", "demo") else MODE


SMARTHOME_PERSONA = (
    "Licht, Steckdosen, Schalter, Szenen und Sensoren im Haus (Home Assistant, ioBroker) sind KEINE Handy-Aktionen: "
    "Fragen dazu beantwortest du immer mit mcp__smarthome__geraete/zustand/raeume, Schalten mit "
    "mcp__smarthome_schalten__schalten/szene (der Nutzer bestaetigt auf dem Bildschirm); rufe das Werkzeug ohne "
    "vorherigen Text auf.")


def cur_persona() -> str:
    p = cfg().get("persona")
    p = p.strip()[:4000] if isinstance(p, str) and p.strip() else PERSONA
    uc = ui_cfg()
    if uc["assistant_name"] != "JARVIS":  # Name nur einsetzen, wenn geaendert (sonst bleibt der Prompt-Cache gleich)
        wake = uc["wake_phrase"] or "Hey " + (uc["brand"].capitalize() if uc["brand"].isupper() else uc["brand"])
        p = p.replace("Hey Jarvis", wake).replace("JARVIS", uc["assistant_name"])
        p = f"Du heisst {uc['assistant_name']}; so spricht dich der Nutzer an. " + p
    if smarthome_enabled():  # nur dann – sonst bleibt der Prompt (und sein Cache) unveraendert
        p += " " + SMARTHOME_PERSONA
    return p


def cur_reasoning() -> bool:
    return cfg().get("reasoning_voice") is True


def cur_voice() -> str:
    v = cfg().get("piper_voice")
    if isinstance(v, str) and v.strip():
        v = v.strip()
        path = Path(v) if v.startswith("/") else HOME / ".hermes/cache/piper-voices" / (v if v.endswith(".onnx") else v + ".onnx")
        if path.is_file() and Path(str(path) + ".json").is_file():
            return str(path)
    return PIPER_VOICE


def cur_length_scale() -> float:
    try:
        x = float(cfg().get("length_scale", 0.95))
        return x if 0.5 <= x <= 2.0 else 0.95
    except (TypeError, ValueError):
        return 0.95


def hermes_env(name: str) -> str:
    """Wert aus der Umgebung oder ~/.hermes/.env (fuer providers.<x>.key_env laut docs/llm-backends.md)."""
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,63}", name or ""):
        return ""
    val = os.environ.get(name, "")
    env = HOME / ".hermes/.env"
    if not val and env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.match(rf"\s*{name}\s*=\s*(.*)\s*$", line)
            if m:
                val = m.group(1).strip().strip('"').strip("'")
    return val


def hermes_key() -> str:
    key = os.environ.get("API_SERVER_KEY", "")
    env = HOME / ".hermes/.env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.match(r"\s*API_SERVER_KEY\s*=\s*(.*)\s*$", line)
            if m:
                key = m.group(1).strip().strip('"').strip("'")
    return key


client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(_app):
    global client
    client = httpx.AsyncClient(timeout=httpx.Timeout(30, connect=2))
    # Stimme vorwaermen, damit der erste Satz nicht 1–2 s Ladezeit kostet. Im Docker-Image laedt ein anderer Dienst
    # die Stimmen erst beim ersten Start herunter: dann ruhig warten statt FileNotFoundError ins Log zu schreiben.
    warm = asyncio.create_task(warm_voice())
    yield
    warm.cancel()
    await client.aclose()


app = FastAPI(title="JARVIS UI", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
_status_cache: dict = {"t": 0.0, "data": None}


@app.middleware("http")
async def lan_only(request: Request, call_next):
    try:
        ip = ipaddress.ip_address((request.client.host if request.client else "0.0.0.0").split("%")[0])
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        ok = any(ip in n for n in ALLOWED_NETS)
    except ValueError:
        ok = False
    if not ok:
        return JSONResponse({"error": "nur im Heimnetz erreichbar"}, status_code=403)
    # Kopplungspflicht (wie im Docker-Image). Auf jarvis vorerst aus (JARVIS_REQUIRE_PAIRING=0): Kiosk und LAN-Browser
    # haben keinen Token. Eingeschaltet brauchen alle /api/* ausser info/pair einen Geraete-Token.
    path = request.url.path
    if pairing_required() and path.startswith("/api/") and path not in PAIR_PUBLIC and device_for_request(request) is None:
        return JSONResponse({"detail": "pairing_required"}, status_code=401)
    if not pairing_required() and path.startswith("/api/") and device_token(request):
        device_for_request(request)  # „zuletzt gesehen“ auch ohne Kopplungspflicht nachfuehren (Kachel „Phones“)
    if path == "/api/status":  # Diagnose: kommt ein Geraete-Token mit? (je IP hoechstens alle 10 min eine Zeile)
        cip = request.client.host if request.client else "?"
        if time.time() - _tokdiag.get(cip, 0) > 600:
            _tokdiag[cip] = time.time()
            tk = device_token(request)
            src = "Bearer" if request.headers.get("authorization", "").lower().startswith("bearer ") else "Cookie" if tk else "-"
            print(f"[geraet] {cip}: Token {('gueltig' if device_for_request(request) else 'ungueltig') + ' (' + src + ')' if tk else 'keiner'}", flush=True)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Permissions-Policy", "microphone=(self), camera=()")
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    elif request.url.path.endswith((".js", ".css", ".html", ".webmanifest")) or request.url.path == "/":
        resp.headers["Cache-Control"] = "no-cache"  # Kiosk-Browser soll neue Versionen sofort holen
    return resp


def _auth() -> dict:
    return {"Authorization": f"Bearer {hermes_key()}"}


# --------------------------------------------------------------------------- Status
async def _probe(url: str, timeout: float = 1.2, headers: dict | None = None) -> tuple[bool, dict | None]:
    try:
        r = await client.get(url, timeout=timeout, headers=headers)
        try:
            data = r.json()
        except Exception:
            data = None
        return r.status_code < 400, data
    except Exception:
        return False, None


@app.get("/api/status")
async def status():
    now = time.monotonic()
    if _status_cache["data"] and now - _status_cache["t"] < 3:
        return _status_cache["data"]
    await discover_rooms()
    (brain, bdata), (hermes, _), (stt, sdata) = await asyncio.gather(
        brain_probe(), _probe(f"{HERMES_URL}/health"),
        _probe(STT_URL.replace("/v1/audio/transcriptions", "/health")))
    # Gehirn-Schalter aus jarvis-admin (ui.json): local | auto | remote; fehlt er, gilt „local“ (bisheriges Verhalten)
    bm = str(cfg().get("brain_mode", "local")).strip().lower()
    bm = bm if bm in ("local", "auto", "remote") else "local"
    effective = "remote" if bm == "remote" or (bm == "auto" and not brain) else "local"
    model = cfg().get("brain_model")
    data = {
        "brain_mode": bm, "brain_effective": effective,
        "brain_model": str(model)[:80] if isinstance(model, str) and model.strip() else None,
        "brain_model_remote": (str(cfg().get("brain_model_remote"))[:80] if isinstance(cfg().get("brain_model_remote"), str) else None),
        # nutzbar = Hermes laeuft und (bei lokal) der PC antwortet
        "brain_ok": bool(hermes and (brain or effective == "remote")),
        "brain": brain, "brain_version": (bdata or {}).get("version"),
        "brain_type": (bdata or {}).get("type"), "brain_models": (bdata or {}).get("models"),
        "brain_server": (bdata or {}).get("server"),
        "hermes": hermes, "stt": stt, "stt_backend": (sdata or {}).get("backend"),
        "tts": tts_engine.ready, "time": datetime.now().isoformat(timespec="seconds"), "mode": cur_mode(),
        "voice": Path(tts_engine.path).stem,
        "wake_word": cfg().get("wake_word") is True,
        **ui_cfg(), "onboarding": onboarding_due(), "onboarded": not onboarding_due(), "user_name": None,
        "features": {"zuhause": feature("zuhause"), "geraet": feature("geraet"), "cloud_weiche": feature("cloud_weiche")},
        "rooms": custom_rooms(),
        # Gespraechsmodus: nach der Antwort nachfragen und weiter zuhoeren (Standard an), Wartezeit bis Sprachbeginn
        "follow_up": cfg().get("follow_up") is not False,
        "follow_up_timeout_s": (int(cfg().get("follow_up_timeout_s")) if isinstance(cfg().get("follow_up_timeout_s"), int)
                                and 4 <= cfg().get("follow_up_timeout_s") <= 30 else 8),
    }
    _status_cache.update(t=now, data=data)
    return data


# --------------------------------------------------------------------------- STT
@app.post("/api/stt")
async def stt(audio: UploadFile = File(...)):
    blob = await audio.read()
    if len(blob) > MAX_AUDIO:
        raise HTTPException(413, "Aufnahme zu gross")
    if len(blob) < 800:
        return {"text": ""}
    files = {"file": (audio.filename or "aufnahme.webm", blob, audio.content_type or "application/octet-stream")}
    t0 = time.monotonic()
    try:
        r = await client.post(STT_URL, files=files,
                              data={"model": "parakeet", "language": "de", "response_format": "json"},
                              timeout=30)
    except Exception as exc:
        raise HTTPException(502, f"Spracherkennung nicht erreichbar: {exc.__class__.__name__}")
    if r.status_code >= 400:
        raise HTTPException(502, f"Spracherkennung meldet {r.status_code}")
    text = (r.json().get("text") or "").strip()
    # Parakeet hoert „Jarvis“ gern als „Javis“/„Jervis“
    text = re.sub(r"\b(J[ae]?r?vis|Dscharvis|Tscharvis|Jarwis)\b", "Jarvis", text, flags=re.I)
    text = re.sub(r"^(Ja,?\s*wi(ss?t?|s)|Ja,?\s*wis|Jawi(ss?t?)|Tschawis|Jawis)\b", "Jarvis", text, flags=re.I)
    return {"text": text, "ms": int((time.monotonic() - t0) * 1000)}


# --------------------------------------------------------------------------- Hermes-Runs
def _new_session() -> str:
    return f"jarvis-ui-{datetime.now():%Y%m%d-%H%M}-{secrets.token_hex(3)}"


# Geraete-Weiche (Nutzerentscheid 24.11., „Über Haiku“): frei formulierte Geraetebefehle, die die lokalen Muster am
# Handy nicht fangen, laufen ueber Claude Haiku statt Gemma (6/6 richtig, ~4 s, ~0,5-0,8 US-Cent). Alles andere wie gehabt.
DEVICE_WORDS = re.compile(
    r"\b(licht|hell|heller|helligkeit|dunkel|dunkler|display|bildschirm|laut|lauter|lautstärke|leise|leiser|ton|töne|stumm"
    r"|w-?lan|wifi|wi-fi|internet|netz|neu ?start\w*|neustart|ausschalt\w*|abschalt\w*|herunterfahr\w*|runterfahr\w*"
    r"|handy|smartphone|telefon"
    # Wetter (eigene Station, Werkzeug mcp__wetter__station) – falls das lokale Muster am Handy nicht greift
    r"|wetter|temperatur|grad|regen\w*|regnet|schnee|schneit|frost|glätte|glatteis|wind|sturm|gewitter|warm|kalt"
    # Haus (Server zuhause/zuhause_schalten): Heizung, Raeume, Klima, Energie – v. a. Schreibsaetze („Stell das Bad auf 22 Grad“)
    r"|puffer|laddomat|pumpe\w*|heizung\w*|heizkreis\w*|ofen|holzofen|wärmer|kälter|klima\w*|raum|räume|zimmer"
    r"|bad|badezimmer|schlafzimmer|küche|flur|gäste.?wc|solar\w*|photovoltaik|batterie|einspeis\w*|strom)\b", re.I)


# Fuer die Android-App nur Haus- und Wetterwoerter (dort gibt es keine Geraetesteuerung)
HOME_WORDS = re.compile(
    r"\b(wetter|temperatur|grad|regen\w*|regnet|schnee|schneit|frost|glätte|glatteis|wind|sturm|gewitter|warm|kalt"
    r"|puffer|laddomat|pumpe\w*|heizung\w*|heizkreis\w*|ofen|holzofen|wärmer|kälter|klima\w*|raum|räume|zimmer"
    r"|bad|badezimmer|schlafzimmer|küche|flur|gäste.?wc|solar\w*|photovoltaik|batterie|einspeis\w*|strom)\b", re.I)


# --------------------------------------------------------------------------- Feature-Flags und Raumnamen
# Standard: alles an (Installation jarvis). Generisches Docker-Image: JARVIS_FEATURE_ZUHAUSE=0 / JARVIS_FEATURE_GERAET=0
# oder ui.json features_zuhause/features_geraet = false. Eigene Raumnamen stehen NIE im Code: ui.json "rooms" (Liste)
# oder automatisch vom Haus-Server (Liste aus dessen Antwort auf einen unbekannten Raum), 1 h zwischengespeichert.
def feature(name: str) -> bool:
    return os.environ.get(f"JARVIS_FEATURE_{name.upper()}", "1") != "0" and cfg().get(f"features_{name}") is not False


_rooms_cache = {"t": 0.0, "rooms": []}


def custom_rooms() -> list[str]:
    r = cfg().get("rooms")
    if isinstance(r, list):
        return [x.strip() for x in r if isinstance(x, str) and re.fullmatch(r"[\wäöüÄÖÜß .-]{1,30}", x.strip())][:30]
    return _rooms_cache["rooms"]


async def discover_rooms() -> None:
    if not feature("zuhause") or isinstance(cfg().get("rooms"), list) or time.monotonic() - _rooms_cache["t"] < 3600:
        return
    _rooms_cache["t"] = time.monotonic()
    d = await zuhause_satz("raeume", {"raum": "__liste__"})
    m = re.search(r"Es gibt:\s*([^.]+)", d.get("satz", ""))
    if m:
        _rooms_cache["rooms"] = [x.strip() for x in m.group(1).split(",") if re.fullmatch(r"[\wäöüÄÖÜß .-]{1,30}", x.strip())][:30]


def room_hit(text: str) -> bool:
    low = text.lower()
    return any(re.search(r"\b" + re.escape(r.lower()) + r"s?\b", low) for r in custom_rooms())


def device_model() -> str:
    m = cfg().get("device_model")
    return m if isinstance(m, str) and re.fullmatch(r"claude-[a-z0-9.-]{3,40}", m) else "claude-haiku-5-5"


@app.post("/api/ask")
async def ask(request: Request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "leer")
    session_id = body.get("session_id") or _new_session()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", session_id):
        raise HTTPException(400, "session_id ungueltig")
    if cur_mode() == "demo":
        return demo_runs.create(text, session_id)
    now = datetime.now().astimezone()
    # Zeit in den Nutzertext, NICHT in instructions: instructions stehen vorn im System-Prompt, jede Aenderung
    # dort entwertet den Prompt-Cache (~10k Token, ~8 s Prefill). So bleibt das Praefix identisch.
    # Interne Systeminfo (Persona: nie vorlesen/zitieren). Weckwort je Client: die UI meldet, ob es hier eins gibt und wie
    # es heisst (NuOrb-App: wakePhrase/wakeVerfuegbar, Kiosk: Wake-Dienst); aeltere UIs ohne Angabe -> bisherige Logik.
    android = body.get("client") == "android"
    dev = body.get("device")
    parts = [f"Systeminfo, nicht vorlesen: {demo_runs.WOCHENTAGE[now.weekday()]}, {now:%d.%m.%Y}, {now:%H:%M} Uhr"]
    if android:
        parts.append("Client NuOrb-App ohne Gerätesteuerung")
    elif isinstance(dev, str) and dev.strip():  # Gerätestatus vom Smartphone, kurz und bereinigt
        parts.append("Smartphone: " + re.sub(r"[^\w %,.°äöüÄÖÜß-]", "", dev)[:140])
    avail = body.get("wake_available")
    uc = ui_cfg()
    phrase = (re.sub(r"[^\w .äöüÄÖÜß-]", "", str(body.get("wake_phrase") or "")).strip()[:30] or uc["wake_phrase"]
              or "Hey " + (uc["brand"].capitalize() if uc["brand"].isupper() else uc["brand"]))  # wie cur_persona
    on = (body.get("wake") is True) if android else (cfg().get("wake_word") is True)
    if avail is False:
        parts.append("kein Weckwort")
    elif on:
        parts.append(f"Weckwort „{phrase}“ an")
    else:
        parts.append("Weckwort aus")
    zeit = "[" + "; ".join(parts) + "]"
    payload = {"input": f"{zeit} {text}", "session_id": session_id, "instructions": cur_persona(),
               # Sprach-Runs ohne Denkphase: ~10x schneller bis zum ersten Satz (Messung ki-backend)
               "model_options": {"reasoning": {"enabled": cur_reasoning()}}}
    # Gehirn-Schalter: bei „remote“ Modell pro Run mitschicken (/v1/runs honoriert das immer) -> wirkt sofort,
    # auch bevor jarvis-admin das Gateway neu gestartet hat. Bei local/auto gilt die globale Hermes-Config.
    bm, bmod = str(cfg().get("brain_mode", "")).lower(), cfg().get("brain_model")
    route = "standard"
    if bm == "remote" and isinstance(bmod, str) and re.fullmatch(r"claude-[a-z0-9.-]{3,40}", bmod):
        payload.update(provider="anthropic", model=bmod)
        route = "remote"
    # Cloud-Weiche abschaltbar (JARVIS_FEATURE_CLOUD_WEICHE=0 bzw. ui.json features_cloud_weiche=false), z. B. im
    # generischen Image oder wenn „lokal“ strikt lokal bleiben soll. Standard an (Nutzerentscheid „Über Haiku“, 24.11.).
    elif (body.get("no_haiku") is not True and feature("cloud_weiche")
          and ((HOME_WORDS if android else DEVICE_WORDS).search(text) or room_hit(text))):
        payload.update(provider="anthropic", model=device_model())
        route = "geraet"

    async def start(p):
        return await client.post(f"{HERMES_URL}/v1/runs", json=p, headers={
            **_auth(), "Idempotency-Key": f"ui-{secrets.token_urlsafe(18)}"}, timeout=15)
    try:
        r = await start(payload)
        if route == "geraet" and r.status_code >= 400:  # Haiku nicht startbar -> gleicher Satz an Gemma
            print(f"Geraete-Weiche: Haiku-Start {r.status_code}, weiter mit Standard-Gehirn", flush=True)
            payload.pop("provider", None); payload.pop("model", None); route = "standard"
            r = await start(payload)
    except Exception:
        raise HTTPException(503, "Hermes nicht erreichbar")
    if r.status_code >= 400:
        detail = r.text[:300]
        raise HTTPException(r.status_code if r.status_code in (409, 429, 503) else 502, detail)
    data = r.json()
    if route == "geraet":
        print(f"Geraete-Weiche: {payload['model']} fuer {text[:60]!r}", flush=True)
    return {"run_id": data.get("run_id"), "session_id": session_id, "status": data.get("status"), "route": route}


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, request: Request):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", run_id):
        raise HTTPException(400, "run_id ungueltig")
    if run_id.startswith("demo_"):
        return StreamingResponse(demo_runs.events(run_id), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    async def gen():
        yield b": verbunden\n\n"
        try:
            async with client.stream("GET", f"{HERMES_URL}/v1/runs/{run_id}/events", headers=_auth(),
                                     timeout=httpx.Timeout(None, connect=3)) as r:
                if r.status_code >= 400:
                    err = {"event": "run.failed", "run_id": run_id, "error": f"Hermes {r.status_code}"}
                    yield f"data: {json.dumps(err)}\n\n".encode()
                    return
                # Hermes-SSE -> schlanke data-Zeilen; der Ereignisname steckt bereits im JSON ("event")
                async for line in r.aiter_lines():
                    if await request.is_disconnected():
                        break
                    if line.startswith("data:"):
                        yield f"{line}\n\n".encode()
                    elif line.startswith(":"):
                        yield b": ping\n\n"
        except Exception as exc:
            err = {"event": "run.failed", "run_id": run_id, "error": f"Verbindung: {exc.__class__.__name__}"}
            yield f"data: {json.dumps(err)}\n\n".encode()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/runs/{run_id}")
async def run_status(run_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", run_id):
        raise HTTPException(400, "run_id ungueltig")
    if run_id.startswith("demo_"):
        return demo_runs.status(run_id)
    r = await client.get(f"{HERMES_URL}/v1/runs/{run_id}", headers=_auth(), timeout=5)
    return JSONResponse(r.json(), status_code=r.status_code)


@app.post("/api/runs/{run_id}/approval")
async def run_approval(run_id: str, request: Request):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", run_id):
        raise HTTPException(400, "run_id ungueltig")
    body = await request.json()
    choice = body.get("choice")
    if choice not in ("once", "deny"):  # Oberflaeche erlaubt bewusst nur Einzelfreigabe oder Ablehnung
        raise HTTPException(400, "nur once/deny")
    if run_id.startswith("demo_"):
        res = demo_runs.approve(run_id, choice)
        return JSONResponse(res, status_code=res.pop("_status", 200))
    out = {"choice": choice}
    if body.get("request_id"):
        out["request_id"] = str(body["request_id"])[:256]
    if body.get("execution_generation") is not None:
        out["execution_generation"] = body["execution_generation"]
    else:
        # Kanonischer Modus braucht die exakte Generation – aus dem Run-Status nachladen
        st = await client.get(f"{HERMES_URL}/v1/runs/{run_id}", headers=_auth(), timeout=5)
        try:
            for c in (st.json().get("pending_controls") or []):
                if not out.get("request_id") or c.get("prompt_id") == out["request_id"]:
                    out["request_id"] = c.get("prompt_id") or out.get("request_id")
                    out["execution_generation"] = c.get("execution_generation")
                    break
        except Exception:
            pass
    r = await client.post(f"{HERMES_URL}/v1/runs/{run_id}/approval", json=out, headers=_auth(), timeout=10)
    if r.status_code >= 400 and out.get("request_id") and out.get("execution_generation") is not None:
        # MCP-Trust-Abfragen (pattern mcp_elicitation) sind laut Doku auch ueber /clarify aufloesbar
        alt = {"request_id": out["request_id"], "execution_generation": out["execution_generation"], "answer": choice}
        r2 = await client.post(f"{HERMES_URL}/v1/runs/{run_id}/clarify", json=alt, headers=_auth(), timeout=10)
        print(f"approval {r.status_code} -> clarify-Fallback {r2.status_code}", flush=True)
        if r2.status_code < 400:
            r = r2
    return JSONResponse(r.json() if r.headers.get("content-type", "").startswith("application/json")
                        else {"text": r.text[:300]}, status_code=r.status_code)


# Geraete-Absicht aus Hermes (MCP „geraet“ → anfordern). tool.completed.preview ist in Hermes' Runs-Pfad leer (Bug,
# laut sprachsteuerung), daher das Werkzeugergebnis aus dem Sitzungsverlauf lesen und STRIKT validieren.
GERAET_AKTIONEN = {"wlan_an", "wlan_aus", "neustart", "ausschalten", "helligkeit", "lautstaerke", "bildschirm_aus", "bildschirm_an"}


@app.get("/api/geraet-aktion")
async def geraet_aktion(session_id: str, tool_call_id: str):
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", session_id) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", tool_call_id):
        raise HTTPException(400, "ungueltig")
    r = await client.get(f"{HERMES_URL}/api/sessions/{session_id}/messages", params={"inline_images": "false"},
                         headers=_auth(), timeout=8)
    if r.status_code >= 400:
        raise HTTPException(502, f"Hermes-Verlauf: {r.status_code}")
    raw = r.json()
    msgs = raw.get("data", raw.get("messages", [])) if isinstance(raw, dict) else raw
    msgs = [m for m in (msgs or []) if isinstance(m, dict)]
    idx = next((i for i, m in enumerate(msgs) if m.get("role") == "tool" and m.get("tool_call_id") == tool_call_id), None)
    if idx is None:
        return JSONResponse({"detail": "Werkzeugergebnis noch nicht im Verlauf"}, status_code=404)
    # Ab diesem Aufruf weitersuchen: Gemma ruft teils erst mit falschen Argumenten auf (Hermes verlangt „Retry“),
    # das gueltige Ergebnis steht dann in einem spaeteren Werkzeugergebnis desselben Turns.
    last_err = "keine GERAET_AKTION im Ergebnis"
    for m in msgs[idx:]:
        if m.get("role") == "user":
            break
        if m.get("role") != "tool" or "geraet" not in str(m.get("tool_name") or m.get("name") or "geraet"):
            continue
        content = m.get("content")
        if isinstance(content, list):
            content = " ".join(str(c.get("text", "")) if isinstance(c, dict) else str(c) for c in content)
        text = str(content or "")
        # Hermes verpackt MCP-Ergebnisse als JSON ({"result": "GERAET_AKTION {\"aktion\": …}"}) -> erst auspacken
        for st in [x.start() for x in re.finditer(r"\{\s*\"result\"", text)]:
            try:
                inner, _ = json.JSONDecoder().raw_decode(text[st:])
                if isinstance(inner, dict) and isinstance(inner.get("result"), str):
                    text = inner["result"] + "\n" + text
                    break
            except ValueError:
                continue
        hit = re.search(r"GERAET_AKTION\s*(\{[^{}]*\})", text)
        if not hit:
            continue
        try:
            d = json.loads(hit.group(1))
        except ValueError:
            last_err = "GERAET_AKTION unlesbar"
            continue
        aktion, wert = d.get("aktion"), d.get("wert")
        if aktion not in GERAET_AKTIONEN:
            raise HTTPException(422, f"unbekannte Aktion {str(aktion)[:30]}")
        if wert is not None and (not isinstance(wert, int) or isinstance(wert, bool) or not 0 <= wert <= 100):
            raise HTTPException(422, "wert muss eine ganze Zahl 0–100 sein")
        if aktion in ("helligkeit", "lautstaerke") and wert is None:
            raise HTTPException(422, "wert fehlt")
        return {"aktion": aktion, "wert": wert, "tool_call_id": m.get("tool_call_id")}
    return JSONResponse({"detail": last_err}, status_code=404)


@app.post("/api/runs/{run_id}/stop")
async def run_stop(run_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", run_id):
        raise HTTPException(400, "run_id ungueltig")
    if run_id.startswith("demo_"):
        demo_runs.stop(run_id)
        return {"status": 200}
    r = await client.post(f"{HERMES_URL}/v1/runs/{run_id}/stop", headers=_auth(), timeout=5)
    return JSONResponse({"status": r.status_code}, status_code=200 if r.status_code < 500 else 502)


# --------------------------------------------------------------------------- Gehirn-Schalter (via jarvis-admin)
# Die Umschalt-Logik liegt in jarvis-admin. Wir rufen dessen interne, nur per Loopback + Token erreichbare
# Schnittstelle auf (Server zu Server). Token-Datei legt jarvis-admin an; TLS gegen die Heim-CA geprueft.
ADMIN_URL = os.environ.get("ADMIN_URL", "https://127.0.0.1:8444")
# --------------------------------------------------------------------------- Kopplung (Einmal-Code -> Geraete-Token)
# Gleiches Format wie im Docker-Image (docker/app/jarvis_common.py). Codes schreibt jarvis-admin (pairing.json:
# {sha256(CODE): {exp, by, created}}), Geraete stehen in devices.json ({d_<hex12>: {name, platform, token: sha256,
# created, last_seen, ip}}). Beide Dateien 0600, atomar (tmp + rename), weil Verwaltung und UI schreiben.
import hashlib
import hmac

CONF_DIR = UI_CONFIG.parent
DEVICES_FILE = CONF_DIR / "devices.json"
PAIRING_FILE = CONF_DIR / "pairing.json"
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAIR_PUBLIC = {"/api/info", "/api/pair"}
DEVICE_COOKIE = "nuorb_device"
DEVICE_COOKIE_OLD = "jarvis_device"  # NuOrb-App < 1.3.3 und Docker-Image setzen noch diesen Namen
_pair_fails: dict[str, list[float]] = {}
_seen_cache: dict[str, float] = {}
_tokdiag: dict[str, float] = {}


def pairing_required() -> bool:
    return os.environ.get("JARVIS_REQUIRE_PAIRING", "0") != "0"


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def _write_json(p: Path, data) -> None:
    tmp = p.with_name(f".{p.name}.{secrets.token_hex(4)}")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def redeem_pairing_code(code: str) -> bool:
    c = "".join(ch for ch in str(code).upper() if ch in CODE_ALPHABET)
    if len(c) != 8:
        return False
    data = _read_json(PAIRING_FILE, {})
    h, hit = _sha(c), None
    for k, v in data.items():
        if hmac.compare_digest(k, h) and isinstance(v, dict) and v.get("exp", 0) > time.time():
            hit = k
    if not hit:
        return False
    data.pop(hit, None)  # nur einmal einloesbar
    _write_json(PAIRING_FILE, {k: v for k, v in data.items() if isinstance(v, dict) and v.get("exp", 0) > time.time()})
    return True


def device_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(DEVICE_COOKIE, "") or request.cookies.get(DEVICE_COOKIE_OLD, "")


# ACHTUNG: Name und Aufruf ueber das Modul-Global stabil lassen – das Docker-Image ersetzt device_for_request
# (Loopback mit internem Token gilt dort als gekoppelt); lan_only ruft es zur Laufzeit ueber den Modulnamen auf.
def device_for_request(request: Request) -> str | None:
    token = device_token(request)
    if not token or len(token) > 200:
        return None
    h, devs = _sha(token), _read_json(DEVICES_FILE, {})
    for did, v in devs.items():
        if isinstance(v, dict) and hmac.compare_digest(str(v.get("token", "")), h):
            if time.time() - _seen_cache.get(did, 0) > 60:  # „zuletzt gesehen“ hoechstens 1x pro Minute schreiben
                _seen_cache[did] = time.time()
                v["last_seen"] = datetime.now().astimezone().isoformat(timespec="seconds")
                v["ip"] = request.client.host if request.client else ""
                try:
                    _write_json(DEVICES_FILE, devs)
                except OSError as exc:
                    print(f"[pair] devices.json nicht schreibbar: {exc}", flush=True)
            return did
    return None


def server_name() -> str:
    """Name des Servers fuer QR/Kopplung – dieselbe Quelle wie jarvis-admin: JARVIS_NAME, sonst die Marke."""
    n = re.sub(r"[^\w .äöüÄÖÜß-]", "", os.environ.get("JARVIS_NAME", "")).strip()[:24]
    return n or ui_cfg()["brand"]


@app.get("/internal/devices")
async def internal_devices(request: Request):
    """Fuer die NuOrb-Verwaltung: gekoppelte Geraete mit „zuletzt gesehen“ (ohne Token-Hashes).
    Nur von Loopback und mit X-Jarvis-Internal (gleiches Token wie /internal/* der Verwaltung)."""
    host = request.client.host if request.client else ""
    try:
        tok = ADMIN_TOKEN_FILE.read_text().strip()
    except OSError:
        tok = ""
    given = request.headers.get("X-Jarvis-Internal", "")
    if host not in ("127.0.0.1", "::1") or not tok or not hmac.compare_digest(given.strip(), tok):
        raise HTTPException(403, "nur intern")
    devs = _read_json(DEVICES_FILE, {})
    return {"devices": {did: {k: v.get(k) for k in ("name", "platform", "created", "last_seen", "ip")}
                        for did, v in devs.items() if isinstance(v, dict)}, "now": datetime.now().astimezone().isoformat(timespec="seconds")}


@app.get("/api/info")
async def api_info(request: Request):
    uc = ui_cfg()
    return {"product": "jarvis-lnx", "api": 1, "name": server_name(), "brand": uc["brand"],
            "assistant_name": uc["assistant_name"], "ui_lang": uc["ui_lang"], "lang": "en" if uc["ui_lang"] == "en" else "de",
            "pairing_required": pairing_required(), "paired": device_for_request(request) is not None, "build": build_id()}


@app.post("/api/pair")
async def api_pair(request: Request):
    ip = request.client.host if request.client else ""
    fails = [t for t in _pair_fails.get(ip, []) if time.time() - t < 600]
    _pair_fails[ip] = fails
    if len(fails) >= 8:
        return JSONResponse({"detail": "too_many_attempts"}, status_code=429)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict) or not redeem_pairing_code(str(body.get("code", ""))):
        fails.append(time.time())
        print(f"[pair] falscher oder abgelaufener Code von {ip}", flush=True)
        return JSONResponse({"detail": "invalid_or_expired_code"}, status_code=403)
    name = re.sub(r"[\x00-\x1f<>]", "", str(body.get("device") or "Smartphone"))[:60]
    platform = re.sub(r"[^a-z0-9_-]", "", str(body.get("platform") or "web").lower())[:20]
    token, did = secrets.token_urlsafe(32), "d_" + secrets.token_hex(6)
    devs = _read_json(DEVICES_FILE, {})
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    devs[did] = {"name": name, "platform": platform, "token": _sha(token), "created": now, "last_seen": now, "ip": ip}
    _write_json(DEVICES_FILE, devs)
    print(f"[pair] Geraet gekoppelt: {did} {name!r} ({platform}) von {ip}", flush=True)
    uc = ui_cfg()
    resp = JSONResponse({"token": token, "device_id": did, "name": server_name(), "api": 1,
                         "lang": "en" if uc["ui_lang"] == "en" else "de"})
    if body.get("cookie") is True:
        for ck in (DEVICE_COOKIE, DEVICE_COOKIE_OLD):
            resp.set_cookie(ck, token, max_age=10 * 365 * 86400, httponly=True, secure=True, samesite="strict", path="/")
    return resp


@app.post("/api/unpair")
async def api_unpair(request: Request):
    did = device_for_request(request)
    if did:
        devs = _read_json(DEVICES_FILE, {})
        devs.pop(did, None)
        _write_json(DEVICES_FILE, devs)
        print(f"[pair] Geraet entkoppelt: {did}", flush=True)
    resp = JSONResponse({"ok": True, "removed": bool(did)})
    resp.delete_cookie(DEVICE_COOKIE, path="/")
    resp.delete_cookie(DEVICE_COOKIE_OLD, path="/")
    return resp


ADMIN_TOKEN_FILE = Path(os.environ.get("ADMIN_TOKEN_FILE", str(HOME / ".config/jarvis/internal.token")))


async def _admin(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    try:
        token = ADMIN_TOKEN_FILE.read_text().strip()
    except OSError:
        return 503, {"detail": "Umschalten vom Handy ist noch nicht eingerichtet – bitte im Admin-UI (:8444) umschalten."}
    try:
        async with httpx.AsyncClient(verify=str(CERT_DIR / "jarvis-ca.crt"), timeout=httpx.Timeout(60, connect=3)) as c:
            r = await c.request(method, ADMIN_URL + path, json=payload, headers={"X-Jarvis-Internal": token})
        try:
            data = r.json()
        except Exception:
            data = {"detail": r.text[:300]}
        if r.status_code == 404:
            data = {"detail": "Admin-UI kennt die Handy-Schnittstelle noch nicht – bitte im Admin-UI (:8444) umschalten."}
        return r.status_code, data if isinstance(data, dict) else {"data": data}
    except Exception as exc:
        return 503, {"detail": f"Admin-UI nicht erreichbar ({exc.__class__.__name__})."}


@app.get("/api/brain")
async def brain_get():
    code, data = await _admin("GET", "/internal/brain")
    data["available"] = code < 400
    data.setdefault("ui_mode", cfg().get("brain_mode", "local"))
    return JSONResponse(data, status_code=200)


@app.post("/api/brain")
async def brain_set(request: Request):
    body = await request.json()
    mode, claude = body.get("mode"), body.get("claude")
    if mode not in ("local", "auto", "remote") or (claude is not None and not re.fullmatch(r"claude-[a-z0-9.-]{3,40}", str(claude))):
        raise HTTPException(400, "Ungültiger Modus oder Modell.")
    code, data = await _admin("POST", "/internal/brain", {"mode": mode, "claude": claude, "source": "handy"})
    _status_cache["t"] = 0  # Status sofort neu
    print(f"Gehirn-Schalter vom Handy: {mode} {claude or ''} -> {code}", flush=True)
    return JSONResponse(data, status_code=code)


@app.post("/api/wake")
async def wake_set(request: Request):
    """Schalter „Hey Jarvis“ (ui.json wake_word, gehoert jarvis-admin) vom Handy aus umstellen."""
    body = await request.json()
    an = body.get("an")
    if not isinstance(an, bool):
        raise HTTPException(400, "Feld „an“ (true/false) fehlt.")
    code, data = await _admin("POST", "/internal/ui", {"wake_word": an, "source": "handy"})
    _status_cache["t"] = 0
    print(f"Wake-Word-Schalter vom Handy: {an} -> {code}", flush=True)
    return JSONResponse(data, status_code=code)


# Haus-Server von sprachsteuerung (zuhause_mcp.py --satz <werkzeug> '<json>'): nur LESEN, deterministisch, ohne LLM,
# fertiger Sprechsatz. Schreiben (Soll-Temperaturen, Klima) laeuft ausschliesslich ueber Hermes, damit Karten greifen.
ZUHAUSE_SKRIPT = HOME / ".hermes/projekt-claude/zuhause_mcp.py"
WETTER_ZEITRAUM = {"jetzt", "heute", "morgen", "uebermorgen", "woche"}
ZUHAUSE_LESEN = {"wetter": "zeitraum", "heizung": "was", "raeume": "raum", "klima": "geraet", "energie": None}


async def zuhause_satz(werkzeug: str, args: dict) -> dict:
    try:
        p = await asyncio.create_subprocess_exec(sys.executable, "-I", str(ZUHAUSE_SKRIPT), "--satz", werkzeug,
                                                 json.dumps(args, ensure_ascii=False),
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(p.communicate(), timeout=12)
    except asyncio.TimeoutError:
        p.kill()
        return {"ok": False, "satz": "Das Haus antwortet gerade nicht."}
    except OSError as exc:
        print(f"Zuhause: Skript nicht startbar ({exc})", flush=True)
        return {"ok": False, "satz": "Die Hausabfrage ist gerade nicht verfügbar."}
    satz = out.decode("utf-8", "replace").strip()[:900]
    if p.returncode not in (0, 1) or not satz or satz.startswith("Traceback"):
        print(f"Zuhause {werkzeug}: Exit {p.returncode}: {err.decode('utf-8', 'replace')[-300:]}", flush=True)
        return {"ok": False, "satz": "Die Hausabfrage ist gerade nicht verfügbar."}
    return {"ok": p.returncode == 0, "satz": satz, "werkzeug": werkzeug}


@app.post("/api/zuhause")
async def zuhause(request: Request):
    body = await request.json()
    if not feature("zuhause"):
        raise HTTPException(503, "Haus-Anbindung ist hier nicht eingerichtet.")
    w, args = body.get("werkzeug"), body.get("args") or {}
    if w not in ZUHAUSE_LESEN or not isinstance(args, dict):
        raise HTTPException(400, "Werkzeug ungültig (nur lesend: " + ", ".join(ZUHAUSE_LESEN) + ").")
    key = ZUHAUSE_LESEN[w]
    if set(args) - ({key} if key else set()):
        raise HTTPException(400, "Unbekanntes Argument.")
    v = args.get(key) if key else None
    if v is not None and (not isinstance(v, str) or not re.fullmatch(r"[\wäöüÄÖÜß .-]{0,40}", v)):
        raise HTTPException(400, "Argument ungültig.")
    if w == "wetter" and args.get("zeitraum", "jetzt") not in WETTER_ZEITRAUM:
        raise HTTPException(400, "Zeitraum ungültig.")
    return await zuhause_satz(w, {k: x for k, x in args.items() if x})


@app.post("/api/wetter")  # aelterer Weg (v.37), jetzt ueber den Haus-Server
async def wetter(request: Request):
    zr = (await request.json()).get("zeitraum", "jetzt")
    if zr not in WETTER_ZEITRAUM:
        raise HTTPException(400, "Zeitraum ungültig.")
    return await zuhause_satz("wetter", {"zeitraum": zr})


# Gleiche Schnittstelle wie im Docker-Image (Sitzung Docker-Server): GET/POST /api/assistant.
# Auf jarvis schreibt sie ueber jarvis-admin /internal/ui (assistant_name, onboarded); den Nutzernamen merkt sich Hermes
# (die UI schickt den Satz an /api/ask), user_name wird hier daher nur angenommen, nicht gespeichert.
def greeting_text(lang: str, name: str) -> str:
    if lang == "en":
        return f"My creator named me {name}. If that's too complicated, tell me what you'd like to call me."
    return f"Mein Schöpfer hat mich {name} getauft. Falls dir das zu kompliziert ist, sag mir, wie du mich nennen möchtest."


@app.get("/api/assistant")
async def assistant_get():
    uc = ui_cfg()
    return {"assistant_name": uc["assistant_name"], "brand": uc["brand"], "user_name": None,
            "onboarded": not onboarding_due(), "greeting": greeting_text(uc["ui_lang"], uc["assistant_name"])}


@app.post("/api/assistant")
async def assistant_set(request: Request):
    body = await request.json()
    if not isinstance(body, dict) or set(body) - {"assistant_name", "user_name", "onboarded"}:
        raise HTTPException(400, "Unbekanntes Feld.")
    d = {}
    if "assistant_name" in body:
        n = str(body["assistant_name"] or "").strip() or ui_cfg()["brand"]  # leer = zurueck zur Marke
        if not NAME_RE.fullmatch(n):
            raise HTTPException(400, "Name ungültig (1–24 Zeichen, Buchstaben, Ziffern, Leerzeichen, Punkt, Bindestrich).")
        d["assistant_name"] = n
    if "onboarded" in body:
        if not isinstance(body["onboarded"], bool):
            raise HTTPException(400, "onboarded muss true/false sein.")
        d["onboarded"] = body["onboarded"]
    if not d:
        return {"ok": True, "unchanged": True}
    code, data = await _admin("POST", "/internal/ui", {**d, "source": "handy"})
    _status_cache["t"] = 0
    print(f"Assistent vom Handy: {d} -> {code}", flush=True)
    return JSONResponse(data, status_code=code)


UI_SETTINGS = {"follow_up": bool, "follow_up_timeout_s": int, "assistant_name": str, "onboarded": bool}


@app.post("/api/setting")
async def setting_set(request: Request):
    """Weitere ui.json-Schalter vom Handy (Whitelist), ueber jarvis-admin /internal/ui."""
    body = await request.json()
    d = {k: v for k, v in body.items() if k in UI_SETTINGS and type(v) is UI_SETTINGS[k]}
    if "assistant_name" in d:
        d["assistant_name"] = d["assistant_name"].strip()
        if not NAME_RE.fullmatch(d["assistant_name"]):
            raise HTTPException(400, "Name ungültig (1–24 Zeichen, Buchstaben, Ziffern, Leerzeichen, Punkt, Bindestrich).")
    if not d or len(d) != len(body) or ("follow_up_timeout_s" in d and not 4 <= d["follow_up_timeout_s"] <= 30):
        raise HTTPException(400, "Unbekannte oder ungültige Einstellung.")
    code, data = await _admin("POST", "/internal/ui", {**d, "source": "handy"})
    _status_cache["t"] = 0
    print(f"Einstellung vom Handy: {d} -> {code}", flush=True)
    return JSONResponse(data, status_code=code)


# --------------------------------------------------------------------------- Client-Log
_clog_times: list[float] = []


@app.post("/api/clientlog")
async def clientlog(request: Request):
    now = time.monotonic()
    _clog_times[:] = [t for t in _clog_times if now - t < 10][-50:]
    if len(_clog_times) >= 50:
        return Response(status_code=429)
    _clog_times.append(now)
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400)
    msg = re.sub(r"[\x00-\x1f]", " ", str(body.get("msg", "")))[:400]
    ip = request.client.host if request.client else "?"
    print(f"[client {ip} v{str(body.get('v', '?'))[:20]}] {msg}", flush=True)
    return Response(status_code=204)


# --------------------------------------------------------------------------- Widgets
def _memory_notes(limit: int = 4) -> list[str]:
    notes: list[str] = []
    for name in ("MEMORY.md", "USER.md"):
        p = HOME / ".hermes/memories" / name
        if not p.exists():
            continue
        for chunk in re.split(r"\n?§\n?|\n{2,}", p.read_text(encoding="utf-8", errors="ignore")):
            s = re.sub(r"\s+", " ", chunk).strip(" -*#")
            if 8 <= len(s):
                notes.append(s[:140])
    return notes[-limit:][::-1]


@app.get("/api/widgets")
async def widgets():
    jobs: list[dict] = []
    try:
        r = await client.get(f"{HERMES_URL}/api/jobs", headers=_auth(), timeout=3)
        if r.status_code < 400:
            raw = r.json()
            items = raw.get("jobs", raw.get("data", raw)) if isinstance(raw, dict) else raw
            for j in items or []:
                if not isinstance(j, dict) or j.get("enabled") is False or j.get("paused"):
                    continue
                jobs.append({
                    "name": j.get("name") or (j.get("prompt") or "Aufgabe")[:60],
                    "next": j.get("next_run_at") or j.get("next_run"),
                    "schedule": j.get("schedule_display") or j.get("schedule"),
                })
    except Exception:
        pass
    jobs.sort(key=lambda j: str(j.get("next") or "~"))
    return {"jobs": jobs[:4], "notes": _memory_notes()}


# --------------------------------------------------------------------------- TTS (Piper)
def _ort_explicit_threads(ort) -> None:
    """Piper legt die ONNX-Session mit Standard-Optionen an (0 Threads = automatisch). Dann setzt onnxruntime die
    CPU-Affinitaet selbst und schreibt in Containern/LXC „pthread_setaffinity_np failed“ als [E] ins Log. Mit
    ausdruecklicher Thread-Zahl entfaellt das (gleiche Leistung)."""
    if getattr(ort, "_nuorb_threads", False):
        return
    orig = ort.InferenceSession

    class Session(orig):
        def __init__(self, path_or_bytes, sess_options=None, *args, **kwargs):
            if sess_options is None:
                sess_options = ort.SessionOptions()
            if not sess_options.intra_op_num_threads:
                sess_options.intra_op_num_threads = max(1, len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 2))
            if not sess_options.inter_op_num_threads:
                sess_options.inter_op_num_threads = 1
            super().__init__(path_or_bytes, sess_options, *args, **kwargs)

    ort.InferenceSession = Session
    ort._nuorb_threads = True


class PiperTTS:
    def __init__(self, path: str):
        self.path = path
        self.voice = None
        self.ready = False
        self._lock = asyncio.Lock()
        self._extra = (None, None)  # (Pfad, PiperVoice): hoechstens EINE Probehoer-Stimme zusaetzlich im Speicher

    def load(self):
        want = cur_voice()
        if self.voice is not None and want != self.path:  # Stimme in ui.json geaendert
            print(f"Piper: wechsle Stimme {Path(self.path).stem} -> {Path(want).stem}", flush=True)
            self.voice, self.ready = None, False
        self.path = want
        if self.voice is None:
            try:  # keine Telemetrie von onnxruntime
                import onnxruntime
                onnxruntime.disable_telemetry_events()
                _ort_explicit_threads(onnxruntime)
            except Exception:
                pass
            from piper import PiperVoice
            self.voice = PiperVoice.load(self.path)
            self.ready = True
        return self.voice

    def synth(self, text: str, path: str | None = None, length_scale: float | None = None) -> bytes:
        """path/length_scale nur fuer diesen Aufruf (Probehoeren in der Verwaltung); Standard-Stimme bleibt geladen."""
        from piper import SynthesisConfig
        voice = self.load()
        if path and path != self.path:
            if self._extra[0] != path:
                from piper import PiperVoice
                print(f"Piper: Probehoer-Stimme {Path(path).stem}", flush=True)
                self._extra = (path, PiperVoice.load(path))
            voice = self._extra[1]
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            voice.synthesize_wav(text, wf, syn_config=SynthesisConfig(
                length_scale=length_scale if length_scale is not None else cur_length_scale()))
        return buf.getvalue()


tts_engine = PiperTTS(cur_voice())


def voice_ready(path: str) -> bool:
    return Path(path).is_file() and Path(path + ".json").is_file()


async def warm_voice() -> None:
    said = False
    while not voice_ready(cur_voice()):
        if not said:
            print(f"Piper: waiting for voice download ({Path(cur_voice()).name}) – Sprachausgabe startet danach", flush=True)
            said = True
        await asyncio.sleep(5)
    if said:
        print(f"Piper: voice available ({Path(cur_voice()).name})", flush=True)
    try:
        await asyncio.get_running_loop().run_in_executor(None, tts_engine.load)
    except Exception as exc:
        print(f"Piper: Stimme nicht ladbar ({exc.__class__.__name__}: {str(exc)[:120]})", flush=True)

_MD = [
    (re.compile(r"\[(?:Systeminfo[^\]]{0,400}|(?:Es ist )?[^\]]{0,40}\d{1,2}:\d{2}[^\]]{0,200})\]"), " "),
    (re.compile(r"\[Projekt-Claude[^\]]*\]", re.I), " "),
    (re.compile(r"<\|?/?(?:channel|tool_call|tool_response)\|?>|<\|\"\|>", re.I), " "),
    (re.compile(r"(^|[\s.!?:])thought(?=[ \t]*(?:\n|$|<))", re.I), r"\1"), (re.compile(r"^[\s|}]+"), ""),
    (re.compile(r"```.*?```", re.S), " "), (re.compile(r"`([^`]*)`"), r"\1"),
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), " "), (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),
    (re.compile(r"https?://\S+"), "ein Link"), (re.compile(r"[*_#>|~]+"), " "),
    (re.compile(r"^\s*[-•]\s+", re.M), ""), (re.compile(r"[\U0001F300-\U0001FAFF☀-➿]"), ""),
    (re.compile(r"\s+"), " "),
]


def speakable(text: str) -> str:
    for rx, rep in _MD:
        text = rx.sub(rep, text)
    return text.strip()[:600]


@app.post("/api/tts")
async def tts(request: Request):
    body = await request.json()
    text = speakable(str(body.get("text") or ""))
    # Optional (Probehoeren aus jarvis-admin): voice = Name in ~/.hermes/cache/piper-voices, length_scale 0.6–1.6
    path = ls = None
    if body.get("voice") is not None:
        v = str(body["voice"])
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", v):
            raise HTTPException(400, "Stimme ungültig.")
        cand = HOME / ".hermes/cache/piper-voices" / f"{v}.onnx"
        if not (cand.is_file() and Path(str(cand) + ".json").is_file()):
            raise HTTPException(404, "Stimme nicht gefunden.")
        path = str(cand)
    if body.get("length_scale") is not None:
        try:
            ls = float(body["length_scale"])
        except (TypeError, ValueError):
            raise HTTPException(400, "Tempo ungültig.")
        if not 0.6 <= ls <= 1.6:
            raise HTTPException(400, "Tempo muss zwischen 0,6 und 1,6 liegen.")
    if not text:
        return Response(status_code=204)
    if not voice_ready(path or cur_voice()):  # Stimme noch nicht heruntergeladen (Docker-Erststart)
        return JSONResponse({"detail": "voice not ready", "code": "voice_loading"}, status_code=503)
    async with tts_engine._lock:  # ein Synthese-Job zur Zeit; Saetze kommen ohnehin nacheinander
        wav = await asyncio.get_running_loop().run_in_executor(None, tts_engine.synth, text, path, ls)
    return Response(wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------------------- Statisch
@app.get("/nuorb-ca.crt")
@app.get("/jarvis-ca.crt")
async def ca_cert(request: Request):
    p = CERT_DIR / "jarvis-ca.crt"
    if not p.exists():
        raise HTTPException(404)
    name = "nuorb-ca.crt" if request.url.path.startswith("/nuorb") else "jarvis-ca.crt"
    return FileResponse(p, media_type="application/x-x509-ca-cert", filename=name)


# Build-Kennung = Hash ueber die ausgelieferten Dateien. index.html bekommt sie als data-build und als ?v= an
# allen JS/CSS-Links (Cache-Busting fuer Epiphany). Die App fragt /api/version und laedt sich bei Aenderung neu.
_BUILD_FILES = ("index.html", "app.js", "orb.js", "style.css", "orb.css", "tokens.css", "i18n.js", "i18n-en.js")


def ui_cfg() -> dict:
    """Marke, Weckwort und Oberflaechensprache. ui.json (brand_name, wake_phrase, ui_lang) vor Umgebung
    (BRAND_NAME, WAKE_PHRASE, UI_LANG). Standard: JARVIS, „Hey Jarvis“, Deutsch. ui_lang: de | en | auto (Browser)."""
    def pick(key, env, default):
        v = cfg().get(key)
        v = v if isinstance(v, str) and v.strip() else os.environ.get(env, default)
        return re.sub(r"[^\w .äöüÄÖÜß-]", "", str(v)).strip()[:24] or default
    lang = pick("ui_lang", "UI_LANG", "de").lower()
    brand = pick("brand_name", "BRAND_NAME", "NuOrb")
    wake = pick("wake_phrase", "WAKE_PHRASE", "")
    name = pick("assistant_name", "ASSISTANT_NAME", brand)  # wie der Assistent heisst (Standard = Produkt)
    return {"brand": brand, "assistant_name": name, "wake_phrase": wake or None,
            "ui_lang": lang if lang in ("de", "en", "auto") else "de"}


def onboarding_due() -> bool:
    """Begruessung beim ersten Start: nur wenn ausdruecklich gewuenscht (Image: JARVIS_ONBOARDING=1 oder ui.json
    onboarded=false) und noch nicht erledigt. Die bestehende Instanz (ohne beides) begruesst nie von selbst."""
    ob = cfg().get("onboarded")
    return ob is False or (ob is not True and os.environ.get("JARVIS_ONBOARDING") == "1")


NAME_RE = re.compile(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß0-9 .-]{0,23}")
_build_cache: dict = {"key": None, "build": "0"}


def build_id() -> str:
    import hashlib
    key = tuple((BASE / "static" / f).stat().st_mtime_ns for f in _BUILD_FILES) + tuple(ui_cfg().values())
    if key != _build_cache["key"]:
        h = hashlib.sha256(json.dumps(ui_cfg(), sort_keys=True).encode())  # Marke/Sprache aendern -> neuer Build
        for f in _BUILD_FILES:
            h.update((BASE / "static" / f).read_bytes())
        _build_cache.update(key=key, build=h.hexdigest()[:10])
    return _build_cache["build"]


@app.get("/api/version")
async def version():
    return {"build": build_id()}


@app.get("/api/manifest")
async def manifest():
    """Dateiliste fuer jarvis-shell auf dem Handy (lokale Kopie der UI). index.html holt die Shell gerendert ueber /."""
    import hashlib
    root = BASE / "static"
    files = {}
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.name != "index.html" and not f.name.startswith("."):
            data = webmanifest_bytes() if f.name == "manifest.webmanifest" else f.read_bytes()  # dynamisch (Marke)
            files[f.relative_to(root).as_posix()] = hashlib.sha256(data).hexdigest()
    return {"build": build_id(), "files": files}


@app.get("/")
async def index():
    b = build_id()
    html = (BASE / "static/index.html").read_text(encoding="utf-8")
    html = re.sub(r'((?:src|href)="(?:app|orb|i18n|i18n-en)\.js|href="(?:style|orb|tokens)\.css)"', rf'\1?v={b}"', html)
    html = html.replace('<html lang="de">', f'<html lang="de" data-build="{b}">', 1)
    uc = ui_cfg()
    html = html.replace("<title>JARVIS</title>", f"<title>{uc['brand']}</title>", 1)
    cfg_js = json.dumps(uc, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace('<script src="i18n.js', f'<script>window.JARVIS_CFG={cfg_js};</script>\n<script src="i18n.js', 1)
    return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache, no-store"})


def webmanifest_bytes() -> bytes:
    m = json.loads((BASE / "static/manifest.webmanifest").read_text(encoding="utf-8"))
    uc = ui_cfg()
    m.update(name=uc["brand"], short_name=uc["brand"], lang="en" if uc["ui_lang"] == "en" else "de")
    return json.dumps(m, ensure_ascii=False, indent=2).encode()


@app.get("/manifest.webmanifest")
async def webmanifest():
    return Response(webmanifest_bytes(), media_type="application/manifest+json")


app.mount("/", StaticFiles(directory=BASE / "static"), name="static")


if __name__ == "__main__":
    ssl = {}
    if (CERT_DIR / "server.crt").exists():
        ssl = {"ssl_certfile": str(CERT_DIR / "server.crt"), "ssl_keyfile": str(CERT_DIR / "server.key")}
    uvicorn.run(app, host=HOST, port=PORT, log_level="info", proxy_headers=False, **ssl)
