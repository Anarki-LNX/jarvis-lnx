"""NuOrb: prüft, ob onnxruntime Telemetrie senden würde – ohne dass etwas das Gerät verlässt.

Läuft im Image mit --network none; die bekannten Telemetrie-Hosts zeigen per --add-host auf 127.0.0.1, wo dieses
Skript auf 443/80 lauscht und jeden Verbindungsversuch zählt. Aufruf über tools/telemetry-check.sh.
Argument: Wartezeit in Sekunden (onnxruntime sendet gebündelt, erster Versuch nach einigen Sekunden).
"""
import os, socket, ssl, sys, threading, time, glob
hits = []
def listen(port):
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port)); s.listen(8)
    while True:
        c, a = s.accept(); hits.append((port, time.strftime("%H:%M:%S"))); c.close()
for p in (443, 80):
    threading.Thread(target=listen, args=(p,), daemon=True).start()
print("ORT_DISABLE_TELEMETRY =", os.environ.get("ORT_DISABLE_TELEMETRY"), flush=True)
import onnxruntime as ort
m = "/opt/nuorb/venv/lib/python3.13/site-packages/onnxruntime/datasets/sigmoid.onnx"
import numpy as np
for i in range(3):
    sess = ort.InferenceSession(m, providers=["CPUExecutionProvider"])
    x = np.random.rand(*[d if isinstance(d, int) else 1 for d in sess.get_inputs()[0].shape]).astype(np.float32)
    sess.run(None, {sess.get_inputs()[0].name: x})
    del sess
time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 45)
print("connections:", len(hits), hits, flush=True)
