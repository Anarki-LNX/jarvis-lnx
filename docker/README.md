# NuOrb – Server als Docker-Container

Dein eigener Sprachassistent in **einem** Container: Hermes Agent als Gehirn-Framework, die NuOrb-Oberfläche mit Orb,
ein Admin-Panel, Spracherkennung (Parakeet, läuft auf der CPU) und Sprachausgabe (Piper). Denken lässt du entweder
dein eigenes **Ollama** (z. B. Gaming-PC), **Claude** über die Anthropic-API oder **beides** mit automatischem Wechsel.

Die **NuOrb-App für Android** und jeder Browser im Heimnetz verbinden sich damit, nachdem sie einmal gekoppelt
wurden (QR-Code oder Code im Admin-Panel).

> **Kurzfassung:** `.env` anlegen → `docker compose up -d` → `https://<server>:8444` öffnen → Einrichtungscode aus
> dem Log eingeben → Gehirn wählen → Handy koppeln. Dauert etwa 10 Minuten, davon die meiste Zeit Downloads.

---

## Voraussetzungen

| | Minimum | Empfohlen |
|---|---|---|
| Architektur | amd64 (x86-64) oder arm64 (z. B. Raspberry Pi 5) | amd64 |
| CPU | 4 Kerne | 6+ Kerne (Spracherkennung läuft auf der CPU, ~1,5 s pro Satz) |
| RAM | 4 GB frei | 6 GB |
| Platte | 8 GB | 15 GB |
| Software | Docker Engine 24+ mit Compose v2 (`docker compose version`) | aktuelle Version |
| Netz | Server und Handy im selben Heimnetz **oder** per VPN verbunden | feste IP für den Server |
| Gehirn | Ollama im Heimnetz **oder** ein Anthropic-API-Schlüssel | beides |

**Downloads:** Image ca. 1,2 GB (entpackt ~3,5 GB). Beim ersten Start lädt der Container zusätzlich
**~530 MB** Sprachmodelle (Spracherkennung Parakeet 464 MB von GitHub, Stimme ~60 MB von Hugging Face). Danach läuft
die Sprachverarbeitung ohne Internet.

**Ollama:** Hermes verlangt mindestens **64k Token Kontext** und lehnt kleinere Modelle ab. Am Ollama-Server
`OLLAMA_CONTEXT_LENGTH=65536` setzen (oder eine Modellvariante mit `PARAMETER num_ctx 65536` anlegen) und Ollama im
LAN erreichbar machen (`OLLAMA_HOST=0.0.0.0`, Port 11434 nur für den NuOrb-Server freigeben). Geeignet sind Modelle
mit Werkzeugnutzung, z. B. Gemma 4 26B oder gpt-oss 20B (16 GB VRAM).

**Claude:** Schlüssel unter <https://console.anthropic.com>, dort ein Ausgabenlimit setzen. Eine kurze Sprachfrage
kostet mit Haiku etwa 0,1–0,5 Cent.

## Installation

### Wohin? Proxmox oder PC

* **Proxmox, VM (empfohlen):** Debian-13-VM mit 4–6 Kernen, 6 GB RAM, 20 GB Platte. Darin Docker installieren:
  `curl -fsSL https://get.docker.com | sh`.
* **Proxmox, LXC:** Debian-13-Container, *unprivilegiert*, unter *Optionen → Features* `nesting=1` und `keyctl=1`.
  Darin Docker wie oben. (Docker im LXC ist von Proxmox nicht offiziell unterstützt, läuft aber meist; sonst VM.)
* **PC/Server:** Linux mit Docker Engine, oder Windows/macOS mit Docker Desktop.

### Fünf Schritte

```bash
# 1. Dateien holen
git clone https://github.com/Anarki-LNX/nuorb && cd nuorb/docker

# 2. Einstellungen: mindestens NUORB_HOSTS (IP/Name des Servers), Sprache, Zeitzone
cp .env.example .env && nano .env

# 3. Starten (lädt das fertige Image; ist es nicht abrufbar, baut Compose es lokal, ~10 min)
docker compose up -d

# 4. Einrichtungscode anzeigen
docker compose logs nuorb | grep -i einrichtungscode
```

5. Im Browser **`https://<server-ip>:8444`** öffnen. Beim ersten Mal warnt der Browser vor dem Zertifikat
   (selbst ausgestellt, siehe unten) → „Erweitert → Trotzdem fortfahren“. Code eingeben, Passwort festlegen. Danach
   führt die **Einrichtung** durch Sprache/Stimme, Gehirn (Ollama-Adresse mit „Verbindung testen“ und Modellauswahl,
   Claude-Schlüssel oder beides) und zeigt den Fortschritt der Modell-Downloads.

`<server-ip>` ist die Adresse des Rechners bzw. der VM/des LXC, auf dem Docker läuft (`hostname -I`).

### Handy koppeln

1. Im Admin-Panel **Gerät koppeln → Neuen Kopplungscode erzeugen**.
2. **App:** NuOrb-App öffnen → „Server hinzufügen“ → **QR-Code scannen**. Ohne Kamera: Adresse
   (`https://<server-ip>:8443`) und Code von Hand eingeben; die App zeigt dann den Zertifikats-Fingerabdruck, der
   mit dem im Admin-Panel übereinstimmen muss.
3. **Browser** (PC, Tablet): `https://<server-ip>:8443` öffnen und den Code eintippen.

Ein Code gilt 10 Minuten und nur einmal. Gekoppelte Geräte stehen im Admin-Panel und lassen sich dort entkoppeln.

### Updates und Sicherung

```bash
docker compose pull && docker compose up -d        # neues Image, Daten bleiben
docker run --rm -v nuorb_data:/d -v "$PWD":/b debian tar czf /b/nuorb-data.tgz -C /d .   # Sicherung
```

## Was wo liegt

| Volume | Inhalt |
|---|---|
| `data` → `/opt/data` | Hermes-Konfiguration, Schlüssel (`.env`, im Admin nur als „gesetzt …1234“ sichtbar), Gedächtnis, Sitzungen, Zeitpläne, Skills; unter `nuorb/`: Admin-Passwort-Hash, Sicherungen, Zertifikate, gekoppelte Geräte, Protokolle |
| `models` → `/opt/models` | Stimmen (`voices/`) und Spracherkennung (`stt/`) |

## Netz und Sicherheit

| Port | Dienst |
|---|---|
| 8443 | Oberfläche und App-Schnittstelle (nur gekoppelte Geräte) |
| 8444 | Admin-Panel (Passwort) |

* **Kein Port ins Internet.** Nicht im Router freigeben. Unterwegs: VPN ins Heimnetz (WireGuard, Tailscale,
  Fritzbox-VPN). Zugriffe sind nur aus privaten Netzen und Tailscale (100.64.0.0/10) erlaubt.
* **Kopplung:** Ohne gekoppeltes Gerät liefert der Server nichts außer der Kopplungsseite. Auf dem Server liegen nur
  Hashes der Gerätetoken.
* **Bestätigungskarten:** Vor gefährlichen Aktionen fragt NuOrb nach (`approvals.mode: manual`). Der Agent hat ein
  Terminal *im Container*; der Container ist seine Sandbox.
* **Keine Telemetrie**, keine Update-Checks. Nach außen geht nur: Claude (Gesprächstext, wenn gewählt) und die
  einmaligen Modell-Downloads.
* **Schlüssel** im Admin-Panel eingeben (oder einmalig per `.env`; danach dort löschen).

### Zertifikat

Standard (`NUORB_TLS=selfsigned`): Der Container erzeugt eine eigene kleine Zertifizierungsstelle und ein
Zertifikat für die Namen in `NUORB_HOSTS`. Die App bekommt den **Fingerabdruck dieser CA im QR-Code** und vertraut
genau diesem Server, ohne Warnung. Browser warnen einmal; wer das nicht will, importiert die CA
(`https://<server-ip>:8443/nuorb-ca.crt`) und vergleicht den Fingerabdruck mit dem im Admin-Panel.

Eigenes Zertifikat (z. B. `tailscale cert`, eigene CA, Let's Encrypt per DNS): `NUORB_TLS=custom` und den Ordner
mit `fullchain.pem`/`privkey.pem` in `compose.yaml` unter `/certs` einbinden. Hinter einem Reverse-Proxy (z. B.
Caddy): `NUORB_TLS=off`, `NUORB_BIND=127.0.0.1`, `NUORB_PUBLIC_URL` auf die Proxy-Adresse.

**Server automatisch finden (mDNS):** Mit `network_mode: host` und `NUORB_MDNS=1` kündigt sich der Server als
`_nuorb._tcp` im Heimnetz an, und die App listet ihn. Im normalen Bridge-Netz geht das nicht; dann IP eintragen.

## Gehirn und Sprache

| Modus | Bedeutung |
|---|---|
| Lokal | Nur Ollama. Nichts verlässt dein Netz. |
| Automatisch | Ollama; ist es nicht erreichbar, übernimmt Claude. |
| Remote | Nur Claude (Haiku, Sonnet oder Opus). |

Umschalten im Admin unter „Modell & Fallback“ oder in der Oberfläche (Abzeichen oben antippen). Eigenes Ollama im
selben Compose-Projekt: `docker compose --profile ollama up -d`, Adresse dann `http://ollama:11434`.

Sprache **Deutsch oder Englisch** wählst du in der Einrichtung; dazu passende Stimmen (Thorsten, Kerstin; Alan, Ryan,
Amy). Stimmen-Lizenzen: <https://huggingface.co/rhasspy/piper-voices> (Thorsten: CC0). Die Orb-Oberfläche ist
derzeit noch deutschsprachig.

Optional „Hey NuOrb“ in der App: Die openWakeWord-Dateien (`melspectrogram.tflite`, `embedding_model.tflite`,
`hey_nuorb_v0.1.tflite`) können im Volume unter `nuorb/wakeword/` liegen; die App fragt sonst selbst beim
offiziellen Projekt an.

## Nicht enthalten

Steuerung des Xiaomi-Handys (NixOS-Kiosk) und Haus-/Wetterstation-Anbindungen des Autors. Eigene Werkzeuge bindest
du im Admin unter „MCP-Server“ an (z. B. Home Assistant).

## Fehlersuche

```bash
docker compose ps                    # läuft er? (healthy)
docker compose logs -f nuorb        # alles; Zeilen [nuorb-init], [nuorb-models], [pair], Hermes
docker compose exec nuorb /command/s6-svstat /run/service/nuorb-ui    # einzelner Dienst
```

| Problem | Lösung |
|---|---|
| Browser: „Verbindung nicht sicher“ | Erwartet beim selbst ausgestellten Zertifikat, einmal bestätigen (oder CA importieren). |
| Einrichtungscode nicht im Log | `docker compose exec nuorb cat /opt/data/nuorb/admin/setup-code.txt` |
| „Nur im Heimnetz erreichbar“ | Zugriff kommt aus einem nicht erlaubten Netz → `NUORB_ALLOWED_NETS` ergänzen. |
| Spracherkennung offline nach dem Start | Modelle laden noch (Fortschritt in der Einrichtung). Ohne Internet: Meldung dort, Container versucht es weiter. |
| NuOrb antwortet „hat noch kein Gehirn“ | Einrichtung im Admin abschließen. |
| Antworten leer oder Fehler „context window … below 64,000“ | Ollama-Kontext zu klein, siehe oben. |
| App: Zertifikatsfehler | Server-IP fehlt in `NUORB_HOSTS` → eintragen, `docker compose up -d`, neu koppeln. |
| Ollama „nicht erreichbar“ | Vom Server aus testen: `curl http://<ollama-ip>:11434/api/version`; Ollama auf `0.0.0.0` lauschen lassen, Firewall. |
| Port 8443/8444 belegt | `NUORB_UI_PORT_PUBLIC` / `NUORB_ADMIN_PORT_PUBLIC` ändern. |
| Uhrzeit falsch | `TZ` in der `.env` setzen. |

## Für Entwickler

* `docker/src/` ist eine bereinigte Kopie von nuorb-ui, nuorb-admin und dem STT-Router
  (`python3 docker/tools/prepare-src.py`; bricht ab, wenn private Werte übrig bleiben).
* `app/` lädt die Originalserver unverändert als Modul und ergänzt Kopplung, s6-Dienste, Einrichtung.
* Image bauen: `docker compose build`. Veröffentlichung per GitHub Actions bei Tag `v*` (`github/workflows/docker.yml`).
* Test ohne GPU: `python3 docker/tools/mock-llm.py &`, dann
  `docker compose -p nuorb-test -f compose.yaml -f compose.test.yaml --env-file .env.test up -d --build` und
  `python3 docker/tools/e2e-test.py --setup-code <code>`.

---

## English summary

NuOrb runs as one Docker container (amd64/arm64): Hermes Agent, the NuOrb web UI, admin panel, local speech
recognition (Parakeet, CPU) and speech synthesis (Piper). The LLM is your own Ollama (≥ 64k context required), the
Claude API, or both with automatic fallback.

1. `git clone https://github.com/Anarki-LNX/nuorb && cd nuorb/docker`
2. `cp .env.example .env` – set `NUORB_HOSTS` (server IP), `NUORB_LANG=en`, `TZ`
3. `docker compose up -d` (first start downloads ~530 MB of speech models)
4. `docker compose logs nuorb | grep -i "setup code"`
5. Open `https://<server-ip>:8444`, enter the code, set a password, follow the setup (language, brain), then
   “Pair device” → scan the QR code with the NuOrb app or enter the code at `https://<server-ip>:8443`.

Never expose the ports to the internet; use a VPN. The QR code carries the fingerprint of the server's own CA, so the
app trusts exactly this server.
