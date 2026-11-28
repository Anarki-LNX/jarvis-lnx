#!/usr/bin/env python3
"""Lizenzprüfung der Python-Pakete im NuOrb-venv (Phase 7, Härtung 2).

Liest python-packages.tsv aus dem Image (erzeugt von app/license_inventory.py beim Bauen) von stdin und prüft
nur das NuOrb-venv (Hermes bringt seine Pakete selbst mit). Erlaubt sind freizügige Lizenzen. Copyleft nur für
Pakete, die schon in THIRD_PARTY_LICENSES.md, Abschnitt 1, stehen, und nur mit genau dieser Lizenz. Ein neues
Paket mit unbekannter oder Copyleft-Lizenz lässt die Prüfung scheitern, bis es geprüft und eingetragen ist.

Aufruf:  docker run --rm --entrypoint cat <image> /usr/share/doc/nuorb/python-packages.tsv | python3 docker/tools/license-check.py
"""
from __future__ import annotations

import re
import sys

PERMISSIVE = re.compile(
    r"^(MIT(-0)?|MIT License|BSD(-[0-3]-Clause)?|BSD License|0BSD|[23]-Clause BSD License|Apache(-2\.0| Software License| licensed.*)|"
    r"ISC|PSF-2\.0|Python Software Foundation License|Zlib|CC0-1\.0|Unlicense|MPL-2\.0|Mozilla Public License 2\.0 \(MPL 2\.0\))$", re.I)
# Copyleft, geprüft und in THIRD_PARTY_LICENSES.md (Abschnitt 1) genannt
REVIEWED = {
    "piper-tts": "GPL-3.0-or-later",
    "zeroconf": "LGPL-2.1-or-later",
}


def ok(name: str, lic: str) -> bool:
    if REVIEWED.get(name.lower()) == lic:
        return True
    if PERMISSIVE.match(lic.strip()):
        return True
    parts = [p.strip(" ()") for p in re.split(r"\s+(?:AND|OR)\s+|;\s*", lic) if p.strip()]
    return bool(parts) and all(PERMISSIVE.match(p) for p in parts)


def main() -> int:
    bad, n = [], 0
    for line in sys.stdin:
        cols = line.rstrip("\n").split("\t")
        if len(cols) < 4 or cols[0] != "nuorb":
            continue
        n += 1
        _, name, ver, lic = cols[:4]
        if not ok(name, lic):
            bad.append(f"{name} {ver}: {lic}")
    if not n:
        print("Keine Pakete des NuOrb-venv gefunden (python-packages.tsv leer oder falsches Format).", file=sys.stderr)
        return 2
    for b in bad:
        print("LIZENZ PRÜFEN", b, file=sys.stderr)
    if bad:
        print("Neue oder unbekannte Lizenzen: prüfen, in THIRD_PARTY_LICENSES.md eintragen und hier freigeben.", file=sys.stderr)
        return 1
    print(f"{n} Pakete des NuOrb-venv, alle Lizenzen bekannt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
