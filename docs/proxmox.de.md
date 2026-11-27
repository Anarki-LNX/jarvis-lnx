# NuOrb auf Proxmox VE (LXC)

[English](proxmox.md) · [Installationsanleitung](../INSTALL.de.md)

Wer [Proxmox VE](https://www.proxmox.com/de/proxmox-virtual-environment) betreibt, kann NuOrb in einen eigenen
Container (LXC) neben die anderen Gäste stellen. Du bekommst dasselbe NuOrb wie mit dem Docker-Installationsskript,
aber in einem CT, den du mit den gewohnten Proxmox-Werkzeugen sicherst, verschiebst und löschst.

Es gibt zwei Wege:

| | Weg A: Einzeiler | Weg B: fertiges Template |
|---|---|---|
| Wie | ein Befehl in der Shell des Proxmox-Hosts, ein Dialog fragt die Einstellungen ab | Template-Datei herunterladen (~150 MB), CT selbst anlegen (Shell oder Weboberfläche) |
| Gut für | die meisten | eigene Automatisierung, wer jeden Schritt sehen will |
| Docker im CT | installiert das Skript | schon enthalten |

Beide Wege führen zum selben Ergebnis: ein unprivilegierter Debian-12-Container mit Docker und NuOrb, Verwaltung auf
Port **8444**, App/Oberfläche auf Port **8443**. Im CT wird NuOrb mit dem normalen
[Installationsskript](../INSTALL.de.md) eingerichtet: gleiches Image, Compose-Ordner `/root/nuorb`, Docker-Container
`nuorb`.

## 1. Voraussetzungen

| | Mindestens |
|---|---|
| Proxmox VE | Version 8 oder neuer, Host mit **amd64** (x86_64). ARM-Hosts werden nicht unterstützt; das Skript bricht mit einer klaren Meldung ab. |
| Freie Ressourcen | 4 CPU-Kerne, 6 GB RAM, 24 GB Platte auf einem Speicher für Container (z. B. `local-lvm`, `local-zfs`) |
| Netz | eine Bridge (Standard `vmbr0`) mit DHCP im Heimnetz oder eine freie feste IP |
| Internet | für den CT beim ersten Start: NuOrb-Image (~1,5 GB) und Sprachmodelle (~530 MB) |
| Gehirn | ein [Ollama](https://ollama.com)-Server oder ein OpenAI-kompatibler Server (llama.cpp, vLLM, LM Studio) **oder** ein [Anthropic-API-Schlüssel](https://console.anthropic.com) (Claude), oder beides |

Alle Werte lassen sich ändern. NuOrb selbst braucht etwa 4 GB RAM; der Rest ist Reserve für die Spracherkennung und
Updates.

Der Container ist **unprivilegiert** und hat die Features `nesting=1` und `keyctl=1`. Beide sind nötig, weil NuOrb im
CT als Docker-Container läuft. Der Einzeiler setzt sie selbst; beim Template hakst du sie selbst an.

## 2. Weg A: Einzeiler (empfohlen)

Öffne die Shell deines Proxmox-**Hosts** (Weboberfläche: auf den Knoten klicken, dann *Shell*, oder per SSH als root)
und führe aus:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/proxmox/nuorb-lxc.sh)"
```

Auf dem Host ausführen, nicht in einem vorhandenen Container oder einer VM.

Das Skript:

1. prüft, ob es als root auf einem Proxmox-VE-Host ab Version 8 mit amd64 läuft;
2. fragt die Sprache und dann *Standard* oder *Erweitert*. *Standard* nimmt: nächste freie CT-ID, Hostname `nuorb`,
   4 Kerne, 6 GB RAM, 24 GB Platte, DHCP auf `vmbr0`, Ports 8443/8444. *Erweitert* lässt dich ID, Hostname, Kerne,
   RAM, Platte, Speicher, Bridge, feste IP und Gateway, VLAN, Ports und deinen Sprachmodell-Server (z. B. Ollama)
   ändern;
3. zeigt eine Zusammenfassung und fragt nach deinem Ja;
4. lädt das Debian-12-Template, falls es fehlt, legt den CT an und startet ihn (Tag `nuorb`, Start beim Booten,
   Zeitzone wie der Host), installiert Docker und NuOrb;
5. wartet, bis NuOrb bereit ist, und zeigt dann **die Adresse der Verwaltung, die Adresse der App und den
   Einrichtungscode**.

Das Ganze dauert etwa 5 bis 10 Minuten, die meiste Zeit Downloads. Alles wird auf dem Host in
`/var/log/nuorb-lxc.log` protokolliert. Geht bei der Einrichtung etwas schief, fragt das Skript, ob der unfertige CT
gelöscht werden soll (Standard: nein, damit du hineinschauen kannst).

> Bevor du ein Skript aus dem Internet als root ausführst, lies es:
> [`proxmox/nuorb-lxc.sh`](../proxmox/nuorb-lxc.sh).

### Ohne Dialog

Alle Einstellungen gibt es auch als Optionen. Hänge `_` und die Optionen an den Befehl an:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/proxmox/nuorb-lxc.sh)" _ --yes --lang de --ctid 120
```

| Option | Bedeutung |
|---|---|
| `--yes` | keine Fragen, Standardwerte für alles, was nicht angegeben ist |
| `--lang de\|en` | Sprache des Skripts und von NuOrb |
| `--ctid 120` | CT-ID (Standard: die nächste freie) |
| `--hostname nuorb` | Hostname |
| `--cores 4` · `--ram 6144` · `--disk 24` | Kerne, RAM in MB, Platte in GB |
| `--storage local-lvm` | Speicher für die Platte (Standard `local-lvm`, `local-zfs` oder der erste passende) |
| `--template-storage local` | Speicher für das Debian-Template |
| `--bridge vmbr0` · `--vlan 10` | Netzwerk-Bridge, optional VLAN-Tag |
| `--ip dhcp` oder `--ip 192.168.1.50/24 --gw <Router>` | DHCP oder feste IP mit Gateway |
| `--llm http://192.168.1.50:11434` | dein Sprachmodell-Server (Ollama oder OpenAI-kompatibel) |
| `--ports 8443,8444` | Ports für App/Oberfläche und Verwaltung |

## 3. Weg B: Template herunterladen

Das Template wird zu jeder Version automatisch gebaut. Es enthält schon Debian 12 und Docker. Das NuOrb-Image selbst
ist nicht drin (die Datei wäre sonst mehr als 20-mal so groß); der CT lädt es beim ersten Start.

Du findest es unter **https://github.com/Anarki-LNX/nuorb/releases/latest**:

- `nuorb-lxc-<version>-amd64.tar.zst` (das Template, ~150 MB)
- `nuorb-lxc-<version>-amd64.tar.zst.sha256` (seine Prüfsumme)
- `nuorb-lxc-<version>-amd64.packages.txt` (Liste der enthaltenen Debian-Pakete, für Neugierige)

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
  --net0 name=eth0,bridge=vmbr0,ip=dhcp --onboot 1 --tags nuorb
pct start 120
```

- `120` ist die CT-ID; nimm eine freie (`pvesh get /cluster/nextid` zeigt die nächste freie ID).
- `local-lvm` ist der Speicher für die Platte; nimm deinen (z. B. `local-zfs`).
- Feste IP statt DHCP: `--net0 name=eth0,bridge=vmbr0,ip=192.168.1.50/24,gw=<dein Router>`.
- Am Tag `nuorb` findet der Einzeiler diesen CT später für Updates.

### 3.3 Oder in der Weboberfläche anlegen

1. *Erstelle CT* (oben rechts).
2. **Allgemein:** CT-ID und Hostname (`nuorb`), *Unprivilegierter Container* angehakt lassen, root-Passwort setzen
   (das Template hat keins und keinen SSH-Server; ohne Passwort kommst du mit `pct enter <ID>` auf dem Host hinein).
3. **Vorlage:** Speicher `local`, Vorlage `nuorb-lxc-<version>-amd64.tar.zst`.
4. **Laufwerke:** 24 GB. **CPU:** 4 Kerne. **Speicher:** 6144 MB, Swap 512 MB.
5. **Netzwerk:** Bridge `vmbr0`, IPv4 *DHCP* (oder eine feste Adresse).
6. Abschließen **ohne** *Nach Erstellung starten*.
7. Den neuen CT auswählen → *Optionen* → *Features* → **keyctl** und **Verschachtelung** (Nesting) anhaken → OK.
8. *Optionen* → *Beim Booten starten* → Ja (empfohlen). Dann *Start*.

Ohne Schritt 7 kann Docker im CT nicht starten, und NuOrb bleibt offline.

### 3.4 Erster Start des Templates

Beim ersten Start lädt der CT das NuOrb-Image und die Sprachmodelle und richtet NuOrb ein (Dienst
`nuorb-firstboot`). Das braucht Internet und dauert ein paar Minuten. Auf dem Host mitverfolgen:

```bash
pct exec 120 -- tail -f /var/log/nuorb-firstboot.log
```

Das Template startet auf Englisch; die Sprache wählst du im Einrichtungsassistenten.

## 4. Erster Start

1. IP herausfinden: in der Weboberfläche beim CT unter *Übersicht*, oder auf dem Host: `pct exec 120 -- hostname -I`.
   Wenn du dich im CT anmeldest (`pct enter 120` oder Konsole der Weboberfläche), zeigt er seine Adressen und den
   Einrichtungscode.
2. `https://<ct-ip>:8444` öffnen (z. B. `https://192.168.1.50:8444`). Der Browser warnt vor dem Zertifikat:
   erwartet, NuOrb stellt sich sein eigenes aus. Fortfahren.
3. Den **Einrichtungscode** eingeben. Weg A zeigt ihn am Ende an. Sonst auf dem Host auslesen:
   ```bash
   pct exec 120 -- nuorb-setup-code
   ```
   (nur verfügbar, bis ein Passwort gesetzt ist).
4. Passwort wählen und der Einrichtung folgen: Name, Sprache, Stimme, **Gehirn**. Wie du Ollama, llama.cpp, vLLM,
   LM Studio oder Claude vorbereitest, steht in der [Installationsanleitung, Abschnitt 4](../INSTALL.de.md#4-gehirn).

**Gib dem CT eine feste Adresse** (DHCP-Reservierung im Router oder feste IP). NuOrb stellt sein Zertifikat für die
Adresse beim ersten Start aus, und gekoppelte Smartphones merken sie sich.

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
  Das aktualisiert Debian und Docker, lädt das neue NuOrb-Image und startet NuOrb neu.
- **Vom Host:** den Einzeiler aus Abschnitt 2 noch einmal ausführen. Er findet CTs mit dem Tag `nuorb` und bietet
  *Aktualisieren* oder *Neuen anlegen* an. Direkt, ohne Dialog:
  `bash -c "$(curl -fsSL …/proxmox/nuorb-lxc.sh)" _ update 120`.

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
  Gib dem wiederhergestellten CT dieselbe IP-Adresse wie vorher; sonst siehe *IP geändert* in Abschnitt 9.

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
| Meldung: als root in der Shell des Proxmox-VE-Hosts ausführen | Host-Shell öffnen (Knoten → *Shell*) oder als root anmelden. |
| Meldung: `pct` nicht gefunden | Du hast es in einem CT, einer VM oder auf einem anderen Rechner gestartet. In der Host-Shell ausführen. |
| Meldung: nur für amd64 (x86_64) | Dein Host ist ARM. Stattdessen das [Docker-Installationsskript](../INSTALL.de.md) in einer VM nutzen. |
| Meldung: Proxmox VE zu alt | Version 8 oder neuer nötig. Erst Proxmox aktualisieren. |
| Bei der Einrichtung ging etwas schief | Auf dem Host `/var/log/nuorb-lxc.log` ansehen. Dann den Einzeiler erneut ausführen. |
| CT startet, NuOrb bleibt offline | Features fehlen: `pct set 120 -features nesting=1,keyctl=1`, dann `pct reboot 120`. Protokoll: `pct exec 120 -- docker logs nuorb --tail 50`. |
| Template-CT: NuOrb erscheint nicht | Erster Start läuft noch oder kein Internet: `pct exec 120 -- tail -f /var/log/nuorb-firstboot.log`. |
| CT bekommt keine IP | DHCP im Netz vorhanden? Bridge richtig (`vmbr0`)? VLAN-Tag nötig? Reiter *Netzwerk* des CT prüfen. |
| Template erscheint nicht bei *Erstelle CT* | Falscher Ordner oder Speicher. Der Speicher braucht den Inhaltstyp *CT-Vorlagen* (*Rechenzentrum* → *Storage* → *Bearbeiten*). |
| `sha256sum` meldet `FAILED` | Download kaputt oder Datei verändert. Beide Dateien löschen und neu herunterladen. |
| Einrichtung: Sprachmodelle hängen, *keine Internetverbindung* | Der CT hat kein Internet: Gateway und DNS des CT (Reiter *Netzwerk*, *DNS*), Regeln der Proxmox-Firewall für den CT. |
| Einrichtungscode wird nicht angezeigt | NuOrb startet noch (1 bis 2 Minuten). `pct exec 120 -- nuorb-setup-code` erneut versuchen. Sobald ein Passwort gesetzt ist, gibt es keinen Code mehr. |
| Passwort der Verwaltung vergessen | `pct exec 120 -- nuorb-reset-password` (fragt j/N, `--yes` ohne Frage) zeigt einen neuen Einrichtungscode. Einstellungen, Gedächtnis und gekoppelte Smartphones bleiben. |
| Ollama *nicht erreichbar* | Ollama muss im Netz lauschen und die IP des CT in seiner Firewall erlauben. Die Einrichtung zeigt die genauen Befehle. Details: [INSTALL.de.md, Fehlersuche](../INSTALL.de.md#8-fehlersuche). |
| CT wird beendet oder ist sehr langsam, *out of memory* im Host-Protokoll | Zu wenig RAM. Dem CT mindestens 6 GB geben: `pct set 120 -memory 6144`. |
| *IP geändert*: App meldet Zertifikatsfehler | Am besten: dem CT die alte Adresse zurückgeben (DHCP-Reservierung). Sonst im CT die neue IP in `NUORB_HOSTS` in `/root/nuorb/.env` eintragen, dort `cd /root/nuorb && docker compose up -d` ausführen und die Smartphones neu koppeln. |
| `vzdump` im Snapshot-Modus schlägt fehl | Speicher ohne Snapshots. `--mode stop` oder `--mode suspend` nehmen. |

## 10. Sicherheit

- **Ports 8443 und 8444 nie im Router freigeben.** NuOrb ist fürs Heimnetz gemacht.
- Unterwegs per **VPN** ins Heimnetz verbinden: WireGuard (z. B. auf dem Router oder in einem weiteren CT), Tailscale
  oder Headscale. Dann funktioniert die App wie zu Hause.
- Der CT ist **unprivilegiert**: root im CT ist nicht root auf dem Host. Lass es so; NuOrb braucht keinen
  privilegierten Container.
- Das Template hat kein root-Passwort und keinen SSH-Server. Wenn du ein Passwort setzt, dann ein starkes; für die
  Wartung reicht `pct enter` vom Host.
- Optional: Zugriff mit der Proxmox-Firewall begrenzen. CT → *Firewall* → *Optionen* → einschalten, dann zwei Regeln
  *IN ACCEPT* für TCP-Port 8443 und 8444 mit Quelle `192.168.1.0/24` (dein Heimnetz).
- Auch die Proxmox-Weboberfläche (Port 8006) gehört nicht ins Internet.
- Regelmäßig aktualisieren (Abschnitt 6). In der Verwaltung eingegebene API-Schlüssel bleiben im CT und werden nur
  maskiert angezeigt.
- Eine Sicherung (Abschnitt 7) enthält Schlüssel und Gedächtnis: privat aufbewahren.

Fragen oder Probleme: [GitHub-Issues](https://github.com/Anarki-LNX/nuorb/issues).
