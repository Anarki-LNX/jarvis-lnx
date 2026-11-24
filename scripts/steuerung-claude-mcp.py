#!/usr/bin/env python3
"""NuOrb Projekt-Claude: MCP-Server (stdio, nur Python-Standardbibliothek).

Laeuft auf nuorb als Benutzer nuorb, gestartet von Hermes (mcp_servers.claude, trust: untrusted).
Gibt Fragen und Auftraege an die Claude-Code-CLI weiter, eng begrenzt:
  - fester Arbeitsordner (CLAUDE_PROJEKT, ein Git-Repo), Claude laeuft mit --restricted
    (keine Shell, kein Code-Ausfuehren, kein WebFetch, keine Nutzer-/Projekt-Einstellungen)
  - fragen:  nur Read/Grep/Glob             (kostet Geld -> trotzdem Bestaetigung)
  - auftrag: zusaetzlich Edit/Write, danach automatischer Git-Commit
  - rueckgaengig: letzten Claude-Commit per git revert zuruecknehmen
  - aenderungen: letzte Commits anzeigen (nur lesend, ohne Rueckfrage)
  - harte Kostengrenze pro Aufruf (--max-budget-usd)
Der API-Schluessel wird aus ~/.hermes/.env gelesen und nur an den Claude-Prozess gegeben.
"""
import json
import os
import subprocess
import sys

PROJEKT = os.environ.get("CLAUDE_PROJEKT", os.path.expanduser("~/projekte/nuorb-ui"))
MODELL = os.environ.get("CLAUDE_MODELL", "claude-sonnet-5-5")
CLAUDE = os.path.expanduser("~/.local/bin/claude")
ENV_DATEI = os.path.expanduser("~/.hermes/.env")
BUDGET = {"fragen": os.environ.get("CLAUDE_BUDGET_FRAGEN", "0.30"),
          "auftrag": os.environ.get("CLAUDE_BUDGET_AUFTRAG", "1.00")}
ZEIT = {"fragen": 240, "auftrag": 600}
WERKZEUGE = {"fragen": ["Read", "Grep", "Glob"], "auftrag": ["Read", "Grep", "Glob", "Edit", "Write"]}
STIL = ("Du wirst per Sprache ueber den Assistenten NuOrb angesprochen. Antworte auf Deutsch, knapp "
        "(hoechstens 5 Saetze), gut vorlesbar, ohne Tabellen und ohne lange Codebloecke. "
        "Du arbeitest nur im aktuellen Projektordner. Wenn der Auftrag unklar ist, aendere nichts und sage, was fehlt.")

PROJEKTNAME = os.path.basename(PROJEKT.rstrip("/"))
TEXT = {"type": "string", "minLength": 3, "maxLength": 2000}
TOOLS = [
    {
        "name": "fragen",
        "title": "Projekt-Claude fragen",
        "description": (f"Stellt dem Projekt-Claude (Claude {MODELL}) eine Frage zum Projekt '{PROJEKTNAME}'. "
                        "Claude darf nur Dateien lesen und durchsuchen, nichts aendern. Nutzen, wenn der Nutzer "
                        "'Frag Claude ...' sagt oder eine Frage zum Code der NuOrb-Oberflaeche stellt. Kostet Geld "
                        "(typisch 1-20 Cent), der Nutzer muss bestaetigen. Gib die Frage moeglichst woertlich weiter. Rufe das Werkzeug ohne vorherigen Text auf und sprich erst nach dem Ergebnis."),
        "inputSchema": {"type": "object", "properties": {"frage": TEXT}, "required": ["frage"],
                        "additionalProperties": False},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
    },
    {
        "name": "auftrag",
        "title": "Projekt-Claude Auftrag",
        "description": (f"Gibt dem Projekt-Claude einen Aenderungsauftrag fuer das Projekt '{PROJEKTNAME}' "
                        "(Arbeitskopie, nicht die laufende Oberflaeche). Claude darf Dateien lesen, aendern und "
                        "anlegen, aber keine Befehle ausfuehren. Jede Aenderung wird als Git-Commit gespeichert und "
                        "kann mit 'rueckgaengig' zurueckgenommen werden. Nur auf ausdrueckliche Bitte des Nutzers. "
                        "Kostet Geld (typisch 5-100 Cent), der Nutzer muss bestaetigen. Auftrag woertlich weitergeben. Rufe das Werkzeug ohne vorherigen Text auf und sprich erst nach dem Ergebnis."),
        "inputSchema": {"type": "object", "properties": {"auftrag": TEXT}, "required": ["auftrag"],
                        "additionalProperties": False},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
    },
    {
        "name": "rueckgaengig",
        "title": "Letzte Claude-Aenderung zuruecknehmen",
        "description": "Nimmt die letzte Aenderung des Projekt-Claude per git revert zurueck. Nur auf Bitte des Nutzers.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "aenderungen",
        "title": "Letzte Projekt-Aenderungen",
        "description": "Zeigt die letzten 5 Aenderungen (Git-Commits) im Projekt des Projekt-Claude. Nur lesend, kostenlos.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
]
NAMES = {t["name"] for t in TOOLS}


def schluessel() -> str:
    try:
        for zeile in open(ENV_DATEI):
            if zeile.startswith("ANTHROPIC_API_KEY="):
                return zeile.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def git(*args, timeout=30) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", PROJEKT, *args], capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).strip()


def claude(art: str, text: str) -> tuple[str, bool]:
    key = schluessel()
    if not key:
        return "Kein ANTHROPIC_API_KEY in ~/.hermes/.env gefunden.", True
    if git("status", "--porcelain")[1]:
        return "Im Projektordner gibt es ungesicherte Aenderungen; bitte erst pruefen. Nichts ausgefuehrt.", True
    werkzeuge = WERKZEUGE[art]
    cmd = [CLAUDE, "-p", text, "--model", MODELL, "--output-format", "json", "--restricted",
           "--tools", *werkzeuge, "--allowedTools", *werkzeuge, "--permission-mode", "dontAsk",
           "--max-budget-usd", BUDGET[art], "--no-session-persistence", "--strict-mcp-config",
           "--disable-slash-commands", "--append-system-prompt", STIL]
    umgebung = {"HOME": os.path.expanduser("~"), "PATH": "/usr/local/bin:/usr/bin:/bin",
                "LANG": "de_DE.UTF-8", "ANTHROPIC_API_KEY": key, "DISABLE_AUTOUPDATER": "1",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    try:
        p = subprocess.run(cmd, cwd=PROJEKT, env=umgebung, capture_output=True, text=True,
                           timeout=ZEIT[art], stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return f"Claude hat nach {ZEIT[art]} Sekunden nicht fertig geantwortet; abgebrochen.", True
    try:
        d = json.loads(p.stdout)
    except json.JSONDecodeError:
        return f"Claude-Aufruf fehlgeschlagen (Code {p.returncode}): {(p.stderr or p.stdout)[-600:]}", True
    antwort = (d.get("result") or "").strip() or "(keine Textantwort)"
    kosten = d.get("total_cost_usd")
    fuss = f"\n\n[Projekt-Claude {MODELL}, Kosten ca. {kosten * 100:.1f} US-Cent]" if isinstance(kosten, (int, float)) else ""
    fehler = bool(d.get("is_error"))
    if art == "auftrag":
        _, stand = git("status", "--porcelain")
        if stand:
            git("add", "-A")
            rc, out = git("commit", "-q", "-m", f"Claude-Auftrag: {text[:200]}")
            _, stat = git("show", "--stat", "--format=%h %s", "HEAD")
            fuss += f"\n\nGeaenderte Dateien (Git-Commit, rueckgaengig moeglich):\n{stat[-1200:]}"
        else:
            fuss += "\n\nEs wurden keine Dateien geaendert."
    return antwort + fuss, fehler


def call(name: str, args: dict) -> tuple[str, bool]:
    if name == "fragen":
        return claude("fragen", str(args.get("frage", "")).strip())
    if name == "auftrag":
        return claude("auftrag", str(args.get("auftrag", "")).strip())
    if name == "aenderungen":
        rc, out = git("log", "-5", "--format=%h %cr: %s")
        return out or "keine Commits", rc != 0
    if name == "rueckgaengig":
        rc, betreff = git("log", "-1", "--format=%s")
        if rc != 0 or not betreff.startswith("Claude-Auftrag:"):
            return f"Die letzte Aenderung stammt nicht vom Projekt-Claude ('{betreff}'); nichts zurueckgenommen.", True
        rc, out = git("revert", "--no-edit", "HEAD")
        return (f"Zurueckgenommen: {betreff}" if rc == 0 else f"Zuruecknehmen fehlgeschlagen: {out}"), rc != 0
    return f"Unbekanntes Werkzeug {name}", True


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
                          "serverInfo": {"name": "nuorb-projekt-claude", "version": "1.0.0"}})
        elif methode == "ping":
            antwort(mid, {})
        elif methode == "tools/list":
            antwort(mid, {"tools": TOOLS})
        elif methode == "tools/call":
            name = params.get("name", "")
            if name not in NAMES:
                antwort(mid, error={"code": -32602, "message": f"Unbekanntes Werkzeug: {name}"})
                continue
            try:
                text, fehler = call(name, params.get("arguments") or {})
            except Exception as exc:  # nie den Server abstuerzen lassen
                text, fehler = f"Interner Fehler: {exc}", True
            antwort(mid, {"content": [{"type": "text", "text": text}], "isError": fehler})
        else:
            antwort(mid, error={"code": -32601, "message": f"Methode nicht unterstuetzt: {methode}"})


if __name__ == "__main__":
    main()
