#!/usr/bin/env python3
"""XIAOMI REBIRTH / JARVIS – Web-Oberflaeche (Server).

Laeuft auf jarvis (LXC 100) als Benutzer jarvis, HTTPS auf Port 8443, nur LAN.
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
BRAIN_URL = os.environ.get("BRAIN_URL", "http://" + os.environ.get("OLLAMA_HOST", "ollama-pc.local") + ":11434/api/version")
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
    "Jede Nachricht beginnt mit der aktuellen Zeit in eckigen Klammern; nutze sie fuer Uhrzeit und Datum, "
    "lies die Klammer aber nicht vor. "
    "Geraeteaktionen am Handy (WLAN, Helligkeit, Lautstaerke, Bildschirm, Neustart, Ausschalten) fuehrst du NIE selbst aus "
    "und behauptest nie, sie seien erledigt: Rufe dafuer immer das Werkzeug mcp__geraet__anfordern auf (aktion und bei Helligkeit/Lautstaerke "
    "wert 0-100) und sage danach nur kurz, dass die Handy-Oberflaeche es ausfuehrt."
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


def cur_persona() -> str:
    p = cfg().get("persona")
    return p.strip()[:4000] if isinstance(p, str) and p.strip() else PERSONA


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
    # Stimme vorwaermen, damit der erste Satz nicht 1–2 s Ladezeit kostet
    asyncio.get_running_loop().run_in_executor(None, tts_engine.load)
    yield
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
    (brain, bdata), (hermes, _), (stt, sdata) = await asyncio.gather(
        _probe(BRAIN_URL), _probe(f"{HERMES_URL}/health"),
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
        "hermes": hermes, "stt": stt, "stt_backend": (sdata or {}).get("backend"),
        "tts": tts_engine.ready, "time": datetime.now().isoformat(timespec="seconds"), "mode": cur_mode(),
        "voice": Path(tts_engine.path).stem,
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
    zeit = f"[Es ist {demo_runs.WOCHENTAGE[now.weekday()]}, {now:%d.%m.%Y}, {now:%H:%M} Uhr"
    dev = body.get("device")
    if isinstance(dev, str) and dev.strip():  # Gerätestatus vom Handy, kurz und bereinigt
        zeit += "; Handy: " + re.sub(r"[^\w %,.°äöüÄÖÜß-]", "", dev)[:140]
    zeit += "]"
    payload = {"input": f"{zeit} {text}", "session_id": session_id, "instructions": cur_persona(),
               # Sprach-Runs ohne Denkphase: ~10x schneller bis zum ersten Satz (Messung ki-backend)
               "model_options": {"reasoning": {"enabled": cur_reasoning()}}}
    # Gehirn-Schalter: bei „remote“ Modell pro Run mitschicken (/v1/runs honoriert das immer) -> wirkt sofort,
    # auch bevor jarvis-admin das Gateway neu gestartet hat. Bei local/auto gilt die globale Hermes-Config.
    bm, bmod = str(cfg().get("brain_mode", "")).lower(), cfg().get("brain_model")
    if bm == "remote" and isinstance(bmod, str) and re.fullmatch(r"claude-[a-z0-9.-]{3,40}", bmod):
        payload.update(provider="anthropic", model=bmod)
    try:
        r = await client.post(f"{HERMES_URL}/v1/runs", json=payload, headers={
            **_auth(), "Idempotency-Key": f"ui-{secrets.token_urlsafe(18)}"}, timeout=15)
    except Exception:
        raise HTTPException(503, "Hermes nicht erreichbar")
    if r.status_code >= 400:
        detail = r.text[:300]
        raise HTTPException(r.status_code if r.status_code in (409, 429, 503) else 502, detail)
    data = r.json()
    return {"run_id": data.get("run_id"), "session_id": session_id, "status": data.get("status")}


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
class PiperTTS:
    def __init__(self, path: str):
        self.path = path
        self.voice = None
        self.ready = False
        self._lock = asyncio.Lock()

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
            except Exception:
                pass
            from piper import PiperVoice
            self.voice = PiperVoice.load(self.path)
            self.ready = True
        return self.voice

    def synth(self, text: str) -> bytes:
        from piper import SynthesisConfig
        voice = self.load()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            voice.synthesize_wav(text, wf, syn_config=SynthesisConfig(length_scale=cur_length_scale()))
        return buf.getvalue()


tts_engine = PiperTTS(cur_voice())

_MD = [
    (re.compile(r"\[(?:Es ist )?[^\]]{0,40}\d{1,2}:\d{2}[^\]]{0,200}\]"), " "),
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
    if not text:
        return Response(status_code=204)
    async with tts_engine._lock:  # ein Synthese-Job zur Zeit; Saetze kommen ohnehin nacheinander
        wav = await asyncio.get_running_loop().run_in_executor(None, tts_engine.synth, text)
    return Response(wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------------------- Statisch
@app.get("/jarvis-ca.crt")
async def ca_cert():
    p = CERT_DIR / "jarvis-ca.crt"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="application/x-x509-ca-cert", filename="jarvis-ca.crt")


# Build-Kennung = Hash ueber die ausgelieferten Dateien. index.html bekommt sie als data-build und als ?v= an
# allen JS/CSS-Links (Cache-Busting fuer Epiphany). Die App fragt /api/version und laedt sich bei Aenderung neu.
_BUILD_FILES = ("index.html", "app.js", "orb.js", "style.css", "orb.css", "tokens.css")
_build_cache: dict = {"key": None, "build": "0"}


def build_id() -> str:
    import hashlib
    key = tuple((BASE / "static" / f).stat().st_mtime_ns for f in _BUILD_FILES)
    if key != _build_cache["key"]:
        h = hashlib.sha256()
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
            files[f.relative_to(root).as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
    return {"build": build_id(), "files": files}


@app.get("/")
async def index():
    b = build_id()
    html = (BASE / "static/index.html").read_text(encoding="utf-8")
    html = re.sub(r'((?:src|href)="(?:app|orb)\.js|href="(?:style|orb|tokens)\.css)"', rf'\1?v={b}"', html)
    html = html.replace('<html lang="de">', f'<html lang="de" data-build="{b}">', 1)
    return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache, no-store"})


app.mount("/", StaticFiles(directory=BASE / "static"), name="static")


if __name__ == "__main__":
    ssl = {}
    if (CERT_DIR / "server.crt").exists():
        ssl = {"ssl_certfile": str(CERT_DIR / "server.crt"), "ssl_keyfile": str(CERT_DIR / "server.key")}
    uvicorn.run(app, host=HOST, port=PORT, log_level="info", proxy_headers=False, **ssl)
