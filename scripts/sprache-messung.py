#!/usr/bin/env python3
"""XIAOMI REBIRTH / JARVIS: Latenzmessung der lokalen Sprachkette auf jarvis (nur CPU).

Misst
  * TTS (Piper): Laden der Stimme, Zeit bis zum ersten Audio-Chunk (= erster Satz),
    Echtzeitfaktor (RTF = Rechenzeit / Audiodauer).
  * STT (faster-whisper, Einstellungen wie Hermes: beam_size=5, VAD an, CPU int8):
    Laden des Modells, Latenz fuer eine ~5-s-Aeusserung (Median aus 3 Laeufen, warm).

Die Testaeusserung wird mit Piper erzeugt (bekannter Text -> grobe Wortfehlerrate).
Optional eine eigene Aufnahme: --wav /pfad/zur/aufnahme.wav --ref "gesprochener Text"

Aufruf (als jarvis, im Hermes-Python):
  cd ~/.hermes/hermes-agent && scripts/run-in-hermes-env python ~/sprache/sprache-messung.py
"""
import argparse
import os
import re
import statistics
import time
import wave

HOME = os.path.expanduser("~")
VOICES = os.path.join(HOME, ".hermes/cache/piper-voices")
MODELS = os.path.join(HOME, ".hermes/models")

SATZ = ("Guten Morgen. Schalte bitte um halb acht das Licht im Wohnzimmer ein "
        "und sag mir, wie das Wetter heute in Berlin wird.")
ERSTER_SATZ_LANG = ("Klar, das Licht im Wohnzimmer geht um halb acht an. "
                    "Heute wird es in Berlin bewoelkt bei elf Grad.")


def wer(ref: str, hyp: str) -> float:
    norm = lambda s: re.sub(r"[^\wäöüß ]", " ", s.lower()).split()
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / max(1, len(r))


def tts_messen(stimme: str, wav_out: str | None):
    from piper import PiperVoice
    t0 = time.perf_counter()
    voice = PiperVoice.load(os.path.join(VOICES, f"{stimme}.onnx"))
    t_load = time.perf_counter() - t0
    # Aufwaermen (erster Lauf initialisiert onnxruntime-Sessions)
    for _ in voice.synthesize("Test."):
        pass
    ergebnisse = []
    for text in (SATZ, ERSTER_SATZ_LANG):
        t0 = time.perf_counter()
        first = None
        samples = 0
        rate = 22050
        frames = []
        for chunk in voice.synthesize(text):
            if first is None:
                first = time.perf_counter() - t0
            rate = chunk.sample_rate
            samples += len(chunk.audio_int16_bytes) // 2
            frames.append(chunk.audio_int16_bytes)
        total = time.perf_counter() - t0
        dauer = samples / rate
        ergebnisse.append((text, first, total, dauer))
        if wav_out and text == SATZ:
            with wave.open(wav_out, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(rate)
                w.writeframes(b"".join(frames))
    print(f"\n[TTS] {stimme}: Laden {t_load:.2f} s")
    for text, first, total, dauer in ergebnisse:
        print(f"  erstes Audio nach {first*1000:.0f} ms | gesamt {total:.2f} s fuer {dauer:.1f} s Audio "
              f"(RTF {total/dauer:.2f}) | '{text[:40]}...'")
    return t_load, ergebnisse


def stt_messen(modell: str, wav: str, ref: str, threads: int):
    from faster_whisper import WhisperModel
    pfad = os.path.join(MODELS, modell)
    t0 = time.perf_counter()
    m = WhisperModel(pfad, device="cpu", compute_type="int8", cpu_threads=threads)
    t_load = time.perf_counter() - t0
    with wave.open(wav) as w:
        dauer = w.getnframes() / w.getframerate()
    zeiten, text = [], ""
    for _ in range(4):  # 1x warmlaufen + 3 Messungen
        t0 = time.perf_counter()
        segs, _info = m.transcribe(wav, language="de", beam_size=5, vad_filter=True)
        text = " ".join(s.text.strip() for s in segs)
        zeiten.append(time.perf_counter() - t0)
    warm = statistics.median(zeiten[1:])
    print(f"\n[STT] {modell} ({threads} Threads): Laden {t_load:.2f} s | Aeusserung {dauer:.1f} s | "
          f"kalt {zeiten[0]:.2f} s | warm (Median) {warm:.2f} s | WER {wer(ref, text)*100:.0f} %")
    print(f"  -> {text}")
    return t_load, zeiten[0], warm, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", help="eigene Testaufnahme (16-bit WAV) statt Piper-Satz")
    ap.add_argument("--ref", default=SATZ, help="Referenztext zur --wav-Aufnahme")
    ap.add_argument("--stimmen", default="de_DE-thorsten-medium,de_DE-thorsten-high")
    ap.add_argument("--modelle", default="whisper-small,whisper-turbo-german")
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()

    wav = a.wav or "/tmp/sprache-test.wav"
    for i, stimme in enumerate(a.stimmen.split(",")):
        tts_messen(stimme, None if (a.wav or i) else wav)
    for modell in a.modelle.split(","):
        stt_messen(modell, wav, a.ref, a.threads)


if __name__ == "__main__":
    main()
