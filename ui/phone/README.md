# JARVIS auf dem Handy: Shell + Gerätedienst

**Stand 24.11. nachmittags:** Der Gerätedienst von handy-linux läuft auf 127.0.0.1:**8765** mit eigenem Schema (`/api/status` mit
`akku_prozent`, `wlan_an` …; POST `/api/wlan {an}`, `/api/helligkeit {wert}` …). Die UI versteht beide Schemas. Die Shell läuft deshalb
auf **8770** mit `DEVICE_URL=http://127.0.0.1:8765`, `DEVICE_PREFIX=/api/`, `DEVICE_ORIGIN=https://JARVIS_HOST:8443`
(siehe jarvis-shell.service), Kiosk-URL `http://127.0.0.1:8770/`.

**Warum die Seite nicht direkt von https://JARVIS_HOST:8443 kommen kann:** WebKitGTK 2.54 blockiert `fetch` von einer
HTTPS-Seite zu `http://127.0.0.1`/`localhost` (TypeError: Load failed, GET und POST, getestet). Chromium erlaubt es.

```
cage + WebKit (Kiosk)  ──▶  http://127.0.0.1:8765  jarvis-shell.py  (diese Datei, Python nur stdlib)
                               ├─ /            lokale Kopie der UI (synct von jarvis /api/manifest)
                               ├─ /api/*   ──▶ https://JARVIS_HOST:8443 (jarvis-ui, SSE/Upload gestreamt)
                               └─ /device/* ─▶ http://127.0.0.1:8766  Gerätedienst (handy-linux), Header X-Jarvis-Device: 1
```

- 127.0.0.1 ist ein sicherer Kontext: Mikrofon geht, in WebKitGTK 2.54 geprüft (isSecureContext, getUserMedia, MediaRecorder).
- Offline: UI kommt aus der lokalen Kopie, `/api/*` antwortet 503 → UI zeigt „WLAN einschalten“ bzw. „jarvis nicht erreichbar“.
- Ohne jemals erfolgreichen Sync: eingebaute Notseite mit WLAN-Knopf.
- Self-Update: Die Shell synct alle 60 s; `/api/version` liefert den Build der LOKALEN Kopie, die UI lädt dann in Ruhe neu.
- POST-Anfragen an /api und /device nur mit Origin http://127.0.0.1:8765 bzw. localhost:8765 (sonst 403).

## Gerätedienst-Vertrag (Port 8766, nur 127.0.0.1, nur mit Header `X-Jarvis-Device: 1`)

| Methode | Pfad | Body | Antwort |
|---|---|---|---|
| GET | /device/status | – | `{battery:{percent,charging,status}, wifi:{enabled,connected,ssid,signal}, temp:{cpu_c,battery_c,warn}, brightness:{percent}, volume:{percent,muted}, screen:{on}}` (unbekannt = null) |
| POST | /device/wifi | `{on: bool}` | `{ok:true,…}` |
| POST | /device/brightness | `{percent: 1–100}` | |
| POST | /device/volume | `{percent: 0–100}` und/oder `{muted: bool}` | |
| POST | /device/screen | `{on: bool}` | |
| POST | /device/reboot, /device/poweroff | `{}` | `{ok:true, in_s:3}` – erst nach ~3 s ausführen |

Fehler: 4xx/5xx mit `{"detail": "<deutscher Text>"}`. `mock-device.py` ist eine Attrappe genau dieses Vertrags (Tests auf dem PC).

## Test auf dem PC

```bash
python3 -I phone/mock-device.py &
JARVIS_CA=$PWD/jarvis-ca.crt SHELL_DATA=/tmp/js python3 -I phone/jarvis-shell.py &
# Browser: http://127.0.0.1:8765/
```
