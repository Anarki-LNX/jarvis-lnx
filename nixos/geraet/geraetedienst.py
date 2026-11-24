#!/usr/bin/env python3
"""JARVIS-Gerätedienst für das Handy (courbet).

Läuft als root, NUR an 127.0.0.1 gebunden. Kleine JSON-API für die Kiosk-Oberfläche:
  GET  /api/status                       Akku, Laden, Temperatur, WLAN, IP, Uptime, Helligkeit, Lautstärke, Bildschirm
  POST /api/wlan        {"an": true|false}
  POST /api/neustart    {}
  POST /api/ausschalten {}
  POST /api/helligkeit  {"wert": 0-100}
  POST /api/lautstaerke {"wert": 0-100}
  POST /api/bildschirm  {"an": true|false}
  POST /api/kiosk-neu   {}                Kiosk-Browser neu starten (Kiosk-Schleife wählt JARVIS oder Notfallseite)
  GET  /notfall          lokale Notfallseite (WLAN an, Neustart), falls JARVIS nicht erreichbar ist
Schreibende Aufrufe nur von erlaubten Ursprüngen (Origin-Header) und werden ins Journal geschrieben.
"""
import json, os, glob, subprocess, syslog, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("GERAET_PORT", "8765"))
ERLAUBT = set(os.environ.get("GERAET_ORIGINS", "https://" + os.environ.get("JARVIS_HOST", "jarvis.local") + ":8443 http://127.0.0.1:8765").split())
NOTFALL = os.environ.get("GERAET_NOTFALL", os.path.join(os.path.dirname(__file__), "notfall.html"))
WLAN_IF = os.environ.get("GERAET_WLAN_IF", "wld0")
JARVIS_UID = int(os.environ.get("GERAET_JARVIS_UID", "1000"))

syslog.openlog("jarvis-geraet")


def log(msg):
    syslog.syslog(syslog.LOG_NOTICE, msg)


def lies(p, default=None):
    try:
        with open(p) as f:
            return f.read().strip()
    except OSError:
        return default


def cmd(args, als_jarvis=False, timeout=10):
    env = dict(os.environ, LC_ALL="C")
    if als_jarvis:
        env["XDG_RUNTIME_DIR"] = f"/run/user/{JARVIS_UID}"
        args = ["runuser", "-u", "jarvis", "--"] + args
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode, r.stdout
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def backlight():
    b = sorted(glob.glob("/sys/class/backlight/*"))
    return b[0] if b else None


def status():
    q = "/sys/class/power_supply/qcom_qg"
    cap = lies(f"{q}/capacity")
    st = lies(f"{q}/status")
    t = lies(f"{q}/temp")
    temps = [int(x) for x in (lies(p) for p in glob.glob("/sys/class/thermal/thermal_zone*/temp")) if x and x.lstrip("-").isdigit()]
    _, radio = cmd(["nmcli", "-t", "radio", "wifi"])
    _, akt = cmd(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "dev", "wifi"])
    ssid = sig = None
    for z in akt.splitlines():
        if z.startswith("yes:"):
            _, ssid, sig = (z.split(":") + [None, None])[:3]
            break
    _, ipa = cmd(["ip", "-4", "-o", "addr", "show", WLAN_IF])
    ip = ipa.split()[3].split("/")[0] if len(ipa.split()) > 3 else None
    bl = backlight()
    hell = None
    bild = None
    if bl:
        try:
            hell = round(int(lies(f"{bl}/brightness")) * 100 / int(lies(f"{bl}/max_brightness")))
        except (TypeError, ValueError):
            pass
        bild = lies(f"{bl}/bl_power") == "0"
    rc, vol = cmd(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], als_jarvis=True)
    lautst = None
    if rc == 0 and len(vol.split()) > 1:
        try:
            lautst = round(float(vol.split()[1]) * 100)
        except ValueError:
            pass
    return {
        "akku_prozent": int(cap) if cap and cap.isdigit() else None,
        "laedt": None if st is None else st == "Charging",
        "akku_temp": round(int(t) / 10, 1) if t and t.lstrip("-").isdigit() else None,
        "temp_max": round(max(temps) / 1000, 1) if temps else None,
        # Warnung: Akku > 45 °C oder SoC > 80 °C (60 °C SoC unter Last ist normal)
        "temp_warn": bool((t and t.lstrip("-").isdigit() and int(t) > 450) or (temps and max(temps) > 80000)),
        "wlan_an": radio.strip() == "enabled",
        "wlan_ssid": ssid or None,
        "wlan_signal_prozent": int(sig) if sig and sig.isdigit() else None,
        "ip": ip,
        "uptime_s": int(float((lies("/proc/uptime") or "0").split()[0])),
        "helligkeit_prozent": hell,
        "lautstaerke_prozent": lautst,
        "bildschirm_an": bild,
        "zeit": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def wert(d):
    v = d.get("wert")
    if not isinstance(v, (int, float)) or not 0 <= v <= 100:
        raise ValueError("wert 0-100")
    return int(v)


ALIAS = {"/api/wifi": "/api/wlan", "/api/reboot": "/api/neustart", "/api/poweroff": "/api/ausschalten",
         "/api/brightness": "/api/helligkeit", "/api/volume": "/api/lautstaerke", "/api/screen": "/api/bildschirm"}


def aktion(pfad, d):
    # englische Pfade/Felder (Vertrag jarvis-shell) auf die deutschen abbilden
    pfad = ALIAS.get(pfad, pfad)
    if "on" in d and "an" not in d:
        d["an"] = d["on"]
    if "percent" in d and "wert" not in d:
        d["wert"] = d["percent"]
    if pfad == "/api/wlan":
        an = bool(d.get("an"))
        rc, out = cmd(["nmcli", "radio", "wifi", "on" if an else "off"])
        return {"ok": rc == 0, "wlan_an": an}
    if pfad in ("/api/neustart", "/api/ausschalten"):
        ziel = "reboot" if pfad == "/api/neustart" else "poweroff"
        rc, _ = cmd(["systemd-run", "--quiet", "--collect", f"--unit=jarvis-geraet-{ziel}", "--on-active=3", "systemctl", ziel])
        return {"ok": rc == 0, "in_s": 3}
    if pfad == "/api/helligkeit":
        bl = backlight()
        v = wert(d)
        mx = int(lies(f"{bl}/max_brightness"))
        with open(f"{bl}/brightness", "w") as f:
            f.write(str(max(1, v * mx // 100)))
        return {"ok": True, "helligkeit_prozent": v}
    if pfad == "/api/lautstaerke":
        v = wert(d)
        rc, _ = cmd(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{v}%"], als_jarvis=True)
        return {"ok": rc == 0, "lautstaerke_prozent": v}
    if pfad == "/api/kiosk-neu":
        rc, out = cmd(["ps", "-eo", "pid,comm"])
        pids = [z.split()[0] for z in out.splitlines() if "epiphany" in z]
        for p in pids:
            cmd(["kill", p])
        return {"ok": True, "beendet": len(pids)}
    if pfad == "/api/bildschirm":
        an = bool(d.get("an"))
        with open(f"{backlight()}/bl_power", "w") as f:
            f.write("0" if an else "4")
        return {"ok": True, "bildschirm_an": an}
    return None


class H(BaseHTTPRequestHandler):
    server_version = "jarvis-geraet/1"

    def _cors(self):
        o = self.headers.get("Origin")
        if o in ERLAUBT:
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Vary", "Origin")

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):  # keine Zugriffslogs fuer GET
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/status":
            return self._json(200, status())
        if self.path in ("/notfall", "/notfall.html", "/"):
            try:
                b = open(NOTFALL, "rb").read()
            except OSError:
                return self._json(404, {"ok": False})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            return self.wfile.write(b)
        return self._json(404, {"ok": False, "fehler": "unbekannt"})

    def do_POST(self):
        o = self.headers.get("Origin")
        if o not in ERLAUBT:
            log(f"abgelehnt (Origin {o!r}): {self.path}")
            return self._json(403, {"ok": False, "fehler": "Ursprung nicht erlaubt"})
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 4096)
            d = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(d, dict):
                raise ValueError
            r = aktion(self.path, d)
        except (ValueError, json.JSONDecodeError) as e:
            return self._json(400, {"ok": False, "fehler": str(e) or "ungueltig"})
        if r is None:
            return self._json(404, {"ok": False, "fehler": "unbekannt"})
        log(f"Aktion {self.path} {json.dumps(d)} von {o} -> {json.dumps(r)}")
        return self._json(200, r)


if __name__ == "__main__":
    log(f"Start auf 127.0.0.1:{PORT}, Ursprünge: {' '.join(sorted(ERLAUBT))}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
