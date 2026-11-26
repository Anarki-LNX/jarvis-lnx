# NuOrb installieren

[English](INSTALL.md)

NuOrb ist ein privater Sprachassistent zum Selbstbetreiben: **ein Docker-Container** auf einem Heimserver, einer
Proxmox-VM/LXC oder deinem PC. Dein Smartphone (NuOrb-App) oder jeder Browser im Heimnetz spricht mit ihm.

## 1. Voraussetzungen

| | Mindestens |
|---|---|
| Rechner | Linux, amd64 oder arm64, 4 CPU-Kerne, 4 GB freier RAM, 8 GB Platte |
| Software | Docker mit Compose v2 (fehlt es, nennt das Installationsskript den passenden Befehl) |
| Internet | einmalig für das Image (~1,2 GB) und die Sprachmodelle (~530 MB) |
| Gehirn | ein [Ollama](https://ollama.com)-Server oder ein OpenAI-kompatibler Server (llama.cpp, vLLM, LM Studio) **oder** ein [Anthropic-API-Schlüssel](https://console.anthropic.com) (Claude) – oder beides |
| Netz | Smartphone und Server im selben Heimnetz oder per VPN verbunden (WireGuard, Tailscale) |

Proxmox-LXC: vorher Nesting und keyctl einschalten – auf dem Proxmox-Host: `pct set <ID> -features nesting=1,keyctl=1`.

## 2. Installation mit einem Befehl

```bash
curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/install.sh | bash -s -- --lang de
```

Funktioniert aus jeder Shell (auch fish/zsh – das Skript läuft in bash).

Das Skript:

1. prüft curl, Docker, Docker Compose, deine Docker-Rechte und die Netz-Einstellungen von Docker und nennt die genaue
   Lösung für deine Distribution (Debian/Ubuntu, Fedora, Arch/CachyOS, openSUSE, Alpine);
2. fragt nur, was es nicht selbst erkennt – Sprache, die IP-Adresse dieses Servers (erkannt, Enter bestätigt),
   Ollama (wird erkannt, wenn es auf diesem Rechner läuft);
3. prüft die Firewall (ufw/firewalld) und zeigt die nötigen Regeln fürs Heimnetz – ausgeführt werden sie **nur nach
   deinem Ja**, nie wird etwas ins Internet geöffnet;
4. lädt und startet NuOrb, wartet, bis es bereit ist, und zeigt dann **die Adresse der Verwaltung und den
   Einrichtungscode**.

Optionen: `--dir ORDNER` (Standard `~/nuorb`), `--ports 8443,8444`, `--lang de|en`, `--ip 192.168.1.50`,
`--ollama http://192.168.1.50:11434|none`, `--yes` (keine Fragen; führt nie sudo aus), `--no-firewall`, `--uninstall`.
Beispiel: `curl -fsSL …/install.sh | bash -s -- --lang de --ports 9443,9444`.

Derselbe Befehl noch einmal **aktualisiert oder repariert** die Installation. Einstellungen und Daten bleiben.

## 3. Erste Schritte

1. `https://<server-ip>:8444` öffnen (z. B. `https://192.168.1.50:8444`). Der Browser warnt vor dem Zertifikat –
   erwartet, NuOrb stellt sich sein eigenes aus. Fortfahren.
2. Den **Einrichtungscode** aus dem Installationsskript eingeben, ein Passwort wählen.
3. Der Einrichtung folgen: Name, Sprache, Stimme, **Gehirn** (Ollama und/oder Claude).
4. **Smartphone koppeln:** Verwaltung → *Gerät koppeln* → QR-Code mit der NuOrb-App scannen. Der Code gilt 10 Minuten
   und nur einmal. Einen Browser koppelst du genauso (`https://<server-ip>:8443`).

Einrichtungscode vergessen? `docker compose -f ~/nuorb/compose.yaml logs nuorb | grep -i "setup code"`
(nur sichtbar, bis ein Passwort gesetzt ist).

## 4. Gehirn

### Ollama (lokal, kostenlos, nichts verlässt das Haus)

Auf dem Rechner, auf dem Ollama läuft:

- im Netz lauschen lassen: `sudo systemctl edit ollama` → eintragen
  ```
  [Service]
  Environment="OLLAMA_HOST=0.0.0.0"
  Environment="OLLAMA_CONTEXT_LENGTH=65536"
  ```
  dann `sudo systemctl restart ollama`. **NuOrb braucht mindestens 64k Kontext.**
- Firewall auf diesem Rechner: Port 11434 nur fürs Heimnetz freigeben, z. B. `sudo ufw allow from 192.168.1.0/24 to any port 11434 proto tcp`.
  Läuft Ollama **auf demselben Rechner** wie NuOrb, zusätzlich Docker erlauben: `sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp`.
- in der Einrichtung die **IP-Adresse** dieses Rechners eintragen, z. B. `http://192.168.1.50:11434` – auch wenn es
  derselbe Rechner ist. Namen wie `pc.local` lösen im Container oft nicht auf.
- gut geeignet: Modelle mit Werkzeugnutzung, z. B. Gemma, Qwen, Llama 3.x (ab 8B).

### llama.cpp, vLLM, LM Studio statt Ollama

NuOrb arbeitet mit **jedem Server, der die OpenAI-Chat-API spricht**. In der Einrichtung **„OpenAI-kompatibel“**
wählen, die Adresse (mit Port, ohne `/v1`) und – falls der Server einen verlangt – den API-Key eintragen.
Das Installationsskript erkennt solche Server auf demselben Rechner (Ports 8080, 8000, 1234) selbst.

Für jeden Server gilt: **Tool-Calling** muss funktionieren, **Kontext ≥ 64k (65536)**, er muss **im Netz lauschen**
(nicht nur auf 127.0.0.1), und sein Port muss in der Firewall dieses Rechners offen sein (von Docker: `172.16.0.0/12`).

**llama.cpp** (`llama-server`, Port 8080):
```bash
llama-server -m Qwen3-8B-Q4_K_M.gguf --alias qwen3-8b --host 0.0.0.0 --port 8080 -c 65536 -ngl 99 --jinja \
  -ctk q8_0 -ctv q8_0 --api-key DEIN_KEY        # --api-key ist optional
```
- `--alias` gibt dem Modell einen kurzen Namen (sonst heißt es wie der Dateipfad).
- Modell mit nativ 32k (z. B. Qwen3 ≤ 32B): zusätzlich `--rope-scaling yarn --rope-scale 2 --yarn-orig-ctx 32768`.
- Kontext passt nicht in den VRAM: `-ctk q8_0 -ctv q8_0` beibehalten (halber KV-Cache) oder kleineres Modell.
- Getestet: Qwen3-4B Q4_K_M mit 64k Kontext – Wissensfragen, Uhrzeit und Notizen per Werkzeug funktionieren.

**vLLM** (Port 8000):
```bash
vllm serve Qwen/Qwen3-8B --host 0.0.0.0 --port 8000 --max-model-len 65536 \
  --enable-auto-tool-choice --tool-call-parser hermes
```
- Tool-Parser je Modellfamilie: Qwen2.5/3 → `hermes`, Llama 3.1+ → `llama3_json`, Mistral → `mistral`, gpt-oss → `openai`.
- Ohne `--enable-auto-tool-choice` lehnt vLLM Anfragen mit Werkzeugen ab (HTTP 400), NuOrb antwortet dann nicht.

**LM Studio** (Port 1234): Entwickler-Tab → Server starten, *Im lokalen Netzwerk bereitstellen* einschalten. Beim
Laden des Modells **Context Length ≥ 65536** einstellen (Standard ist oft 4096). Ohne Oberfläche:
`lms server start --port 1234` und `lms load <modell> --context-length 65536`.

**LocalAI** (Port 8080): in der Modell-YAML `context_size: 65536` setzen und die Function-Vorlage aktivieren.

Nicht jeder Server ist gleich gut getestet: llama.cpp und Ollama liefen mit NuOrb; vLLM, LM Studio und LocalAI folgen
deren Dokumentation. Bestehende Ollama-Installationen laufen unverändert weiter.

### Claude (kein eigener Grafikchip nötig, kostet pro Frage)

Schlüssel unter [console.anthropic.com](https://console.anthropic.com) anlegen und in der Einrichtung eintragen. Dort
ein Ausgabenlimit setzen. Eine kurze Sprachfrage kostet mit Haiku etwa 0,1–0,5 Cent. Gesprächstexte gehen an
Anthropic (USA), Audio bleibt immer lokal. *Beides (Automatik)* nutzt Ollama und weicht auf Claude aus, wenn der PC aus ist.

## 5. Firewall und Ports

| Port | Was | Wer braucht ihn |
|---|---|---|
| 8443 | App/Oberfläche | Smartphones und Browser im Heimnetz |
| 8444 | Verwaltung | dein Browser im Heimnetz |

Diese Ports nie am Router freigeben. Für unterwegs: VPN ins Heimnetz.

**ufw** (Ubuntu, CachyOS, Arch …):
```bash
sudo ufw default allow routed                                             # Container dürfen ins Internet
sudo ufw allow from 192.168.1.0/24 to any port 8443,8444 proto tcp        # nur dein Heimnetz
sudo ufw reload
```
**firewalld** (Fedora, openSUSE):
```bash
sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=192.168.1.0/24 port port=8443 protocol=tcp accept'
sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=192.168.1.0/24 port port=8444 protocol=tcp accept'
sudo firewall-cmd --reload
```
`192.168.1.0/24` durch dein Heimnetz ersetzen.

## 6. Manuelle Installation (Alternative)

```bash
mkdir -p ~/nuorb && cd ~/nuorb
curl -fsSLO https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/docker/compose.yaml
curl -fsSL  https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/docker/.env.example -o .env
nano .env                       # mindestens NUORB_HOSTS=192.168.1.50 (IP dieses Servers), NUORB_LANG, TZ
docker compose up -d
docker compose logs -f nuorb    # auf „setup code“ warten, Strg+C
```
Die Einstellungen heißen aus historischen Gründen `NUORB_…`; sie sind in der `.env` erklärt.

## 7. Update, Sicherung, Deinstallation

- **Update:** den Installationsbefehl noch einmal ausführen – oder `cd ~/nuorb && docker compose pull && docker compose up -d`.
- **Sicherung:** `docker run --rm -v nuorb_data:/d -v "$PWD":/b debian tar czf /b/nuorb-data.tgz -C /d .`
- **Deinstallation:** `curl -fsSL …/install.sh | bash -s -- --uninstall` – fragt vorher; Daten werden nur gelöscht,
  wenn du `LÖSCHEN` eintippst.
- **Von v0.3.x oder älter** (Container `nuorb-nuorb-1`): einfach den Installationsbefehl ausführen – er findet
  die alte Installation, übernimmt ihre Einstellungen und behält die Daten. Von Hand: `docker compose -p nuorb down`
  (**ohne** `-v`), dann die neue `compose.yaml` und `docker compose up -d`.

## 8. Fehlersuche

| Problem | Ursache und Lösung |
|---|---|
| `curl … \| bash` in fish zeigt einen Fehler | Genau den Befehl oben nehmen; fish gibt das Skript an bash weiter. Andere Befehle aus dieser Anleitung: vorher `bash` starten. |
| `permission denied … docker.sock` | `sudo usermod -aG docker $USER`, ab- und wieder anmelden (oder mit sudo). |
| Einrichtungscode noch nicht im Log | NuOrb startet noch (erster Start ~1–2 min). Warten, oder: `docker compose exec nuorb cat /opt/data/nuorb/admin/setup-code.txt`. |
| Einrichtung: *„Der Container hat keine Internetverbindung“*, Sprachmodelle laden nicht | Die Firewall verwirft Container-Verkehr: ufw `sudo ufw default allow routed && sudo ufw reload`; firewalld `sudo firewall-cmd --permanent --zone=trusted --add-interface=docker0 && sudo firewall-cmd --reload`. |
| Container haben gar kein Netz | `/etc/docker/daemon.json` enthält `"iptables": false` oder `"bridge": "none"` – beides entfernen, `sudo systemctl restart docker`. |
| `unable to derive the IP value for host-gateway` | Dein Docker hat keine Standard-Bridge; nicht `host.docker.internal` nutzen, sondern die IP des Rechners. |
| Ollama *nicht erreichbar* / ConnectTimeout | Ollama lauscht nur auf 127.0.0.1 → `OLLAMA_HOST=0.0.0.0`; Firewall am Ollama-Rechner → 11434 freigeben (von Docker `172.16.0.0/12`, wenn es derselbe Rechner ist); IP statt `.local` nehmen. Die Einrichtung zeigt die passenden Firewall-Befehle für diesen Rechner an. |
| *context window … below 64,000* | Kontext zu klein → Ollama `OLLAMA_CONTEXT_LENGTH=65536`, llama.cpp `-c 65536`, vLLM `--max-model-len 65536`, LM Studio Context Length 65536; Server neu starten. |
| llama.cpp/vLLM/LM Studio *nicht erreichbar* (Timeout) | Der Server lauscht nur auf 127.0.0.1 → `--host 0.0.0.0` / *Im lokalen Netzwerk bereitstellen*; seinen Port in der Firewall des PCs freigeben (`sudo ufw allow from 172.16.0.0/12 to any port 8080 proto tcp`). |
| *Der Server verlangt einen API-Key* | Der Server läuft mit `--api-key` → denselben Key in der Einrichtung eintragen. |
| vLLM: NuOrb antwortet nicht, im Server-Log HTTP 400 | vLLM mit `--enable-auto-tool-choice --tool-call-parser …` starten. |
| Browser: *Verbindung nicht privat* | Erwartet beim eigenen Zertifikat – fortfahren, oder `https://<server-ip>:8443/nuorb-ca.crt` importieren. |
| App: Zertifikatsfehler nach IP-Wechsel | Die IP fehlt in `NUORB_HOSTS` in `~/nuorb/.env` → eintragen, `docker compose up -d`, neu koppeln. |
| Smartphone verbindet sich nicht | Gleiches Netz/VPN? Firewall-Regel für 8443 (siehe 5)? Adresse in der App = `https://<server-ip>:8443`. |
| *Port 8443 wird schon benutzt* | Mit anderen Ports installieren: `… \| bash -s -- --ports 9443,9444`. |
| Alte Version läuft noch (Portkonflikt nach Update) | `docker compose -p nuorb down` (ohne `-v`), dann das Installationsskript erneut starten. |
| Proxmox-LXC: Docker startet nicht | Auf dem Host: `pct set <ID> -features nesting=1,keyctl=1`, LXC neu starten. |
| Smart Home schaltet nicht | Siehe [docker/README.md](docker/README.md#smart-home-optional): mit Claude zuverlässig; mit lokalem Modell die Werkzeugsuche ausschalten. |

Mehr Details: [docker/README.md](docker/README.md).
