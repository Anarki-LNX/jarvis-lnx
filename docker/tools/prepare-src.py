#!/usr/bin/env python3
"""Kopiert NuOrb-Oberfläche, NuOrb-Admin und den STT-Router in docker/src/ (Build-Kontext des Images).

Dabei werden nutzerspezifische Werte (LAN-Adressen, Unit-IDs, Namen) durch neutrale Platzhalter ersetzt.
Danach prüft ein Wächter den ganzen Ordner: Findet er noch etwas Privates, bricht er mit Exit 1 ab, und es
wird nichts gebaut.

Aufruf (vom Projektordner aus):  python3 docker/tools/prepare-src.py [--quelle PFAD]
  --quelle: Projektwurzel mit jarvis-ui/, jarvis-admin/, scripts/ (Standard: zwei Ebenen über diesem Skript).
            Für das öffentliche Repo geht auch dessen Layout (ui/, admin/).

Jede Ersetzung MUSS greifen (sonst Abbruch), damit eine geänderte Quelle nicht still durchrutscht. Fällt eine
Ersetzung weg, weil die Quelle sie nicht mehr braucht: Regel hier entfernen.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
DOCKER = HIER.parent
ZIEL = DOCKER / "src"

# Regeln und Verbotsliste enthalten zwangsläufig die privaten Werte selbst. Sie liegen deshalb NICHT hier, sondern in
# tools/sanitize_local.py (git-ignoriert, nie veröffentlichen). Ohne diese Datei wird nur generisch geprüft.
# Format dort: REGELN = [(datei, muster, ersatz, mindest_treffer), ...]; VERBOTEN = [regex, ...]
REGELN: list[tuple[str, str, str, int]] = [
    ("ui/server.py", r"XIAOMI REBIRTH / JARVIS", "JARVIS LNX", 0),
    ("stt/stt_router.py", r"XIAOMI REBIRTH / JARVIS", "JARVIS LNX", 0),
]
# generisch: private Netze im Code (außer CIDR-Listen), API-Schlüssel, SSH-Schlüsselnamen
VERBOTEN = [r"\b192\.168\.(?!1\.50\b)\d+\.\d+\b(?!/)",  # 192.168.1.50 = dokumentierte Beispieladresse (wie in der CI)
            r"\b10\.\d+\.\d+\.\d+\b(?!/)", r"sk-ant-[A-Za-z0-9]", r"id_ed25519\w*",
            r"-----BEGIN [A-Z ]*PRIVATE KEY"]
try:
    sys.path.insert(0, str(HIER))
    import sanitize_local  # noqa: E402
    REGELN = sanitize_local.REGELN + REGELN
    VERBOTEN = VERBOTEN + sanitize_local.VERBOTEN
    print("Private Bereinigungsregeln geladen (tools/sanitize_local.py).")
except ImportError:
    print("Hinweis: tools/sanitize_local.py fehlt – nur generische Prüfung.", file=sys.stderr)


def quelle_layout(q: Path) -> dict[str, Path]:
    if (q / "jarvis-ui").is_dir():
        return {"ui": q / "jarvis-ui", "admin": q / "jarvis-admin", "stt": q / "scripts/sprache-stt-router.py"}
    return {"ui": q / "ui", "admin": q / "admin", "stt": q / "scripts/sprache-stt-router.py"}


def kopieren(q: Path) -> None:
    lay = quelle_layout(q)
    if ZIEL.exists():
        shutil.rmtree(ZIEL)
    (ZIEL / "ui").mkdir(parents=True)
    for f in ("server.py", "demo_runs.py"):
        shutil.copy2(lay["ui"] / f, ZIEL / "ui" / f)
    shutil.copytree(lay["ui"] / "static", ZIEL / "ui/static",
                    ignore=shutil.ignore_patterns("mictest.html", "*.pyc", "__pycache__", ".*"))
    (ZIEL / "admin").mkdir()
    shutil.copy2(lay["admin"] / "server.py", ZIEL / "admin/server.py")
    shutil.copytree(lay["admin"] / "static", ZIEL / "admin/static", ignore=shutil.ignore_patterns(".*"))
    (ZIEL / "stt").mkdir()
    shutil.copy2(lay["stt"], ZIEL / "stt/stt_router.py")


def ersetzen() -> list[str]:
    fehler = []
    for datei, muster, ersatz, mindest in REGELN:
        p = ZIEL / datei
        text = p.read_text(encoding="utf-8")
        neu, n = re.subn(muster, ersatz, text)
        if n < mindest:  # 0 = optional; was trotzdem privat bleibt, findet der Wächter
            fehler.append(f"Regel griff nicht ({n}x < {mindest}): {datei}: {muster}")
        p.write_text(neu, encoding="utf-8")
    return fehler


def waechter() -> list[str]:
    funde = []
    for p in sorted(ZIEL.rglob("*")):
        if not p.is_file() or p.suffix in (".woff2",):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for muster in VERBOTEN:
            for m in re.finditer(muster, text, re.I):
                zeile = text.count("\n", 0, m.start()) + 1
                funde.append(f"{p.relative_to(DOCKER)}:{zeile}: {m.group(0)!r}")
    return funde


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quelle", type=Path, default=DOCKER.parent)
    a = ap.parse_args()
    kopieren(a.quelle.resolve())
    fehler = ersetzen()
    funde = waechter()
    for f in fehler:
        print("FEHLER", f, file=sys.stderr)
    for f in funde:
        print("PRIVAT", f, file=sys.stderr)
    if fehler or funde:
        print("Abbruch: docker/src/ ist nicht sauber. Nichts bauen.", file=sys.stderr)
        return 1
    n = sum(1 for p in ZIEL.rglob("*") if p.is_file())
    print(f"docker/src/ bereit ({n} Dateien), Privatsphäre-Prüfung bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
