#!/usr/bin/env python3
"""Attrappe des Geraetedienstes (Vertrag mit handy-linux) – nur zum Testen der UI auf dem PC.

GET  /device/status
POST /device/wifi {on} | /device/brightness {percent} | /device/volume {percent}|{muted} | /device/screen {on}
POST /device/reboot {} | /device/poweroff {}   -> {"ok": true, "in_s": 3}
Alle Anfragen brauchen den Header X-Jarvis-Device: 1 (setzt jarvis-shell). Port: MOCK_PORT (8766).
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

S = {"battery": {"percent": 78, "charging": True, "status": "Charging"},
     "wifi": {"enabled": True, "connected": True, "ssid": "Heimnetz", "signal": 72},
     "temp": {"cpu_c": 41.5, "battery_c": 31.0, "warn": False},
     "brightness": {"percent": 60}, "volume": {"percent": 55, "muted": False}, "screen": {"on": True}}
LOG = []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _j(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.headers.get("X-Jarvis-Device") != "1":
            return self._j(403, {"detail": "nur über jarvis-shell"})
        if self.path == "/device/status":
            return self._j(200, S)
        if self.path == "/device/_log":
            return self._j(200, {"log": LOG})
        self._j(404, {"detail": "unbekannt"})

    def do_POST(self):
        if self.headers.get("X-Jarvis-Device") != "1":
            return self._j(403, {"detail": "nur über jarvis-shell"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            d = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._j(400, {"detail": "kein JSON"})
        p = self.path
        LOG.append([p, d])
        if p == "/device/wifi":
            S["wifi"].update(enabled=bool(d.get("on")), connected=bool(d.get("on")), ssid="Heimnetz" if d.get("on") else None)
        elif p == "/device/brightness":
            S["brightness"]["percent"] = max(1, min(100, int(d.get("percent", 50))))
        elif p == "/device/volume":
            if "percent" in d:
                S["volume"]["percent"] = max(0, min(100, int(d["percent"])))
            if "muted" in d:
                S["volume"]["muted"] = bool(d["muted"])
        elif p == "/device/screen":
            S["screen"]["on"] = bool(d.get("on"))
        elif p in ("/device/reboot", "/device/poweroff"):
            return self._j(200, {"ok": True, "in_s": 3})
        elif p == "/device/_set":  # Testhilfe: Zustand direkt setzen
            for k, v in d.items():
                S[k].update(v)
        else:
            return self._j(404, {"detail": "unbekannt"})
        self._j(200, {"ok": True, **S})


ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("MOCK_PORT", "8766"))), H).serve_forever()
