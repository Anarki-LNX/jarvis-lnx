"""NuOrb: Docker-Erweiterungen sauber in die Apps von Oberfläche und Admin-Panel einhängen.

Die Server in docker/src bringen ihre eigenen Routen mit. Das Image ergänzt oder ersetzt einige davon
(Einrichtung, Kopplung, Seiten, Statusfelder). Statt die Routenliste von Hand zu verändern, laufen beide
Einstiege (ui_main.py, admin_main.py) über diese zwei Funktionen:

- original_endpoint(): holt die Original-Funktion einer Route, die eine Erweiterung umhüllt. Fehlt sie,
  bricht der Start sofort mit einer klaren Meldung ab, statt später bei der ersten Anfrage.
- extend_routes(): setzt die neuen Routen vor die Originale (die erste passende Route gewinnt) und entfernt
  Originale, die dadurch vollständig verdeckt sind, damit keine toten Doppelungen bleiben.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


def _methods(route: Any) -> set[str]:
    return set(getattr(route, "methods", None) or ())


def _is_endpoint_route(route: Any) -> bool:
    # Route und APIRoute haben path, endpoint und methods; Mounts (Static) und WebSockets bleiben unberührt
    return hasattr(route, "endpoint") and hasattr(route, "path") and bool(_methods(route))


def original_endpoint(app: Any, path: str, method: str = "GET") -> Callable[..., Any]:
    """Endpunkt der bestehenden Route für path und method. RuntimeError, wenn es sie nicht gibt."""
    for r in app.router.routes:
        if _is_endpoint_route(r) and r.path == path and method in _methods(r):
            return r.endpoint
    raise RuntimeError(f"Route {method} {path} fehlt in der Quelle, die Docker-Erweiterung kann sie nicht umhüllen")


def extend_routes(app: Any, routes: Iterable[Any]) -> list[str]:
    """Neue Routen vor die bestehenden setzen. Gibt die entfernten, vollständig verdeckten Originale zurück.

    Doppelte Einträge (gleicher Pfad und gleiche Methode) in routes selbst sind ein Programmierfehler
    und brechen ab. Ein Original bleibt, solange es noch Methoden bedient, die keine neue Route abdeckt.
    """
    new = list(routes)
    covered: dict[str, set[str]] = {}
    for r in new:
        if not _is_endpoint_route(r):
            raise TypeError(f"Nur Routen mit Endpunkt erlaubt, nicht {type(r).__name__}")
        doppelt = covered.setdefault(r.path, set()) & _methods(r)
        if doppelt:
            raise ValueError(f"Route {r.path} ({', '.join(sorted(doppelt))}) ist doppelt eingetragen")
        covered[r.path] |= _methods(r)
    removed, keep = [], []
    for r in app.router.routes:
        if _is_endpoint_route(r) and r.path in covered and _methods(r) - {"HEAD"} <= covered[r.path]:
            removed.append(f"{'/'.join(sorted(_methods(r) - {'HEAD'}))} {r.path}")
            continue
        keep.append(r)
    app.router.routes[:] = new + keep
    return removed
