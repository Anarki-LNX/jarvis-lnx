"""NuOrb: Update-Prüfung für das Admin-Panel (v0.7.3).

Ein einziger Abruf: die Release-Angabe von GitHub (releases/latest). Automatisch höchstens alle 6 Stunden und nur, wenn
das Admin-Panel offen ist, sonst über den Knopf „Auf Update prüfen“. Abschaltbar unter „Über“ (auto), ganz aus mit
NUORB_UPDATE_CHECK=0. Ergebnis und Einstellung liegen in config/update-check.json.
"""
from __future__ import annotations

import asyncio
import json
import time

import httpx

import nuorb_common as jc

UPDATE_URL = "https://api.github.com/repos/Anarki-LNX/nuorb/releases/latest"
NOTES_PREFIX = "https://github.com/Anarki-LNX/nuorb/"
EVERY = 6 * 3600
MIN_GAP = 60            # Knopf: höchstens einmal pro Minute wirklich abrufen
_lock = asyncio.Lock()
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


def state() -> dict:
    c = cache()
    cur, latest = jc.version(), str(c.get("latest") or "")
    cv, lv = jc.version_tuple(cur), jc.version_tuple(latest)
    return {"current": cur, "label": jc.server_label(), "latest": latest or None, "url": c.get("url"),
            "published": c.get("published"), "checked": c.get("checked"), "error": c.get("error"),
            "newer": bool(cv and lv and lv > cv), "auto": c.get("auto", True) is not False,
            "enabled": enabled(), "kind": jc.env("NUORB_INSTALL_KIND") or None}


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
