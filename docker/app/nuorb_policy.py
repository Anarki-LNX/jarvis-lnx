#!/usr/bin/env python3
"""NuOrb: Sicherheitsregeln für Werkzeugaufrufe von Hermes, außerhalb des Sprachmodells (S5 und S6).

Hermes ruft dieses Skript als Shell-Hook auf (config.yaml, hooks.pre_tool_call und hooks.post_tool_call, eingetragen
von first_run.py). Eingabe auf stdin: JSON mit tool_name, tool_input und session_id. Ausgabe auf stdout: nichts
(erlaubt) oder eine Anweisung an Hermes.

S6, fremde Inhalte: Hat der Assistent in einer Sitzung fremde Inhalte gelesen (Websuche, Webseite, Browser, Datei,
Bild, ein vom Nutzer hinzugefügter MCP-Server), wird die Sitzung markiert. Danach braucht jede Aktion mit Wirkung
eine Bestätigung auf der Karte der Oberfläche ({"action": "approve"}). Die Markierung gilt für die ganze Sitzung
(höchstens MARK_TTL), nicht nur für einen Durchgang.

S5, Heimnetz: Shell, Python und Browser dürfen keine privaten, Loopback- oder Link-Local-Ziele ansprechen, außer
den Adressen, die in der Konfiguration stehen (Gehirn, MCP, Smart Home). Das ist eine zweite Schicht, denn diese
Werkzeuge sind im engen Standard ohnehin aus.

Aufruf:  nuorb_policy.py pre|post   (pre mit fail_closed: ein Fehler hier blockiert den Aufruf)
"""
from __future__ import annotations

import functools
import hashlib
import ipaddress
import json
import os
import re
import socket
import sys
import time
from pathlib import Path

DATA = Path(os.environ.get("HERMES_HOME", "/opt/data"))
MARKS = DATA / "nuorb" / "policy" / "fremd"
MARK_TTL = 24 * 3600

# Werkzeuge, deren Ergebnis fremden Text enthalten kann
SOURCE_TOOLS = {"web_search", "web_extract", "read_file", "search_files", "vision_analyze", "session_search"}
# Eigene MCP-Werkzeuge, die nur lesen und deren Ergebnis keine fremden Anweisungen trägt
OWN_READ_MCP = re.compile(r"^mcp__(smarthome__(geraete|zustand|raeume)|wetter__wetter|nuorb__[a-z_]*(lesen|status|info))$")
# Werkzeuge mit Wirkung (nach fremden Inhalten nur mit Bestätigung)
EFFECT_TOOLS = {"terminal", "process_manage", "execute_code", "write_file", "patch", "cronjob_manage", "delegate_task",
                "skill_manage", "memory", "image_generate", "browser_exec", "browser_cdp", "browser_dialog", "browser_vault"}
# Werkzeuge, die Netzwerkziele aus freiem Text ansprechen können (S5)
NET_TOOLS = {"terminal", "process_manage", "execute_code", "browser_exec", "browser_cdp"}

URL_RE = re.compile(r"\b(https?|wss?|ftp)://(?:[^\s/@'\"<>]*@)?(\[[0-9a-fA-F:.]+\]|[A-Za-z0-9.\-_]+)(?::(\d{1,5}))?", re.I)
DEFAULT_PORT = {"http": 80, "https": 443, "ws": 80, "wss": 443, "ftp": 21}
IP_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.])")
LOCAL_NAMES = re.compile(r"^(localhost|[a-z0-9\-]+\.(local|lan|home|internal|localdomain|home\.arpa|fritz\.box))$", re.I)


def is_mcp(tool: str) -> bool:
    return tool.startswith("mcp__")


def is_source(tool: str) -> bool:
    if tool in SOURCE_TOOLS or tool.startswith("browser_"):
        return True
    return is_mcp(tool) and not OWN_READ_MCP.match(tool) and not is_effect_mcp_own(tool)


def is_effect_mcp_own(tool: str) -> bool:
    return bool(re.match(r"^mcp__(smarthome_schalten|geraet|nuorb)__", tool))


def is_effect(tool: str) -> bool:
    return tool in EFFECT_TOOLS or (is_mcp(tool) and not OWN_READ_MCP.match(tool))


def mark_file(session: str) -> Path:
    return MARKS / (hashlib.sha256(session.encode("utf-8", "replace")).hexdigest()[:32] + ".json")


def marked(session: str) -> dict | None:
    if not session:
        return None
    try:
        d = json.loads(mark_file(session).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and time.time() - float(d.get("t", 0)) < MARK_TTL else None


def set_mark(session: str, tool: str) -> None:
    if not session:
        return
    MARKS.mkdir(parents=True, exist_ok=True, mode=0o700)
    p = mark_file(session)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"t": time.time(), "tool": tool}), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)
    for old in MARKS.glob("*.json"):   # alte Markierungen aufräumen
        try:
            if time.time() - old.stat().st_mtime > MARK_TTL:
                old.unlink()
        except OSError:
            pass


def url_targets(text: str) -> set[tuple[str, int]]:
    """(host, port) jeder URL im Text, Port aus dem Schema, wenn keiner dasteht."""
    return {(h.strip("[]").lower(), int(port) if port else DEFAULT_PORT.get(scheme.lower(), 0))
            for scheme, h, port in URL_RE.findall(text)}


def configured_targets() -> set[tuple[str, int]]:
    """Ziele aus der Hermes-Konfiguration (Gehirn, MCP-URLs) und dem Smart-Home-Zugang: die darf Shell und Browser.
    Verglichen wird Host UND Port, sonst gäbe eine eingetragene 127.0.0.1-Adresse den ganzen Container frei."""
    targets: set[tuple[str, int]] = set()
    for f in (DATA / "config.yaml", DATA / "smarthome.env"):
        try:
            targets |= url_targets(f.read_text(encoding="utf-8"))
        except OSError:
            continue
    return targets


def private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified or ip.is_multicast


@functools.lru_cache(maxsize=64)
def resolve(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    socket.setdefaulttimeout(2)
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return []
    out = []
    for info in infos:
        try:
            out.append(ipaddress.ip_address(str(info[4][0]).split("%")[0]))
        except ValueError:
            continue
    return out


def home_targets(text: str) -> list[str]:
    """Ziele im Heimnetz (oder im Container selbst), die nicht in der Konfiguration stehen."""
    allowed = configured_targets()
    allowed_hosts = {h for h, _ in allowed}
    found = []
    url_hosts = url_targets(text)
    bare = {(ip, 0) for ip in IP_RE.findall(text)} - {(h, 0) for h, _ in url_hosts}
    for host, port in sorted(url_hosts | bare):
        by_name = bool(LOCAL_NAMES.match(host))
        if not by_name and not any(private_ip(ip) for ip in resolve(host)):
            continue
        loopback = host == "localhost" or (not by_name and any(ip.is_loopback for ip in resolve(host)))
        if (host, port) in allowed or (port == 0 and host in allowed_hosts and not loopback):
            continue
        found.append(f"{host}:{port}" if port else host)
    return found


def decide(event: str, data: dict) -> dict | None:
    tool = str(data.get("tool_name") or "")
    session = str(data.get("session_id") or "")
    args = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    if event == "post":
        if is_source(tool):
            set_mark(session, tool)
        return None
    if tool in NET_TOOLS:
        ziele = home_targets(json.dumps(args, ensure_ascii=False))
        if ziele:
            return {"action": "block", "message": "NuOrb blocks access to addresses in the home network from this tool "
                    f"({', '.join(ziele[:3])}). Use the dedicated NuOrb tools instead."}
    m = marked(session)
    if m and is_effect(tool):
        return {"action": "approve", "message": f"After reading outside content ({m.get('tool')}), this action needs "
                "your confirmation.", "rule_key": f"nuorb-fremd:{tool}:{time.time_ns()}"}
    return None


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    if event not in ("pre", "post"):
        print("usage: nuorb_policy.py pre|post", file=sys.stderr)
        return 2
    data = json.loads(sys.stdin.read() or "{}")
    out = decide(event, data if isinstance(data, dict) else {})
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
