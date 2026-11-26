# NuOrb – Server als Docker-Container

Dein eigener Sprachassistent in **einem** Container: Hermes Agent als Gehirn-Framework, die NuOrb-Oberfläche mit Orb,
ein Admin-Panel, Spracherkennung (Parakeet, läuft auf der CPU) und Sprachausgabe (Piper). Denken lässt du entweder
dein eigenes **Ollama** (z. B. Gaming-PC), **Claude** über die Anthropic-API oder **beides** mit automatischem Wechsel.

Die **NuOrb-App für Android** und jeder Browser im Heimnetz verbinden sich damit, nachdem sie einmal gekoppelt
wurden (QR-Code oder Code im Admin-Panel).

> **Am einfachsten:** `curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/install.sh | bash -s -- --lang de`
> – prüft Docker und Firewall, fragt kurz nach, startet NuOrb und zeigt Adresse und Einrichtungscode.
> Ausführliche Anleitung: [INSTALL.de.md](../INSTALL.de.md) · [INSTALL.md](../INSTALL.md) (English).
> Von Hand: `.env` anlegen → `docker compose up -d` → `https://<server>:8444` öffnen → Einrichtungscode eingeben →
> Gehirn wählen → Smartphone koppeln. Dauert etwa 10 Minuten, davon die meiste Zeit Downloads.

---

## Voraussetzungen

| | Minimum | Empfohlen |
|---|---|---|
| Architektur | amd64 (x86-64) oder arm64 (z. B. Raspberry Pi 5) | amd64 |
| CPU | 4 Kerne | 6+ Kerne (Spracherkennung läuft auf der CPU, ~1,5 s pro Satz) |
| RAM | 4 GB frei | 6 GB |
| Platte | 8 GB | 15 GB |
| Software | Docker Engine 24+ mit Compose v2 (`docker compose version`) | aktuelle Version |
| Netz | Server und Smartphone im selben Heimnetz **oder** per VPN verbunden | feste IP für den Server |
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
docker compose logs nuorb | grep -i "setup code"
```

5. Im Browser **`https://<server-ip>:8444`** öffnen. Beim ersten Mal warnt der Browser vor dem Zertifikat
   (selbst ausgestellt, siehe unten) → „Erweitert → Trotzdem fortfahren“. Code eingeben, Passwort festlegen. Danach
   führt die **Einrichtung** durch Sprache/Stimme, Gehirn (Ollama-Adresse mit „Verbindung testen“ und Modellauswahl,
   Claude-Schlüssel oder beides) und zeigt den Fortschritt der Modell-Downloads.

`<server-ip>` ist die Adresse des Rechners bzw. der VM/des LXC, auf dem Docker läuft (`hostname -I`).

### Smartphone koppeln

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

### Umstieg von einer älteren Installation (bis v0.3.x)

Seit v0.4.0 heißen Compose-Projekt, Dienst und Container `nuorb` (vorher `nuorb` / `nuorb` /
`nuorb-nuorb-1`), das Image seit v0.3.0 `ghcr.io/anarki-lnx/nuorb`. Die Daten bleiben erhalten: Die neue
`compose.yaml` nutzt die bisherigen Volumes `nuorb_data` und `nuorb_models` unter festem Namen.

```bash
cd nuorb/docker                                  # Ordner mit deiner .env
docker compose -p nuorb down                # alten Container stoppen – OHNE -v, sonst sind die Daten weg
git pull                                         # neue compose.yaml (oder die Datei aus dem Repo holen)
docker compose pull && docker compose up -d      # startet „nuorb“ mit denselben Daten
```

Passwort, Schlüssel, Gedächtnis, Zertifikate und gekoppelte Geräte bleiben, die App muss nicht neu gekoppelt werden.
Docker meldet beim ersten Start einmalig, dass die Volumes von einem anderen Projekt angelegt wurden; das ist erwartet.

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
  einmaligen Modell-Downloads. onnxruntime (ab 1.32) würde von sich aus Nutzungsdaten an Microsoft senden; das Image
  schaltet das für jeden Prozess ab (`ORT_DISABLE_TELEMETRY=1`). Nachprüfen, komplett offline:
  `tools/telemetry-check.sh ghcr.io/anarki-lnx/nuorb:latest`.
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
`_nuorb._tcp` (und für ältere Apps `_nuorb._tcp`) im Heimnetz an, und die App listet ihn. Im normalen Bridge-Netz geht das nicht; dann IP eintragen.

## Gehirn und Sprache

| Modus | Bedeutung |
|---|---|
| Lokal | Nur dein lokaler Server (Ollama, llama.cpp, vLLM, LM Studio …). Nichts verlässt dein Netz. |
| Automatisch | Lokaler Server; ist er nicht erreichbar, übernimmt Claude. |
| Remote | Nur Claude (Haiku, Sonnet oder Opus). |

Statt Ollama geht **jeder OpenAI-kompatible Server** (llama.cpp `llama-server`, vLLM, LM Studio, LocalAI): in der
Einrichtung Typ „OpenAI-kompatibel“ wählen, Adresse mit Port und ggf. API-Key eintragen. Startbefehle mit Tool-Calling
und 64k Kontext: [INSTALL.de.md](../INSTALL.de.md#llamacpp-vllm-lm-studio-statt-ollama). In der `.env`: `NUORB_INIT_LLM_TYPE=openai`,
`NUORB_INIT_OLLAMA_URL`, `NUORB_INIT_OLLAMA_MODEL`, `NUORB_INIT_LLM_API_KEY`.

Umschalten im Admin unter „Modell & Fallback“ oder in der Oberfläche (Abzeichen oben antippen). Eigenes Ollama im
selben Compose-Projekt: `docker compose --profile ollama up -d`, Adresse dann `http://ollama:11434`.

**Name:** Das Produkt heißt NuOrb, das Weckwort „Hey NuOrb“ (`BRAND_NAME`). Wie du den Assistenten ansprichst,
legst du in der Einrichtung fest oder einfach im Gespräch: „Ab jetzt heißt du Max.“ Beim ersten Gespräch stellt er
sich vor und fragt auch nach deinem Namen.

Sprache **Deutsch oder Englisch** wählst du in der Einrichtung (Oberfläche: `UI_LANG=auto` folgt der Gerätesprache; Admin-Webinterface: `ADMIN_LANG=en` oder `de`, im Browser umschaltbar); dazu passende Stimmen: Thorsten (Deutsch) und Joe (Englisch), beide CC0 und auch kommerziell nutzbar. Bis v0.6.2
angebotene Stimmen ohne diese Freigabe (Alan, Ryan, Amy, Kerstin low, Thorsten high) stellt das Update automatisch um
und löscht ihre Dateien; Details in `THIRD_PARTY_LICENSES.md`. 

Optionales Weckwort in der App: Die openWakeWord-Dateien (`melspectrogram.tflite`, `embedding_model.tflite`,
`hey_nuorb_v0.1.tflite`) können im Volume unter `nuorb/wakeword/` liegen; die App fragt sonst selbst beim
offiziellen Projekt an.

## Smart Home (optional)

NuOrb kann Licht, Steckdosen, Schalter, Szenen und Sensoren aus **Home Assistant** und/oder **ioBroker** abfragen und
schalten. Standardmäßig ist das **aus**.

**Einschalten in der Verwaltung:** „Smart Home“ öffnen, Adresse und Zugang eintragen (Home Assistant: Long-Lived
Access Token aus dem HA-Profil; ioBroker: Adapter `rest-api` mit Benutzer/Passwort oder Token), „Verbindung testen“,
dann einschalten. Der Zugang landet in `/opt/data/smarthome.env` (nur für den Besitzer lesbar) und wird nie angezeigt.

**Oder per `.env`** (z. B. für automatische Installationen): Zugangsdatei ins Daten-Volume legen oder als
Docker-Secret einbinden (`NUORB_SMARTHOME_ZUGANG=/run/secrets/…`), dann `NUORB_SMARTHOME=1` und `docker compose up -d`.
`NUORB_SMARTHOME=0` schaltet beim Start aus; leer lässt die Einstellung der Verwaltung stehen.

```bash
docker compose exec -T nuorb sh -c 'umask 077; cat > /opt/data/smarthome.env' <<'EOF'
HA_URL=http://homeassistant.local:8123
HA_TOKEN=<Long-Lived Access Token>
EOF
```

Lesen läuft ohne Rückfrage, **Schalten zeigt immer eine Bestätigungskarte**. Der Container muss Home Assistant
(Port 8123) bzw. ioBroker (8093) im Netz erreichen.

**Ehrlich zur Zuverlässigkeit:** Mit **Claude** (z. B. Haiku) klappt das zuverlässig (im Test 36 von 37 Fragen
inhaltlich richtig). Mit einem **lokalen Ollama-Modell** ist es eingeschränkt: im Test etwa 10 von 16 richtig, typische
Fehler sind „Ich schalte jetzt …“ ohne tatsächlichen Aufruf. Lokal unbedingt unter „Model & Fallback“ die
Werkzeugsuche (`tools.tool_search`) ausschalten.

## Nicht enthalten

Steuerung des Xiaomi-Smartphones (NixOS-Kiosk) und Haus-/Wetterstation-Anbindungen des Autors. Weitere eigene
Werkzeuge bindest du im Admin unter „MCP-Server“ an.

## Fehlersuche

```bash
docker compose ps                    # läuft er? (healthy)
docker compose logs -f nuorb        # alles; Zeilen [nuorb-init], [nuorb-models], [nuorb-admin], [pair], Hermes
docker compose exec nuorb /command/s6-svstat /run/service/nuorb-ui    # einzelner Dienst
```

| Problem | Lösung |
|---|---|
| Browser: „Verbindung nicht sicher“ | Erwartet beim selbst ausgestellten Zertifikat, einmal bestätigen (oder CA importieren). |
| Einrichtungscode nicht im Log | `docker compose exec nuorb cat /opt/data/nuorb/admin/setup-code.txt` |
| „Nur im Heimnetz erreichbar“ | Zugriff kommt aus einem nicht erlaubten Netz → `NUORB_ALLOWED_NETS` ergänzen. |
| Spracherkennung offline nach dem Start | Modelle laden noch (Fortschritt in der Einrichtung). Meldet die Einrichtung „keine Internetverbindung“: siehe unten. |
| NuOrb antwortet „hat noch kein Gehirn“ | Einrichtung im Admin abschließen. |
| Antworten leer oder Fehler „context window … below 64,000“ | Ollama-Kontext zu klein, siehe oben. |
| App: Zertifikatsfehler | Server-IP fehlt in `NUORB_HOSTS` → eintragen, `docker compose up -d`, neu koppeln. |
| Ollama „nicht erreichbar“ | Die IP des Ollama-Rechners eintragen (z. B. `http://192.168.1.50:11434`), auch wenn Ollama auf demselben PC läuft; Ollama mit `OLLAMA_HOST=0.0.0.0` starten. `.local`-Namen lösen im Container oft nicht auf. Testen: `docker compose exec nuorb curl -s <adresse>/api/version`. Firewall siehe unten; die Einrichtung zeigt bei Timeout fertige Befehle (ufw, firewalld, Windows) mit der IP dieses Servers (`NUORB_HOST_IP`, sonst die erste IP aus `NUORB_HOSTS`). Alternative für denselben PC: in `compose.yaml` die `extra_hosts`-Zeile aktivieren, dann `http://host.docker.internal:11434`. |
| Port 8443/8444 belegt | `NUORB_UI_PORT_PUBLIC` / `NUORB_ADMIN_PORT_PUBLIC` ändern. |
| Uhrzeit falsch | `TZ` in der `.env` setzen. |

### Kein Netz im Container (ufw, firewalld)

Zeigt die Einrichtung „Der Container hat keine Internetverbindung“, steht der Modell-Download bei „Verbinde …“ oder
erreicht NuOrb dein Ollama nicht, blockiert meist die Firewall des Rechners den weitergeleiteten Verkehr der Container.

* **ufw** (Ubuntu, CachyOS, Arch …): Standard ist `DEFAULT_FORWARD_POLICY="DROP"`. Freigeben:
  ```bash
  sudo ufw default allow routed && sudo ufw reload
  ```
  Ollama auf demselben PC zusätzlich vom Docker-Netz erlauben: `sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp`.
* **firewalld** (Fedora, openSUSE): `sudo firewall-cmd --permanent --zone=trusted --add-interface=docker0 && sudo firewall-cmd --reload`
  (Compose-Netze heißen `br-…`; bei Bedarf ebenso hinzufügen).
* **Docker selbst ohne Netz:** Stehen in `/etc/docker/daemon.json` die Schlüssel `"iptables": false` oder
  `"bridge": "none"`, haben Container gar kein Netz. Beide Schlüssel entfernen, dann `sudo systemctl restart docker`.
  Docker legt danach eigene Firewall-Regeln an; veröffentlichte Ports (8443/8444) sind dann im Heimnetz erreichbar.
* **Ollama auf demselben PC, Test meldet „ConnectTimeout“:** ufw blockt Anfragen aus dem Docker-Netz an Port 11434:
  `sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp`.
* Danach `docker compose restart`. Prüfen: `docker compose exec nuorb curl -sI https://huggingface.co | head -1`.

Die Ports 8443/8444 bleiben dabei nur im Heimnetz erreichbar, solange du sie am Router nicht freigibst.

## Für Entwickler

* `docker/src/` ist eine bereinigte Kopie der NuOrb-Oberfläche, des NuOrb-Admin-Panels und des STT-Routers
  (`python3 docker/tools/prepare-src.py`; bricht ab, wenn private Werte übrig bleiben).
* `app/` lädt die Originalserver unverändert als Modul und ergänzt Kopplung, s6-Dienste, Einrichtung.
* Image bauen: `docker compose build`. Veröffentlichung per GitHub Actions bei Tag `v*` (`github/workflows/docker.yml`).
* Test ohne GPU: `python3 docker/tools/mock-llm.py &`, dann
  `docker compose -p nuorb-test -f compose.yaml -f compose.test.yaml --env-file .env.test up -d --build` und
  `python3 docker/tools/e2e-test.py --setup-code <code>`.

---

## English summary

The NuOrb server runs as one Docker container (amd64/arm64): Hermes Agent, the NuOrb web UI, admin panel, local speech
recognition (Parakeet, CPU) and speech synthesis (Piper). The LLM is your own Ollama (≥ 64k context required), the
Claude API, or both with automatic fallback.

1. `git clone https://github.com/Anarki-LNX/nuorb && cd nuorb/docker`
2. `cp .env.example .env` – set `NUORB_HOSTS` (server IP), `NUORB_LANG=en`, `TZ`
3. `docker compose up -d` (first start downloads ~530 MB of speech models)
4. `docker compose logs nuorb | grep -i "setup code"`
5. Open `https://<server-ip>:8444`, enter the code, set a password, follow the setup (language, brain), then
   “Pair device” → scan the QR code with the NuOrb app or enter the code at `https://<server-ip>:8443`.

**Upgrading from v0.3.x or older:** since v0.4.0 project, service and container are called `nuorb`. Run
`docker compose -p nuorb down` (without `-v`!), take the new `compose.yaml`, then `docker compose pull && docker compose up -d`.
The new file keeps using the volumes `nuorb_data` / `nuorb_models`, so password, data and paired devices stay.

**Smart home (optional):** off by default. Enter Home Assistant / ioBroker access under “Smart Home” in the admin panel (or put
`/opt/data/smarthome.env` in place and set `NUORB_SMARTHOME=1`). Reading needs no confirmation, switching always shows a
confirmation card. Reliable with Claude; with a local model it is limited (turn off `tools.tool_search`).

**Troubleshooting:** enter the IP of the computer running Ollama, even if it is the same PC (start Ollama with `OLLAMA_HOST=0.0.0.0`); `.local` names often don't resolve inside the container.
No network inside the container (setup says “no internet connection”, often ufw with `DEFAULT_FORWARD_POLICY="DROP"`):
`sudo ufw default allow routed && sudo ufw reload`, then `docker compose restart`. Remove `"iptables": false` /
`"bridge": "none"` from `/etc/docker/daemon.json` if present (`sudo systemctl restart docker`). Ollama on the same PC
times out: `sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp`.

Never expose the ports to the internet; use a VPN. The QR code carries the fingerprint of the server's own CA, so the
app trusts exactly this server.
