#!/usr/bin/env python3
"""XIAOMI REBIRTH / NuOrb: Clips mit Parakeet (sherpa-onnx, CPU) transkribieren – laeuft AUF nuorb.

Wird von frei-verarbeiten.py per ssh aufgerufen:
  ~/sprache/venv/bin/python -I frei-transkribieren-nuorb.py <ordner-mit-wavs>
Ausgabe (stdout): je Clip eine JSON-Zeile {"id", "dauer", "text", "t_start", "t_ende"}
t_start/t_ende = Zeit des ersten/letzten Tokens (s), zur Pruefung abgeschnittener Woerter.
"""
import json
import os
import sys

import numpy as np
import sherpa_onnx
import soundfile as sf

D = os.path.expanduser("~/.hermes/models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8")
rec = sherpa_onnx.OfflineRecognizer.from_transducer(
    encoder=f"{D}/encoder.int8.onnx", decoder=f"{D}/decoder.int8.onnx", joiner=f"{D}/joiner.int8.onnx",
    tokens=f"{D}/tokens.txt", model_type="nemo_transducer", num_threads=os.cpu_count() or 4)

ordner = sys.argv[1]
for name in sorted(os.listdir(ordner)):
    if not name.endswith(".wav"):
        continue
    a, r = sf.read(os.path.join(ordner, name), dtype="float32", always_2d=True)
    a = np.ascontiguousarray(a.mean(axis=1))
    s = rec.create_stream()
    s.accept_waveform(r, a)  # sherpa resampelt intern auf 16 kHz
    rec.decode_stream(s)
    ts = list(s.result.timestamps or [])
    print(json.dumps({"id": name[:-4], "dauer": round(len(a) / r, 3), "text": s.result.text.strip(),
                      "t_start": ts[0] if ts else None, "t_ende": ts[-1] if ts else None},
                     ensure_ascii=False), flush=True)
