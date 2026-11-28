"""NuOrb: Update-Prüfung für das Admin-Panel (v0.7.3).

Ein einziger Abruf: die Release-Angabe von GitHub (releases/latest). Automatisch höchstens alle 6 Stunden und nur, wenn
das Admin-Panel offen ist, sonst über den Knopf „Auf Update prüfen“. Abschaltbar unter „Über“ (auto), ganz aus mit
NUORB_UPDATE_CHECK=0. Ergebnis und Einstellung liegen in config/update-check.json.
"""
from __future__ import annotations

import asyncio
import calendar
import json
import os
import re
import secrets
import time
from pathlib import Path

import httpx

import nuorb_common as jc

UPDATE_URL = "https://api.github.com/repos/Anarki-LNX/nuorb/releases/latest"
NOTES_PREFIX = "https://github.com/Anarki-LNX/nuorb/"
EVERY = 6 * 3600
MIN_GAP = 60            # Knopf: höchstens einmal pro Minute wirklich abrufen
_lock = asyncio.Lock()
CONTROL = Path(os.environ.get("NUORB_CONTROL", "/opt/nuorb/control"))   # ./control auf dem Rechner (compose.yaml)
REQUEST_GAP = 600       # höchstens eine Anforderung je 10 Minuten (die Hilfe prüft das selbst noch einmal)
ONE_LINER = "curl -fsSL https://github.com/Anarki-LNX/nuorb/releases/latest/download/install.sh | bash"
COMMANDS = {
    "docker": {"update": ONE_LINER, "rollback": ONE_LINER + " -s -- --rollback"},
    "proxmox": {"update": "update", "rollback": ONE_LINER + " -s -- --rollback --dir /root/nuorb"},
}
transport: httpx.AsyncBaseTransport | None = None   # in Tests ersetzbar


def cache_file():
    return jc.CONF / "update-check.json"


def enabled() -> bool:
    return jc.env("NUORB_UPDATE_CHECK", "1") != "0"


def cache() -> dict:
    try:
        d = json.loads(cache_file().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def set_auto(on: bool) -> None:
    c = cache()
    c["auto"] = bool(on)
    jc._write_json(cache_file(), c)


def _read_json(p: Path) -> dict:
    """Kleine JSON-Datei der Hilfe lesen. Keine Symlinks, höchstens 4 KB, sonst leer."""
    try:
        if p.is_symlink() or p.stat().st_size > 4096:
            return {}
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def helper() -> dict:
    """Update-Hilfe auf dem Rechner: Variante, letzter Status. {} ohne Hilfe."""
    h = _read_json(CONTROL / "status" / "helper.json")
    if h.get("variant") not in ("docker", "proxmox"):
        return {}
    st = _read_json(CONTROL / "status" / "status.json")
    if st.get("state") not in ("running", "done", "failed", "rolled_back", "refused"):
        st = {}
    return {"variant": h["variant"], "auto_rollback": h.get("auto_rollback") is not False,
            "status": {k: str(st.get(k, ""))[:300] for k in ("state", "release", "time", "message", "verified")} if st else None}


def request_update(release: str) -> dict:
    """Anforderung für die Hilfe schreiben. Nur die Version, die die Prüfung gefunden hat, und nur wenn sie neuer ist."""
    st = state()
    if not st["helper"]:
        raise PermissionError("no helper")
    if not st["newer"] or release != st["latest"] or not re.fullmatch(r"v\d{1,4}\.\d{1,4}\.\d{1,4}", release):
        raise ValueError("not the newer release")
    cur = (st["helper"].get("status") or {})
    if cur.get("state") == "running":
        raise RuntimeError("running")
    c = cache()
    if time.time() - float(c.get("requested", 0)) < REQUEST_GAP:
        raise RuntimeError("too soon")
    d = CONTROL / "request"
    if d.is_symlink() or not d.is_dir():
        raise PermissionError("no request folder")
    body = json.dumps({"action": "update", "release": release, "id": secrets.token_hex(16)}, separators=(",", ":"))
    tmp = d / ".request.tmp"
    tmp.write_text(body + "\n", encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, d / "request.json")
    c["requested"] = time.time()
    c["requested_release"] = release
    jc._write_json(cache_file(), c)
    return state()


def pending(c: dict) -> dict | None:
    """Offene Anforderung: angefordert vor weniger als REQUEST_GAP und die Hilfe hat seitdem keinen Status geschrieben."""
    t = float(c.get("requested", 0))
    if not t or time.time() - t > REQUEST_GAP or not helper():   # ohne Hilfe wartet niemand: Befehl statt Wartezustand
        return None
    st = helper().get("status") or {}
    try:   # die Hilfe schreibt UTC (…Z)
        newer_status = bool(st.get("time")) and calendar.timegm(time.strptime(st["time"][:19], "%Y-%m-%dT%H:%M:%S")) >= t - 2
    except ValueError:
        newer_status = False
    return None if newer_status else {"release": c.get("requested_release"), "since": int(t)}


def state() -> dict:
    c = cache()
    cur, latest = jc.version(), str(c.get("latest") or "")
    cv, lv = jc.version_tuple(cur), jc.version_tuple(latest)
    return {"current": cur, "label": jc.server_label(), "latest": latest or None, "url": c.get("url"),
            "published": c.get("published"), "checked": c.get("checked"), "error": c.get("error"),
            "newer": bool(cv and lv and lv > cv), "auto": c.get("auto", True) is not False,
            "enabled": enabled(), "kind": jc.env("NUORB_INSTALL_KIND") or None, "helper": helper() or None,
            "pending": pending(c),
            "commands": COMMANDS.get(jc.env("NUORB_INSTALL_KIND") or "docker", COMMANDS["docker"])}


def due() -> bool:
    """Automatische Prüfung fällig? Nur eingeschaltet und wenn die letzte älter als EVERY ist."""
    st, c = state(), cache()
    return st["enabled"] and st["auto"] and time.time() - float(c.get("t", 0)) > EVERY


async def fetch() -> None:
    """GitHub fragen und das Ergebnis speichern. Fehler werden gespeichert, nie geworfen."""
    async with _lock:
        c = cache()
        if time.time() - float(c.get("t", 0)) < MIN_GAP:
            return
        c.update(t=time.time(), checked=jc.now_iso(), error=None)
        try:
            url = UPDATE_URL
            mock = jc.env("NUORB_UPDATE_URL")
            if mock.startswith("http://127.0.0.1:"):   # nur Tests (e2e mit Mock), nie eine fremde Adresse
                url = mock
            async with httpx.AsyncClient(timeout=8, follow_redirects=False, transport=transport) as cl:
                r = await cl.get(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "NuOrb-Server"})
            d = r.json() if r.status_code == 200 else {}
            tag = str(d.get("tag_name") or "") if isinstance(d, dict) else ""
            if not jc.version_tuple(tag):
                raise ValueError(f"HTTP {r.status_code}")
            url = str(d.get("html_url") or "")
            c.update(latest=tag, published=d.get("published_at"), url=url if url.startswith(NOTES_PREFIX) else None)
        except (httpx.HTTPError, OSError, ValueError) as exc:
            c["error"] = jc.tr("Update-Prüfung fehlgeschlagen", "Update check failed") + f" ({exc.__class__.__name__})"
        jc._write_json(cache_file(), c)
