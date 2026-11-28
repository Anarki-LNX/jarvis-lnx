#!/usr/bin/env python3
"""NuOrb-Server (Docker): lädt beim ersten Start die Sprachmodelle ins Modell-Volume (nicht ins Image gebacken).

  * Piper-Stimme(n): rhasspy/piper-voices auf Hugging Face (Standard: de_DE-thorsten-medium bzw. en_US-joe-medium; nur Stimmen mit CC0/CC-BY-Kette)
  * Spracherkennung: Parakeet-TDT-0.6B-v3 int8 für sherpa-onnx (GitHub-Release k2-fsa/sherpa-onnx, ~465 MB)
Vorhandene Dateien werden nicht erneut geladen. Downloads laufen in eine .part-Datei und werden erst am Ende umbenannt.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import socket
import threading
import urllib.parse
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nuorb_common as jc  # noqa: E402

# Feste Revision statt des veränderlichen Branches main (Stand 28.11.2026), dazu SHA-256 jeder bekannten Datei.
HF_REV = "613b6e5ad36ddca4e70e171957291483dc244d9f"
HF = f"https://huggingface.co/rhasspy/piper-voices/resolve/{HF_REV}"
PARAKEET = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
PARAKEET_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{PARAKEET}.tar.bz2"
SHA256 = {
    "de_DE-thorsten-medium.onnx": "fd270eb3d1ebf91d763f8a0f949b1b1bebdfefaea18c3aaf8577dd34536e064f",
    "de_DE-thorsten-medium.onnx.json": "e5bb7410dcbbcc0be6f4544f6bc66612b315ab5cb3099ec44bb46d860bc7cca9",
    "en_US-joe-medium.onnx": "abf4b998e34045cbd00eaf050de2de620f81ded6eb8b85a24b022a1c2b3f08d2",
    "en_US-joe-medium.onnx.json": "9b91a652090ffa8a49e36569afa9acc8ead2b3a22a950e8e6ca11914f3e85d56",
    f"{PARAKEET}.tar.bz2": "1495e91b59d7fc53ddca91f3431758ec99f8fa253fdb0e1e851be0f72b14b0f9",
}


class ChecksumError(Exception):
    """Die geladene Datei stimmt nicht mit der hinterlegten Prüfsumme überein (beschädigt oder verändert)."""
VOICES = jc.MODELS / "voices"
STT = jc.MODELS / "stt"


def log(msg: str) -> None:
    print(f"[nuorb-models] {msg}", flush=True)


_reachable: set[str] = set()


def preflight(url: str) -> None:
    """Vor dem ersten Download vom Host: DNS + TCP in höchstens ~12 s prüfen. Eine Firewall, die weiterleitende Pakete
    verwirft (ufw DEFAULT_FORWARD_POLICY=DROP, firewalld), ließe den Download sonst minutenlang ohne Meldung hängen."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if host in _reachable:
        return
    res: dict = {}

    def probe() -> None:
        try:
            socket.create_connection((host, 443), timeout=8).close()
            res["ok"] = True
        except OSError as exc:
            res["err"] = exc
    t = threading.Thread(target=probe, daemon=True)
    t.start()
    t.join(12)
    if not res.get("ok"):
        raise ConnectionError(f"no connection to {host}:443 ({res.get('err') or 'timeout, DNS or firewall'})")
    _reachable.add(host)


def fetch(url: str, dest: Path) -> None:
    """Lädt in <dest>.part, prüft die SHA-256 (falls bekannt) und benennt erst danach um."""
    jc.set_models_status(state="loading", item=dest.name, done_mb=0, total_mb=0, error=None, error_code=None)
    preflight(url)
    part = dest.with_name(dest.name + ".part")
    t0, last = time.time(), 0.0
    req = urllib.request.Request(url, headers={"User-Agent": "nuorb-docker"})
    digest = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if time.time() - last > 2:
                if time.time() - last > 15 or not last:
                    log(f"{dest.name}: {done >> 20} / {total >> 20 or '?'} MB")
                last = time.time()
                jc.set_models_status(state="loading", item=dest.name, done_mb=done >> 20, total_mb=total >> 20, error=None)
    want = SHA256.get(dest.name)
    if want and digest.hexdigest() != want:
        part.unlink(missing_ok=True)
        raise ChecksumError(f"{dest.name}: checksum mismatch (expected {want[:12]}…, got {digest.hexdigest()[:12]}…), file deleted")
    if not want:
        log(f"{dest.name}: no checksum on record, loaded from the pinned revision")
    os.replace(part, dest)
    log(f"{dest.name}: done ({done >> 20} MB in {time.time() - t0:.0f} s)")


def voice_path(name: str) -> str:
    # de_DE-thorsten-medium -> de/de_DE/thorsten/medium/de_DE-thorsten-medium
    loc, spk, q = name.split("-", 2)
    return f"{loc.split('_')[0]}/{loc}/{spk}/{q}/{name}"


def log_skip(name: str) -> bool:
    print(f"[nuorb-models] Voice {name} skipped: not licensed for commercial use.", flush=True)
    return False


def voices(extra: list[str] | None = None) -> None:
    names = [jc.voice_name()] + (extra or [])
    names += [v.strip() for v in jc.env("NUORB_EXTRA_VOICES").split(",") if v.strip()]
    VOICES.mkdir(parents=True, exist_ok=True)
    for n in [x for x in dict.fromkeys(names) if not jc.voice_replacement(x) or log_skip(x)]:
        for ext in (".onnx", ".onnx.json"):
            dest = VOICES / f"{n}{ext}"
            if not dest.exists() or dest.stat().st_size == 0:
                fetch(f"{HF}/{voice_path(n)}{ext}", dest)


def parakeet() -> None:
    target = STT / PARAKEET
    if (target / "encoder.int8.onnx").exists() and (target / "tokens.txt").exists():
        return
    STT.mkdir(parents=True, exist_ok=True)
    arc = STT / f"{PARAKEET}.tar.bz2"
    if not arc.exists():
        log("Downloading speech recognition Parakeet (~465 MB, once) …")
        fetch(PARAKEET_URL, arc)
    tmp = STT / f".{PARAKEET}.entpacken"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    with tarfile.open(arc, "r:bz2") as t:
        t.extractall(tmp, filter="data")
    shutil.rmtree(target, ignore_errors=True)
    os.replace(tmp / PARAKEET, target)
    shutil.rmtree(tmp, ignore_errors=True)
    arc.unlink(missing_ok=True)
    for f in target.glob("test_wavs"):
        shutil.rmtree(f, ignore_errors=True)
    log(f"Parakeet ready in {target}")


# Die Einrichtungsseite übersetzt anhand von error_code selbst; der Text hier ist für Protokoll und API.
OFFLINE = ("No internet connection from the container: the speech models (~530 MB) could not be downloaded. "
           "Retrying automatically. Check DNS/proxy/firewall; with ufw: sudo ufw default allow routed && sudo ufw reload.")


def main() -> int:
    args = sys.argv[1:] or ["voices", "stt"]
    extra = args[args.index("voice") + 1:] if "voice" in args else []
    for attempt in range(1, 6):
        try:
            if "voices" in args or extra:
                voices(extra)
            if "stt" in args:
                parakeet()
            jc.set_models_status(state="ready", item=None, error=None, error_code=None)
            return 0
        except Exception as exc:
            wait = min(300, 20 * attempt)
            net = isinstance(exc, (OSError,)) and not isinstance(exc, (PermissionError, FileNotFoundError))
            code = "checksum" if isinstance(exc, ChecksumError) else "offline" if net else "error"
            msg = OFFLINE if net else f"{exc.__class__.__name__}: {exc}"
            jc.set_models_status(state="error", error=msg[:300], error_code=code, retry_in=wait)
            log(f"Download failed ({exc.__class__.__name__}: {exc}); retrying in {wait} s")
            time.sleep(wait)
    return 1


if __name__ == "__main__":
    sys.exit(main())
