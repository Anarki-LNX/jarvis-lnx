#!/usr/bin/env python3
"""NuOrb: MCP-Server „wetter“ (stdio, nur Standardbibliothek), nur lesend, ohne Bestätigung.

Werkzeug für Hermes:
  wetter {zeitraum: jetzt|heute|morgen|woche|warnungen}
Liefert einen fertigen, vorlesbaren Satz in der Sprache des Assistenten (ui.json "lang", sonst NUORB_LANG).
Ort und Anbieter richtet der Nutzer in der Verwaltung unter „Wetter“ ein (nuorb_weather.py).
Direkt ohne Modell (Diagnose):  python3 nuorb_weather_mcp.py --satz [zeitraum] [de|en]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nuorb_weather as nw  # noqa: E402

TOOLS = [{
    "name": "wetter",
    "title": "Wetter",
    "description": (
        "Current weather, forecast and official warnings for the user's place (set up in the NuOrb admin panel). "
        "ALWAYS use this for any question about weather, temperature outside, rain, snow, wind, frost or warnings. "
        "Never guess, never use web search. zeitraum: 'jetzt' for right now, 'heute' for the rest of today, "
        "'morgen' for tomorrow, 'woche' for the next days or the weekend, 'warnungen' for official warnings. "
        "The result is a finished sentence with numbers written out: speak it almost word for word, keep the "
        "source it names, add nothing. Call the tool without any text before it."),
    "inputSchema": {"type": "object",
                    "properties": {"zeitraum": {"type": "string", "enum": list(nw.PERIODS),
                                                "description": "jetzt, heute, morgen, woche or warnungen"}},
                    "additionalProperties": False},
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True},
}]


def assistant_lang() -> str:
    try:
        v = json.loads((nw.CONF / "ui.json").read_text(encoding="utf-8")).get("lang")
    except (OSError, ValueError, AttributeError):
        v = None
    if v in ("de", "en"):
        return v
    return "en" if os.environ.get("NUORB_LANG", "de").strip().lower().startswith("en") else "de"


def call(name: str, args: dict) -> tuple[str, bool]:
    if name != "wetter":
        return f"Unknown tool: {name}", True
    try:
        return nw.report(str(args.get("zeitraum") or "jetzt"), assistant_lang())
    except Exception as e:  # nie den Server abstürzen lassen, nie Schlüssel ausgeben
        return f"Internal weather error ({e.__class__.__name__}).", True


def send(mid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": mid}
    msg["error" if error is not None else "result"] = error if error is not None else result
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        try:
            req = json.loads(line)
        except ValueError:
            continue
        mid, method, params = req.get("id"), req.get("method", ""), req.get("params") or {}
        if mid is None:
            continue
        if method == "initialize":
            send(mid, {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                       "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": "nuorb-wetter", "version": "1.0.0"}})
        elif method == "ping":
            send(mid, {})
        elif method == "tools/list":
            send(mid, {"tools": TOOLS})
        elif method == "tools/call":
            text, err = call(params.get("name"), params.get("arguments") or {})
            send(mid, {"content": [{"type": "text", "text": text}], "isError": err})
        else:
            send(mid, error={"code": -32601, "message": f"Method not supported: {method}"})


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--satz":
        text, err = nw.report(sys.argv[2] if len(sys.argv) > 2 else "jetzt",
                              sys.argv[3] if len(sys.argv) > 3 else assistant_lang())
        print(text)
        sys.exit(1 if err else 0)
    main()
