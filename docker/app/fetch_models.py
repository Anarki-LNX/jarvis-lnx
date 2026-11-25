#!/usr/bin/env python3
"""NuOrb (Docker): lädt beim ersten Start die Sprachmodelle ins Modell-Volume (nicht ins Image gebacken).

  * Piper-Stimme(n): rhasspy/piper-voices auf Hugging Face (Standard: de_DE-thorsten-medium bzw. en_GB-alan-medium)
  * Spracherkennung: Parakeet-TDT-0.6B-v3 int8 für sherpa-onnx (GitHub-Release k2-fsa/sherpa-onnx, ~465 MB)
Vorhandene Dateien werden nicht erneut geladen. Downloads laufen in eine .part-Datei und werden erst am Ende umbenannt.
"""
from __future__ import annotations

import os
import shutil
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nuorb_common as jc  # noqa: E402

HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
PARAKEET = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
PARAKEET_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{PARAKEET}.tar.bz2"
VOICES = jc.MODELS / "voices"
STT = jc.MODELS / "stt"


def log(msg: str) -> None:
    print(f"[nuorb-models] {msg}", flush=True)


def fetch(url: str, dest: Path) -> None:
    part = dest.with_name(dest.name + ".part")
    t0, last = time.time(), 0.0
    req = urllib.request.Request(url, headers={"User-Agent": "nuorb-docker"})
    with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if time.time() - last > 2:
                if time.time() - last > 15 or not last:
                    log(f"{dest.name}: {done >> 20} / {total >> 20 or '?'} MB")
                last = time.time()
                jc.set_models_status(state="loading", item=dest.name, done_mb=done >> 20, total_mb=total >> 20, error=None)
    os.replace(part, dest)
    log(f"{dest.name}: done ({done >> 20} MB in {time.time() - t0:.0f} s)")


def voice_path(name: str) -> str:
    # de_DE-thorsten-medium -> de/de_DE/thorsten/medium/de_DE-thorsten-medium
    loc, spk, q = name.split("-", 2)
    return f"{loc.split('_')[0]}/{loc}/{spk}/{q}/{name}"


def voices(extra: list[str] | None = None) -> None:
    names = [jc.voice_name()] + (extra or [])
    names += [v.strip() for v in jc.env("NUORB_EXTRA_VOICES").split(",") if v.strip()]
    VOICES.mkdir(parents=True, exist_ok=True)
    for n in dict.fromkeys(names):
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
OFFLINE = ("No internet connection: the speech models (~530 MB) could not be downloaded. "
           "Retrying automatically. Check the container's DNS/proxy/firewall.")


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
            msg = OFFLINE if net else f"{exc.__class__.__name__}: {exc}"
            jc.set_models_status(state="error", error=msg[:300], error_code="offline" if net else "error", retry_in=wait)
            log(f"Download failed ({exc.__class__.__name__}: {exc}); retrying in {wait} s")
            time.sleep(wait)
    return 1


if __name__ == "__main__":
    sys.exit(main())
