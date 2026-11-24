#!/usr/bin/env python3
"""XIAOMI REBIRTH / NuOrb: STT-Router auf nuorb (OpenAI-kompatibel, nur LAN/localhost).

POST /v1/audio/transcriptions  (multipart: file, model, language, response_format)
  1. Ist PC_STT_URL gesetzt und der PC erreichbar -> Anfrage dorthin weiterreichen
     (z. B. whisper.cpp-Server mit turbo-german auf der GPU). Erreichbarkeit wird 10 s gecacht.
  2. Sonst / bei Fehler -> lokal auf der CPU: Parakeet-TDT-0.6B-v3 (int8) ueber sherpa-onnx,
     Modell bleibt resident im RAM (kein Kaltstart pro Anfrage).
GET /health -> {"ok": true, "pc": <bool>, "backend": "..."}

Hermes-Anbindung (~/.hermes/config.yaml):
  stt.provider: openai
  stt.openai.base_url: http://127.0.0.1:8178/v1      (lokale URL -> Hermes braucht keinen Key)
  stt.openai.model: parakeet                          (beliebig != whisper-1 -> JSON-Antwort)

Start: ~/sprache/venv/bin/python -I ~/sprache/sprache-stt-router.py
Umgebung: STT_ROUTER_PORT (8178), STT_ROUTER_HOST (127.0.0.1), PARAKEET_DIR,
          PC_STT_URL (z. B. http://<PC_HOST>:8177/v1/audio/transcriptions), PC_TIMEOUT (8)
Audio wird nie gespeichert und verlaesst das LAN nicht.
"""
import json
import os
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import sherpa_onnx

HOST = os.environ.get("STT_ROUTER_HOST", "127.0.0.1")
PORT = int(os.environ.get("STT_ROUTER_PORT", "8178"))
PARAKEET_DIR = os.path.expanduser(os.environ.get(
    "PARAKEET_DIR", "~/.hermes/models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"))
PC_STT_URL = os.environ.get("PC_STT_URL", "").strip()
PC_TIMEOUT = float(os.environ.get("PC_TIMEOUT", "8"))
THREADS = int(os.environ.get("STT_THREADS", str(os.cpu_count() or 4)))
MAX_BYTES = 50 * 1024 * 1024


def lade_parakeet():
    d = PARAKEET_DIR
    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=f"{d}/encoder.int8.onnx", decoder=f"{d}/decoder.int8.onnx",
        joiner=f"{d}/joiner.int8.onnx", tokens=f"{d}/tokens.txt",
        model_type="nemo_transducer", num_threads=THREADS, provider="cpu")


RECOGNIZER = None
LOCK = threading.Lock()  # ein Decode zur Zeit, nutzt ohnehin alle Kerne


def dekodiere_audio(daten: bytes) -> np.ndarray:
    """Beliebiges Format (ogg/opus, m4a, wav, mp3 …) -> 16 kHz mono float32 via ffmpeg."""
    p = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0",
         "-ac", "1", "-ar", "16000", "-f", "f32le", "pipe:1"],
        input=daten, capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.float32)


def lokal_erkennen(daten: bytes) -> str:
    samples = dekodiere_audio(daten)
    with LOCK:
        s = RECOGNIZER.create_stream()
        s.accept_waveform(16000, samples)
        RECOGNIZER.decode_stream(s)
        return s.result.text.strip()


_pc_cache = {"t": 0.0, "ok": False}


def pc_erreichbar() -> bool:
    if not PC_STT_URL:
        return False
    if time.monotonic() - _pc_cache["t"] < 10:
        return _pc_cache["ok"]
    u = urllib.parse.urlparse(PC_STT_URL)
    try:
        with socket.create_connection((u.hostname, u.port or 80), timeout=0.15):
            ok = True
    except OSError:
        ok = False
    _pc_cache.update(t=time.monotonic(), ok=ok)
    return ok


def pc_erkennen(roh: bytes, content_type: str) -> str:
    req = urllib.request.Request(PC_STT_URL, data=roh, method="POST",
                                 headers={"Content-Type": content_type})
    with urllib.request.urlopen(req, timeout=PC_TIMEOUT) as r:
        body = r.read().decode("utf-8", "replace")
    try:
        return json.loads(body).get("text", "").strip()
    except json.JSONDecodeError:
        return body.strip()


def parse_multipart(content_type: str, roh: bytes) -> dict:
    msg = BytesParser(policy=HTTP).parsebytes(
        b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + roh)
    felder = {}
    for teil in msg.iter_parts():
        name = teil.get_param("name", header="content-disposition")
        if name:
            felder[name] = teil.get_payload(decode=True)
    return felder


class Handler(BaseHTTPRequestHandler):
    server_version = "nuorb-stt-router/1"

    def log_message(self, fmt, *args):  # knapp loggen, keine Inhalte
        print(f"{self.address_string()} {fmt % args}", flush=True)

    def _antwort(self, code: int, body, ctype="application/json"):
        daten = body if isinstance(body, bytes) else (
            json.dumps(body, ensure_ascii=False).encode() if ctype == "application/json" else body.encode())
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(daten)))
        self.end_headers()
        self.wfile.write(daten)

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            return self._antwort(200, {"ok": True, "pc": pc_erreichbar(), "backend": "parakeet-tdt-0.6b-v3-int8"})
        self._antwort(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/audio/transcriptions"):
            return self._antwort(404, {"error": {"message": "not found"}})
        laenge = int(self.headers.get("Content-Length", "0"))
        if laenge <= 0 or laenge > MAX_BYTES:
            return self._antwort(413, {"error": {"message": "bad size"}})
        ctype = self.headers.get("Content-Type", "")
        roh = self.rfile.read(laenge)
        t0 = time.perf_counter()
        try:
            felder = parse_multipart(ctype, roh)
            fmt = (felder.get("response_format") or b"json").decode()
            text, weg = None, "cpu"
            if pc_erreichbar():
                try:
                    text, weg = pc_erkennen(roh, ctype), "pc"
                except Exception as e:  # PC weg/zu langsam -> lokal
                    print(f"PC-Fehler, nehme CPU: {e}", flush=True)
                    _pc_cache.update(t=time.monotonic(), ok=False)
            if text is None:
                text = lokal_erkennen(felder["file"])
        except Exception as e:
            return self._antwort(500, {"error": {"message": f"{type(e).__name__}: {e}"}})
        print(f"transkribiert via {weg} in {time.perf_counter()-t0:.2f} s", flush=True)
        if fmt == "text":
            return self._antwort(200, text, "text/plain")
        self._antwort(200, {"text": text})


def main():
    global RECOGNIZER
    t0 = time.perf_counter()
    RECOGNIZER = lade_parakeet()
    print(f"Parakeet geladen in {time.perf_counter()-t0:.1f} s, {THREADS} Threads; "
          f"PC: {PC_STT_URL or 'aus'}; lausche auf {HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
