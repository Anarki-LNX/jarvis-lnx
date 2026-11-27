# NuOrb auf Proxmox VE (LXC)

[English](proxmox.md) · [Installationsanleitung](../INSTALL.de.md)

Wer [Proxmox VE](https://www.proxmox.com/de/proxmox-virtual-environment) betreibt, kann NuOrb in einen eigenen
Container (LXC) neben die anderen Gäste stellen. Du bekommst dasselbe NuOrb wie mit dem Docker-Installationsskript,
aber in einem CT, den du mit den gewohnten Proxmox-Werkzeugen sicherst, verschiebst und löschst.

Es gibt zwei Wege:

| | Weg A: Einzeiler | Weg B: fertiges Template |
|---|---|---|
| Wie | ein Befehl in der Shell des Proxmox-Hosts, ein Dialog fragt die Einstellungen ab | Template-Datei herunterladen, CT selbst anlegen (Shell oder Weboberfläche) |
| Gut für | die meisten | Umgebungen ohne Internet am Host, eigene Automatisierung, wer jeden Schritt sehen will |
| Internet am Host | ja | nur für den Download (geht auch an einem anderen Rechner) |

Beide Wege führen zum selben Ergebnis: ein unprivilegierter Debian-12-Container mit NuOrb, Verwaltung auf Port
**8444**, App/Oberfläche auf Port **8443**.

## 1. Voraussetzungen

| | Mindestens |
|---|---|
| Proxmox VE | 8.x, Host mit **amd64** (x86_64). ARM-Hosts werden nicht unterstützt; das Skript bricht mit einer klaren Meldung ab. |
| Freie Ressourcen | 4 CPU-Kerne, 6 GB RAM, 24 GB Platte auf einem Speicher für Container (z. B. `local-lvm`, ZFS) |
| Netz | eine Bridge (Standard `vmbr0`) mit DHCP im Heimnetz oder eine freie feste IP |
| Internet | einmalig für das Container-Image, NuOrb und die Sprachmodelle (~530 MB) |
| Gehirn | ein [Ollama](https://ollama.com)-Server oder ein OpenAI-kompatibler Server (llama.cpp, vLLM, LM Studio) **oder** ein [Anthropic-API-Schlüssel](https://console.anthropic.com) (Claude), oder beides |

Alle Werte lassen sich im Dialog ändern. NuOrb selbst braucht etwa 4 GB RAM; der Rest ist Reserve für die
Spracherkennung und Updates.

Der Container wird **unprivilegiert** angelegt, mit den Features `nesting=1` und `keyctl=1`. Beide sind nötig, weil
NuOrb im CT als Docker-Container läuft. Du musst sie nicht selbst setzen.

## 2. Weg A: Einzeiler (empfohlen)

Öffne die Shell deines Proxmox-**Hosts** (Weboberfläche: auf den Knoten klicken, dann *Shell*, oder per SSH als root)
und führe aus:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/proxmox/nuorb-lxc.sh)"
```

Auf dem Host ausführen, nicht in einem vorhandenen Container oder einer VM.

Das Skript:

1. prüft, ob es auf einem Proxmox-Host als root läuft und ob der Host amd64 ist;
2. öffnet einen Dialog mit den Standardwerten: Debian 12, 4 Kerne, 6 GB RAM, 24 GB Platte, DHCP auf `vmbr0`, nächste
   freie CT-ID. *Standard* übernimmt sie, *Erweitert* lässt dich ID, Hostname, Speicher, Bridge, IP, Kerne, RAM und
   Platte ändern;
3. lädt das Debian-12-Template, falls es fehlt, legt den CT an und startet ihn;
4. installiert NuOrb im CT, wartet, bis es bereit ist, und zeigt dann **die Adresse der Verwaltung und den
   Einrichtungscode**.

Das Ganze dauert etwa 5 bis 10 Minuten, die meiste Zeit Downloads.

> Bevor du ein Skript aus dem Internet als root ausführst, lies es:
> [`proxmox/nuorb-lxc.sh`](../proxmox/nuorb-lxc.sh).

## 3. Weg B: Template herunterladen

Das Template wird zu jeder Version automatisch gebaut. Du findest es unter
**https://github.com/Anarki-LNX/nuorb/releases/latest** als zwei Dateien:

- `nuorb-lxc-<version>-amd64.tar.zst` (das Template)
- `nuorb-lxc-<version>-amd64.tar.zst.sha256` (seine Prüfsumme)

### 3.1 Auf dem Host herunterladen und prüfen

In der Shell des Proxmox-Hosts (`<version>` durch die Version von der Release-Seite ersetzen, z. B. `0.7.0`):

```bash
VER=<version>
cd /var/lib/vz/template/cache
wget https://github.com/Anarki-LNX/nuorb/releases/download/v$VER/nuorb-lxc-$VER-amd64.tar.zst
wget https://github.com/Anarki-LNX/nuorb/releases/download/v$VER/nuorb-lxc-$VER-amd64.tar.zst.sha256
sha256sum -c nuorb-lxc-$VER-amd64.tar.zst.sha256
```

Der letzte Befehl muss `OK` ausgeben. Steht dort `FAILED`, beide Dateien löschen und neu herunterladen. Ein Template
mit falscher Prüfsumme nie verwenden.

`/var/lib/vz/template/cache` ist der Template-Ordner des Speichers `local`. Liegen deine Templates auf einem anderen
Speicher, nimm dessen Ordner `template/cache`.

An einem anderen Rechner heruntergeladen? Dort prüfen (`sha256sum -c …`, unter Windows
`Get-FileHash nuorb-lxc-<version>-amd64.tar.zst`) und in der Weboberfläche hochladen: Speicher `local` →
*CT-Vorlagen* → *Hochladen*.

### 3.2 Container in der Shell anlegen

```bash
pct create 120 local:vztmpl/nuorb-lxc-$VER-amd64.tar.zst \
  --hostname nuorb --ostype debian --unprivileged 1 --features nesting=1,keyctl=1 \
  --cores 4 --memory 6144 --swap 512 --rootfs local-lvm:24 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp --onboot 1
pct start 120
```

- `120` ist die CT-ID; nimm eine freie (`pvesh get /cluster/nextid` zeigt die nächste freie ID).
- `local-lvm` ist der Speicher für die Platte; nimm deinen (z. B. `local-zfs`).
- Feste IP statt DHCP: `--net0 name=eth0,bridge=vmbr0,ip=192.168.1.50/24,gw=<dein Router>`.

### 3.3 Oder in der Weboberfläche anlegen

1. *Erstelle CT* (oben rechts).
2. **Allgemein:** CT-ID und Hostname (`nuorb`), *Unprivilegierter Container* angehakt lassen, root-Passwort oder
   SSH-Schlüssel setzen.
3. **Vorlage:** Speicher `local`, Vorlage `nuorb-lxc-<version>-amd64.tar.zst`.
4. **Laufwerke:** 24 GB. **CPU:** 4 Kerne. **Speicher:** 6144 MB, Swap 512 MB.
5. **Netzwerk:** Bridge `vmbr0`, IPv4 *DHCP* (oder eine feste Adresse).
6. Abschließen **ohne** *Nach Erstellung starten*.
7. Den neuen CT auswählen → *Optionen* → *Features* → **keyctl** und **Verschachtelung** (Nesting) anhaken → OK.
8. *Optionen* → *Beim Booten starten* → Ja (empfohlen). Dann *Start*.

Ohne Schritt 7 kann Docker im CT nicht starten, und NuOrb bleibt offline.

## 4. Erster Start

Beim ersten Start erzeugt der Container seine eigenen Zertifikate für seine IP-Adresse und lädt die Sprachmodelle.
Gib ihm 1 bis 2 Minuten.

1. IP herausfinden: in der Weboberfläche beim CT unter *Übersicht*, oder auf dem Host: `pct exec 120 -- hostname -I`.
2. `https://<ct-ip>:8444` öffnen (z. B. `https://192.168.1.50:8444`). Der Browser warnt vor dem Zertifikat:
   erwartet, NuOrb stellt sich sein eigenes aus. Fortfahren.
3. Den **Einrichtungscode** eingeben. Weg A zeigt ihn am Ende an. Sonst auf dem Host auslesen:
   ```bash
   pct exec 120 -- nuorb-setup-code
   ```
   (nur verfügbar, bis ein Passwort gesetzt ist).
4. Passwort wählen und der Einrichtung folgen: Name, Sprache, Stimme, **Gehirn**. Wie du Ollama, llama.cpp, vLLM,
   LM Studio oder Claude vorbereitest, steht in der [Installationsanleitung, Abschnitt 4](../INSTALL.de.md#4-gehirn).

Tipp: Gib dem CT eine feste Adresse (DHCP-Reservierung im Router oder feste IP). Das Zertifikat und die gekoppelten
Smartphones nutzen diese Adresse; ändert sie sich, müssen die Smartphones neu gekoppelt werden.

## 5. Kopplung

1. Die **NuOrb**-App auf dem Smartphone installieren oder einen beliebigen Browser im Heimnetz nehmen.
2. Verwaltung → *Gerät koppeln* → *Neuen Kopplungscode erzeugen*.
3. Den QR-Code mit der App scannen. Der Code gilt 10 Minuten und nur einmal.
4. Ein Browser wird genauso gekoppelt: `https://<ct-ip>:8443` öffnen und den Code eingeben.

Gekoppelte Geräte stehen in der Verwaltung und lassen sich dort entkoppeln.

## 6. Update

Beide Wege behalten Einstellungen, Passwort, gekoppelte Geräte und Gedächtnis:

- **Im CT:** Konsole des CT öffnen (Weboberfläche → CT → *Konsole*) oder auf dem Host ausführen:
  ```bash
  pct exec 120 -- update
  ```
  Das lädt das neue NuOrb-Image und startet NuOrb neu.
- **Vom Host:** den Einzeiler aus Abschnitt 2 noch einmal ausführen und den vorhandenen CT wählen. Er aktualisiert,
  statt einen neuen anzulegen.

Debian-Updates im CT: `pct exec 120 -- bash -c "apt update && apt -y full-upgrade"`.

Ein neues Template auf der Release-Seite brauchst du nur für neue Installationen. Vorhandene CTs aktualisierst du mit
`update`.

## 7. Sicherung und Wiederherstellung

NuOrb hält alles (Einstellungen, Passwort, gekoppelte Geräte, Gedächtnis, Modelle) im CT. Eine normale
Proxmox-Sicherung deckt es ab.

```bash
vzdump 120 --mode snapshot --compress zstd --storage local
```

- In der Weboberfläche: CT → *Backup* → *Jetzt sichern*, oder ein geplanter Auftrag unter *Rechenzentrum* → *Backup*.
- `--mode snapshot` braucht einen Speicher mit Snapshots (LVM-thin, ZFS, Ceph). Schlägt es fehl, nimm
  `--mode stop` (NuOrb ist dann etwa eine Minute offline).
- Wiederherstellen: Weboberfläche → Sicherungsspeicher → *Backups* → *Wiederherstellen*, oder
  ```bash
  pct restore 121 /var/lib/vz/dump/vzdump-lxc-120-<datum>.tar.zst --storage local-lvm
  ```
  Bei einer neuen ID mit neuer IP müssen die Smartphones neu gekoppelt werden (siehe Abschnitt 4, Tipp).

Eine Sicherung enthält deine API-Schlüssel und das Gedächtnis der Gespräche. Bewahre sie auf wie eine Passwortdatei.

## 8. Deinstallation

```bash
pct stop 120
pct destroy 120 --purge 1
```

Das löscht den CT mit allen NuOrb-Daten, auch Passwort der Verwaltung und gekoppelte Geräte. Vorher sichern, falls du
sie vielleicht zurückhaben willst. `--purge 1` entfernt den CT auch aus Sicherungsaufträgen und HA. In der
Weboberfläche: CT → *Mehr* → *Entfernen*.

Das heruntergeladene Template bleibt in `/var/lib/vz/template/cache`; lösche es dort oder in der Weboberfläche, wenn
du es nicht mehr brauchst.

## 9. Fehlersuche

| Problem | Ursache und Lösung |
|---|---|
| Skript: *Host ist nicht amd64* | Das NuOrb-LXC gibt es nur für amd64. Auf ARM das [Docker-Installationsskript](../INSTALL.de.md) in einer VM nutzen. |
| Skript: *muss auf einem Proxmox-VE-Host laufen* | Du hast es in einem CT oder einer VM gestartet. In der Host-Shell ausführen (Knoten → *Shell*). |
| CT startet, NuOrb bleibt offline | Features fehlen: `pct set 120 -features nesting=1,keyctl=1`, dann `pct reboot 120`. Protokoll: `pct exec 120 -- docker logs nuorb --tail 50`. |
| CT bekommt keine IP | DHCP im Netz vorhanden? Bridge richtig (`vmbr0`)? VLAN-Tag nötig? Reiter *Netzwerk* des CT prüfen. |
| Template erscheint nicht bei *Erstelle CT* | Falscher Ordner oder Speicher. Der Speicher braucht den Inhaltstyp *CT-Vorlagen* (*Rechenzentrum* → *Storage* → *Bearbeiten*). |
| `sha256sum` meldet `FAILED` | Download kaputt oder Datei verändert. Beide Dateien löschen und neu herunterladen. |
| Einrichtung: Sprachmodelle hängen, *keine Internetverbindung* | Der CT hat kein Internet: Gateway und DNS des CT (Reiter *Netzwerk*, *DNS*), Regeln der Proxmox-Firewall für den CT. |
| Einrichtungscode wird nicht angezeigt | NuOrb startet noch (1 bis 2 Minuten). `pct exec 120 -- nuorb-setup-code` erneut versuchen. Sobald ein Passwort gesetzt ist, gibt es keinen Code mehr. |
| Passwort der Verwaltung vergessen | `pct exec 120 -- nuorb-reset-password` gibt einen neuen Einrichtungscode aus. |
| Ollama *nicht erreichbar* | Ollama muss im Netz lauschen und die IP des CT in seiner Firewall erlauben. Die Einrichtung zeigt die genauen Befehle. Details: [INSTALL.de.md, Fehlersuche](../INSTALL.de.md#8-fehlersuche). |
| CT wird beendet oder ist sehr langsam, *out of memory* im Host-Protokoll | Zu wenig RAM. Dem CT mindestens 6 GB geben: `pct set 120 -memory 6144`. |
| Falsche Uhrzeit in Antworten | Zeitzone im CT setzen: `pct exec 120 -- timedatectl set-timezone Europe/Berlin`. |
| `vzdump` im Snapshot-Modus schlägt fehl | Speicher ohne Snapshots. `--mode stop` oder `--mode suspend` nehmen. |
| App: Zertifikatsfehler nach IP-Wechsel | Der CT hat eine neue Adresse. CT neu starten, damit NuOrb Zertifikate für die neue IP erzeugt, dann neu koppeln. Besser: feste IP. |

## 10. Sicherheit

- **Ports 8443 und 8444 nie im Router freigeben.** NuOrb ist fürs Heimnetz gemacht.
- Unterwegs per **VPN** ins Heimnetz verbinden: WireGuard (z. B. auf dem Router oder in einem weiteren CT), Tailscale
  oder Headscale. Dann funktioniert die App wie zu Hause.
- Der CT ist **unprivilegiert**: root im CT ist nicht root auf dem Host. Lass es so; NuOrb braucht keinen
  privilegierten Container.
- Optional: Zugriff mit der Proxmox-Firewall begrenzen. CT → *Firewall* → *Optionen* → einschalten, dann zwei Regeln
  *IN ACCEPT* für TCP-Port 8443 und 8444 mit Quelle `192.168.1.0/24` (dein Heimnetz).
- Auch die Proxmox-Weboberfläche (Port 8006) gehört nicht ins Internet.
- Regelmäßig aktualisieren (Abschnitt 6). In der Verwaltung eingegebene API-Schlüssel bleiben im CT und werden nur
  maskiert angezeigt.
- Eine Sicherung (Abschnitt 7) enthält Schlüssel und Gedächtnis: privat aufbewahren.

Fragen oder Probleme: [GitHub-Issues](https://github.com/Anarki-LNX/nuorb/issues).
