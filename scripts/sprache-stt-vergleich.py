#!/usr/bin/env python3
"""XIAOMI REBIRTH / NuOrb: STT-Vergleich auf nuorb – gleiche Testaufnahmen fuer alle Engines.

Schritt 1 (Hermes-Python, hat piper):   ... python -I sprache-stt-vergleich.py erzeuge
   -> ~/sprache/testset/*.wav + saetze.json  (Piper thorsten medium/high, je sauber + mit Rauschen 15 dB SNR)
   Eigene Aufnahmen: WAV nach ~/sprache/testset/ legen und Text in saetze.json eintragen.
Schritt 2: ... python -I sprache-stt-vergleich.py whisper-small        (Hermes-Python, faster-whisper)
           ~/sprache/venv/bin/python -I sprache-stt-vergleich.py parakeet (sherpa-onnx)
Ausgabe: je Datei Latenz + WER, am Ende Mittelwerte.
"""
import json
import os
import re
import statistics
import subprocess
import sys
import time
import wave

import numpy as np

HOME = os.path.expanduser("~")
TS = os.path.join(HOME, "sprache/testset")
SAETZE = [
    "Guten Morgen. Schalte bitte um halb acht das Licht im Wohnzimmer ein und sag mir, wie das Wetter heute in Berlin wird.",
    "Erinnere mich am Donnerstag um vierzehn Uhr dreißig an den Zahnarzttermin bei Doktor Müller.",
    "Wie viele Kilometer sind es von Hamburg nach München, und wie lange braucht der ICE?",
    "Spiel etwas ruhige Musik und mach die Heizung im Schlafzimmer auf einundzwanzig Grad.",
    "Schreib eine Nachricht an Anna: Ich komme heute etwas später, warte bitte nicht mit dem Essen.",
]
STIMMEN = ["de_DE-thorsten-medium", "de_DE-thorsten-high"]

ZAHLEN = {"halb 8": "halb acht", "14:30": "vierzehn uhr dreißig", "14.30": "vierzehn uhr dreißig",
          "21 grad": "einundzwanzig grad", "21°": "einundzwanzig grad", "dr.": "doktor", "14 uhr 30": "vierzehn uhr dreißig"}


def norm(s: str) -> list[str]:
    s = s.lower()
    for a, b in ZAHLEN.items():
        s = s.replace(a, b)
    return re.sub(r"[^\wäöüß ]", " ", s).split()


def wer(ref: str, hyp: str) -> float:
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / max(1, len(r))


def lies_wav16k(pfad: str) -> np.ndarray:
    p = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", pfad, "-ac", "1", "-ar", "16000",
                        "-f", "f32le", "pipe:1"], capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.float32)


def erzeuge():
    from piper import PiperVoice
    os.makedirs(TS, exist_ok=True)
    meta = {}
    rng = np.random.default_rng(42)
    for st in STIMMEN:
        v = PiperVoice.load(os.path.join(HOME, ".hermes/cache/piper-voices", st + ".onnx"))
        for i, satz in enumerate(SAETZE):
            chunks = list(v.synthesize(satz))
            rate = chunks[0].sample_rate
            audio = np.frombuffer(b"".join(c.audio_int16_bytes for c in chunks), dtype=np.int16).astype(np.float32)
            for art in ("sauber", "rauschen"):
                a = audio
                if art == "rauschen":  # weisses Rauschen, SNR 15 dB
                    p_sig = np.mean(a ** 2)
                    a = a + rng.normal(0, np.sqrt(p_sig / 10 ** 1.5), a.shape)
                name = f"{st.split('-')[-1]}_{i}_{art}.wav"
                with wave.open(os.path.join(TS, name), "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
                    w.writeframes(np.clip(a, -32768, 32767).astype(np.int16).tobytes())
                meta[name] = satz
    with open(os.path.join(TS, "saetze.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"{len(meta)} Testdateien in {TS}")


def engine(name: str):
    if name == "parakeet":
        import sherpa_onnx
        d = os.path.join(HOME, ".hermes/models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8")
        rec = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=f"{d}/encoder.int8.onnx", decoder=f"{d}/decoder.int8.onnx", joiner=f"{d}/joiner.int8.onnx",
            tokens=f"{d}/tokens.txt", model_type="nemo_transducer", num_threads=os.cpu_count() or 4)

        def run(pfad):
            s = rec.create_stream()
            s.accept_waveform(16000, lies_wav16k(pfad))
            rec.decode_stream(s)
            return s.result.text
        return run
    from faster_whisper import WhisperModel  # whisper-small, whisper-turbo-german …
    m = WhisperModel(os.path.join(HOME, ".hermes/models", name), device="cpu", compute_type="int8",
                     cpu_threads=os.cpu_count() or 4)

    def run(pfad):  # Hermes-Einstellungen
        segs, _ = m.transcribe(pfad, language="de", beam_size=5, vad_filter=True)
        return " ".join(s.text.strip() for s in segs)
    return run


def vergleiche(name: str):
    meta = json.load(open(os.path.join(TS, "saetze.json")))
    t0 = time.perf_counter()
    run = engine(name)
    print(f"[{name}] Laden {time.perf_counter()-t0:.2f} s")
    run(os.path.join(TS, next(iter(meta))))  # Aufwaermen
    zeilen = []
    for datei, ref in meta.items():
        pfad = os.path.join(TS, datei)
        with wave.open(pfad) as w:
            dauer = w.getnframes() / w.getframerate()
        t = time.perf_counter()
        hyp = run(pfad)
        lat = time.perf_counter() - t
        e = wer(ref, hyp)
        zeilen.append((datei, dauer, lat, e))
        print(f"  {datei:28s} {dauer:4.1f} s Audio  {lat:5.2f} s  WER {e*100:4.0f} %  | {hyp}", flush=True)
    for art in ("sauber", "rauschen"):
        z = [x for x in zeilen if art in x[0]]
        print(f"[{name}] {art:8s}: Latenz Mittel {statistics.mean(x[2] for x in z):.2f} s "
              f"(RTF {statistics.mean(x[2]/x[1] for x in z):.2f}), WER Mittel {statistics.mean(x[3] for x in z)*100:.1f} %")


if __name__ == "__main__":
    erzeuge() if sys.argv[1] == "erzeuge" else vergleiche(sys.argv[1])
