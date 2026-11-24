#!/usr/bin/env python3
"""Attrappe des Geraetedienstes von handy-linux (deren Schema), nur fuer Tests der UI auf dem PC.

GET  /api/status -> {akku_prozent, laedt, akku_temp, temp_max, wlan_an, wlan_ssid, wlan_signal_prozent, ip, uptime_s,
                     helligkeit_prozent, lautstaerke_prozent, bildschirm_an, zeit}
POST /api/wlan {an} | /api/neustart {} | /api/ausschalten {} | /api/helligkeit {wert} | /api/lautstaerke {wert}
     /api/bildschirm {an} | /api/kiosk-neu {}
CORS nur fuer ORIGIN (Standard https://$NUORB_SERVER_IP:8443); POST mit anderem Origin -> 403. Port MOCK_PORT (8765).
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ORIGIN = os.environ.get("ORIGIN", "https://" + os.environ.get("NUORB_SERVER_IP", "nuorb.local") + ":8443")
S = {"akku_prozent": 64, "laedt": False, "akku_temp": 30.5, "temp_max": 43.0, "wlan_an": True, "wlan_ssid": "Heimnetz",
     "wlan_signal_prozent": 68, "ip": "192.0.2.14", "uptime_s": 1234, "helligkeit_prozent": 55,
     "lautstaerke_prozent": 70, "bildschirm_an": True, "zeit": ""}
LOG = []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _cors(self):
        if self.headers.get("Origin") == ORIGIN:
            self.send_header("Access-Control-Allow-Origin", ORIGIN)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Vary", "Origin")

    def _j(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self._cors()
        self.end_headers()
        self.wfile.write(b)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/status":
            S["zeit"] = time.strftime("%H:%M:%S")
            return self._j(200, S)
        if self.path == "/_log":
            return self._j(200, {"log": LOG})
        self._j(404, {"fehler": "unbekannt"})

    def do_POST(self):
        if self.headers.get("Origin") != ORIGIN and self.path != "/_set":
            return self._j(403, {"fehler": "Origin nicht erlaubt"})
        n = int(self.headers.get("Content-Length") or 0)
        d = json.loads(self.rfile.read(n) or b"{}")
        LOG.append([self.path, d])
        p = self.path
        if p == "/api/wlan":
            S.update(wlan_an=bool(d.get("an")), wlan_ssid="Heimnetz" if d.get("an") else None)
        elif p == "/api/helligkeit":
            S["helligkeit_prozent"] = int(d.get("wert", 50))
        elif p == "/api/lautstaerke":
            S["lautstaerke_prozent"] = int(d.get("wert", 50))
        elif p == "/api/bildschirm":
            S["bildschirm_an"] = bool(d.get("an"))
        elif p == "/_set":
            S.update(d)
        elif p not in ("/api/neustart", "/api/ausschalten", "/api/kiosk-neu"):
            return self._j(404, {"fehler": "unbekannt"})
        self._j(200, {"ok": True})


ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("MOCK_PORT", "8765"))), H).serve_forever()
