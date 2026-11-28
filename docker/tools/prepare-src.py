#!/usr/bin/env python3
"""Kopiert NuOrb-Oberfläche, NuOrb-Admin und den STT-Router in docker/src/ (Build-Kontext des Images).

Dabei werden nutzerspezifische Werte (LAN-Adressen, Unit-IDs, Namen) durch neutrale Platzhalter ersetzt.
Danach prüft ein Wächter den ganzen Ordner: Findet er noch etwas Privates, bricht er mit Exit 1 ab, und es
wird nichts gebaut.

Aufruf (vom Projektordner aus):  python3 docker/tools/prepare-src.py [--quelle PFAD]
  --quelle: Projektwurzel mit nuorb-ui/, nuorb-admin/, scripts/ (Standard: zwei Ebenen über diesem Skript).
            Das ist die private Arbeitskopie des Maintainers. Im öffentlichen Repo ist docker/src selbst die
            Quelle (siehe SOURCES.md), dort wird dieses Skript nicht gebraucht.

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
    ("ui/server.py", r"XIAOMI REBIRTH / NuOrb", "NuOrb", 0),
    ("stt/stt_router.py", r"XIAOMI REBIRTH / NuOrb", "NuOrb", 0),
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
    if not (q / "nuorb-ui").is_dir():
        sys.exit(f"{q} hat kein nuorb-ui/. Im öffentlichen Repo ist docker/src schon die Quelle (SOURCES.md).")
    return {"ui": q / "nuorb-ui", "admin": q / "nuorb-admin", "stt": q / "scripts/sprache-stt-router.py", "scripts": q / "scripts"}


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
    # Smart Home (optional im Image, standardmäßig aus): MCP-Server + Skill vom NuOrb-KI-Backend
    (ZIEL / "smarthome").mkdir()
    shutil.copy2(lay["scripts"] / "backend-smarthome-mcp.py", ZIEL / "smarthome/smarthome_mcp.py")
    shutil.copy2(lay["scripts"] / "backend-smarthome-SKILL.md", ZIEL / "smarthome/SKILL.md")


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
                funde.append(f"{p.relative_to(ZIEL.parent)}:{zeile}: {m.group(0)!r}")
    return funde


def vergleichen(a: Path, b: Path, ohne: set[str]) -> list[str]:
    """Unterschiede zwischen zwei Ordnern (fehlende, zusätzliche, abweichende Dateien), relativ benannt."""
    def dateien(d: Path) -> dict[str, Path]:
        return {str(p.relative_to(d)): p for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    da, db = dateien(a), dateien(b)
    out = []
    for name in sorted(set(da) | set(db)):
        if name in ohne:
            continue
        if name not in db:
            out.append(f"fehlt in {b}: {name}")
        elif name not in da:
            out.append(f"zusätzlich in {b}: {name}")
        elif da[name].read_bytes() != db[name].read_bytes():
            out.append(f"weicht ab: {name}")
    return out


def main() -> int:
    global ZIEL
    ap = argparse.ArgumentParser()
    ap.add_argument("--quelle", type=Path, default=DOCKER.parent)
    ap.add_argument("--check", type=Path, nargs="?", const=ZIEL, metavar="ORDNER",
                    help="nur in einen Arbeitsordner erzeugen und mit ORDNER vergleichen (Standard docker/src); "
                         "Exit 1, wenn ORDNER nicht genau dem Ergebnis entspricht")
    ap.add_argument("--ohne", action="append", default=[], metavar="DATEI",
                    help="beim Vergleich auslassen, relativ zu docker/src (mehrfach möglich)")
    a = ap.parse_args()
    if a.check:
        import tempfile
        basis = Path.home() / ".cache" / "nuorb-prepare-src"   # nie /tmp
        basis.mkdir(parents=True, exist_ok=True)
        ZIEL = Path(tempfile.mkdtemp(prefix="check-", dir=basis)) / "src"
        try:
            rc = erzeugen(a.quelle.resolve())
            if rc:
                return rc
            diff = vergleichen(ZIEL, a.check.resolve(), set(a.ohne))
            for d in diff:
                print("VERALTET", d, file=sys.stderr)
            if diff:
                print(f"{a.check} ist nicht aus der Quelle erzeugt. prepare-src.py ausführen und erneut übernehmen.", file=sys.stderr)
                return 1
            print(f"{a.check} entspricht der Quelle.")
            return 0
        finally:
            shutil.rmtree(ZIEL.parent, ignore_errors=True)
    return erzeugen(a.quelle.resolve())


def erzeugen(quelle: Path) -> int:
    kopieren(quelle)
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
    print(f"{ZIEL.relative_to(DOCKER) if ZIEL.is_relative_to(DOCKER) else ZIEL}/ bereit ({n} Dateien), Privatsphäre-Prüfung bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
