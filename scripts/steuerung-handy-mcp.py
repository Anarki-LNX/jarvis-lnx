#!/usr/bin/env python3
"""JARVIS-Steuerung: MCP-Server (stdio) fuer das Handy. Nur Python-Standardbibliothek.

Laeuft auf jarvis als Benutzer jarvis, gestartet von Hermes (mcp_servers.handy, trust: untrusted).
Spricht das Handy per SSH mit dem eingeschraenkten Schluessel an; das Handy fuehrt nur das
Wrapper-Skript jarvis-steuerung aus (status | generationen | neustart | rollback).

Lesende Werkzeuge tragen readOnlyHint=true (laufen ohne Rueckfrage), alle anderen nicht:
Hermes verlangt fuer sie bei trust: untrusted vor JEDEM Aufruf eine Bestaetigung.
"""
import json
import os
import subprocess
import sys

HOST = os.environ.get("HANDY_HOST", "")
KEY = os.environ.get("HANDY_KEY", os.path.expanduser("~/.ssh/id_ed25519_handy_steuerung"))
KNOWN = os.path.expanduser("~/.ssh/known_hosts_handy")

TOOLS = [
    {
        "name": "status",
        "title": "Handy-Status",
        "description": ("Liest den Zustand des JARVIS-Handys (Xiaomi): Akku, Temperatur, WLAN, Laufzeit seit Start, "
                        "NixOS-Generation. Nur lesend. Nutzen bei Fragen wie 'Wie geht es dem Handy?', "
                        "'Akkustand?', 'Wie warm ist das Telefon?'."),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "generationen",
        "title": "Handy-Systemstaende",
        "description": "Listet die letzten installierten NixOS-Systemstaende (Generationen) des Handys. Nur lesend.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "neustart",
        "title": "Handy neu starten",
        "description": ("Startet das JARVIS-Handy neu (systemctl reboot nach 3 Sekunden). Die Verbindung und die "
                        "Oberflaeche sind danach ca. 2 Minuten weg. Nur aufrufen, wenn der Nutzer ausdruecklich "
                        "einen Neustart des Handys verlangt. Der Nutzer muss den Aufruf bestaetigen."),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False,
                        "openWorldHint": False},
    },
    {
        "name": "rollback",
        "title": "Handy-System zuruecksetzen",
        "description": ("Setzt das Handy auf den vorherigen NixOS-Systemstand (Generation) zurueck und aktiviert ihn "
                        "sofort; die Oberflaeche startet dabei neu. Nur auf ausdrueckliche Bitte des Nutzers, z. B. "
                        "wenn nach einem Update etwas nicht geht. Der Nutzer muss den Aufruf bestaetigen."),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False,
                        "openWorldHint": False},
    },
]
NAMES = {t["name"] for t in TOOLS}


def handy(auftrag: str, timeout: int = 20) -> tuple[int, dict, str]:
    if not HOST:
        return 99, {}, "HANDY_HOST ist nicht gesetzt."
    cmd = ["ssh", "-i", KEY, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=8",
           "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN}", "-o", "LogLevel=ERROR",
           f"root@{HOST}", auftrag]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 98, {}, "Das Handy antwortet nicht (Zeitueberschreitung)."
    werte = {}
    for zeile in p.stdout.splitlines():
        if "=" in zeile:
            k, v = zeile.split("=", 1)
            werte[k.strip()] = v.strip()
    return p.returncode, werte, (p.stdout + p.stderr).strip()


def dauer(sek: str) -> str:
    try:
        s = int(sek)
    except ValueError:
        return "unbekannt"
    h, m = divmod(s // 60, 60)
    t, h = divmod(h, 24)
    teile = ([f"{t} Tag{'e' if t != 1 else ''}"] if t else []) + ([f"{h} Stunde{'n' if h != 1 else ''}"] if h else [])
    teile.append(f"{m} Minute{'n' if m != 1 else ''}")
    return " ".join(teile)


ZUSTAND = {"Charging": "lädt", "Discharging": "entlädt", "Full": "voll", "Not charging": "lädt nicht (Ladelimit)"}


def call(name: str) -> tuple[str, bool]:
    if name == "status":
        rc, w, roh = handy("status")
        if rc != 0:
            return f"Handy nicht erreichbar oder Fehler: {roh}", True
        text = (f"Akku {w.get('akku_prozent', '?')} Prozent, {ZUSTAND.get(w.get('akku_zustand', ''), w.get('akku_zustand', '?'))}. "
                f"Akku-Temperatur {w.get('akku_temp_c', '?')} Grad, heißeste Stelle {w.get('temp_max_c', '?')} Grad. "
                f"WLAN {w.get('wlan_ssid') or 'nicht verbunden'}, Signal {w.get('wlan_signal', '?')} Prozent, IP {w.get('wlan_ip', '?')}. "
                f"Läuft seit {dauer(w.get('uptime_s', ''))}. Systemstand Generation {w.get('generation', '?')}. "
                f"Kiosk {'läuft' if w.get('kiosk_aktiv') == 'ja' else 'läuft nicht'}.")
        return text + "\n\nRohdaten: " + json.dumps(w, ensure_ascii=False), False
    if name == "generationen":
        rc, _, roh = handy("generationen")
        return (roh or "keine Ausgabe"), rc != 0
    if name == "neustart":
        rc, w, roh = handy("neustart")
        if rc != 0:
            return f"Neustart fehlgeschlagen: {roh}", True
        return "Das Handy startet in 3 Sekunden neu und ist in etwa 2 Minuten wieder da.", False
    if name == "rollback":
        rc, w, roh = handy("rollback", timeout=60)
        if rc != 0:
            return f"Zurücksetzen fehlgeschlagen: {roh}", True
        return f"Handy wird auf den vorherigen Systemstand zurückgesetzt ({w.get('von', '?')} → {w.get('auf', '?')}).", False
    return f"Unbekanntes Werkzeug {name}", True


def antwort(mid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": mid}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for zeile in sys.stdin:
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            req = json.loads(zeile)
        except json.JSONDecodeError:
            continue
        mid, methode, params = req.get("id"), req.get("method", ""), req.get("params") or {}
        if mid is None:  # Benachrichtigung
            continue
        if methode == "initialize":
            antwort(mid, {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "jarvis-handy-steuerung", "version": "1.0.0"},
                "instructions": "Werkzeuge fuer das JARVIS-Handy. Neustart und Rollback nur auf ausdrueckliche Bitte.",
            })
        elif methode == "ping":
            antwort(mid, {})
        elif methode == "tools/list":
            antwort(mid, {"tools": TOOLS})
        elif methode == "tools/call":
            name = params.get("name", "")
            if name not in NAMES:
                antwort(mid, error={"code": -32602, "message": f"Unbekanntes Werkzeug: {name}"})
                continue
            text, fehler = call(name)
            antwort(mid, {"content": [{"type": "text", "text": text}], "isError": fehler})
        else:
            antwort(mid, error={"code": -32601, "message": f"Methode nicht unterstuetzt: {methode}"})


if __name__ == "__main__":
    main()
