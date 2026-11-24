#!/usr/bin/env python3
"""NuOrb-Geraeteabsicht: MCP-Server (stdio, nur Python-Standardbibliothek).

Hermes hat KEINEN Zugang zum Handy. Dieses Werkzeug fuehrt nichts aus: Es prueft die gewuenschte
Geraeteaktion und gibt eine feste Zeile zurueck, die die Handy-Oberflaeche (nuorb-ui) im SSE-Strom
(tool.completed, tool = mcp_geraet_anfordern) erkennt und LOKAL ueber den Geraetedienst des Handys
(127.0.0.1) ausfuehrt - bei Neustart/Ausschalten/WLAN aus nach ihrer eigenen Bestaetigungskarte.

    GERAET_AKTION {"aktion": "helligkeit", "wert": 40}

Weil hier nichts passiert, traegt das Werkzeug readOnlyHint=true (keine zweite Karte in Hermes).
"""
import json
import sys

AKTIONEN = {
    "wlan_an": "WLAN einschalten", "wlan_aus": "WLAN ausschalten",
    "neustart": "Handy neu starten", "ausschalten": "Handy ausschalten",
    "bildschirm_an": "Bildschirm einschalten", "bildschirm_aus": "Bildschirm ausschalten",
    "helligkeit": "Helligkeit setzen", "lautstaerke": "Lautstärke setzen",
}
MIT_WERT = {"helligkeit", "lautstaerke"}
KARTE = {"neustart", "ausschalten", "wlan_aus"}

TOOLS = [{
    "name": "anfordern",
    "title": "Handy-Geraeteaktion anfordern",
    "description": (
        "Fordert eine Aktion am NuOrb-Handy an: WLAN an/aus, Neustart, Ausschalten, Bildschirm an/aus, "
        "Helligkeit oder Lautstaerke in Prozent (wert 0-100). Die Handy-Oberflaeche fuehrt die Aktion selbst aus, "
        "bei Neustart, Ausschalten und WLAN aus erst nach Bestaetigung durch den Nutzer. Nur fuer sofortige "
        "Aktionen auf ausdruecklichen Wunsch. Fuer 'heller'/'dunkler'/'lauter'/'leiser' den aktuellen Wert aus der "
        "[Handy: ...]-Angabe in der Nachricht nehmen und um etwa 20 Prozentpunkte aendern. "
        "Antworte danach kurz in der Ich-Form, was jetzt passiert, z. B. 'Ich stelle die Helligkeit auf 40 Prozent.' "
        "Bei Neustart, Ausschalten und WLAN aus: 'Bitte bestaetige den Neustart auf dem Bildschirm.' Rufe das Werkzeug ohne vorherigen Text auf und sprich erst nach dem Ergebnis."),
    "inputSchema": {
        "type": "object",
        "properties": {"aktion": {"type": "string", "enum": sorted(AKTIONEN)},
                       "wert": {"type": "integer", "minimum": 0, "maximum": 100}},
        "required": ["aktion"], "additionalProperties": False},
    "annotations": {"readOnlyHint": True, "openWorldHint": False},
}]


def anfordern(args: dict) -> tuple[str, bool]:
    aktion = args.get("aktion")
    if aktion not in AKTIONEN:
        return f"Unbekannte Aktion: {aktion}. Erlaubt: {', '.join(sorted(AKTIONEN))}", True
    daten = {"aktion": aktion}
    if aktion in MIT_WERT:
        wert = args.get("wert")
        if not isinstance(wert, int) or isinstance(wert, bool) or not 0 <= wert <= 100:
            return "Fuer Helligkeit und Lautstaerke braucht es wert als ganze Zahl von 0 bis 100.", True
        daten["wert"] = wert
    zeile = "GERAET_AKTION " + json.dumps(daten, ensure_ascii=False)
    hinweis = ("Die Handy-Oberflaeche fuehrt das aus" + (" , sobald der Nutzer es auf der Karte bestaetigt"
               if aktion in KARTE else "") + ". Sag nicht, dass es schon erledigt ist; sag kurz, was passiert.")
    return zeile + "\n" + hinweis.replace(" ,", ","), False


def antwort(mid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": mid}
    msg["error" if error is not None else "result"] = error if error is not None else result
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
        if mid is None:
            continue
        if methode == "initialize":
            antwort(mid, {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                          "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": "nuorb-geraet", "version": "2.0.0"}})
        elif methode == "ping":
            antwort(mid, {})
        elif methode == "tools/list":
            antwort(mid, {"tools": TOOLS})
        elif methode == "tools/call":
            if params.get("name") != "anfordern":
                antwort(mid, error={"code": -32602, "message": f"Unbekanntes Werkzeug: {params.get('name')}"})
                continue
            text, fehler = anfordern(params.get("arguments") or {})
            antwort(mid, {"content": [{"type": "text", "text": text}], "isError": fehler})
        else:
            antwort(mid, error={"code": -32601, "message": f"Methode nicht unterstuetzt: {methode}"})


if __name__ == "__main__":
    main()
