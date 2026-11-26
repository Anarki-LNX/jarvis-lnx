"""NuOrb: Lizenzverzeichnis des Images beim Bauen erzeugen (/usr/share/doc/nuorb/).

Liest die Metadaten aller Python-Pakete in den beiden venvs (NuOrb und Hermes), schreibt eine Liste
(python-packages.tsv: venv, Paket, Version, Lizenz) und kopiert die mitgelieferten Lizenz-/NOTICE-Dateien
nach python/<venv>/<paket>-<version>/. Läuft offline, ändert nichts an den Paketen.
Aufruf (im Dockerfile): python -I license_inventory.py /usr/share/doc/nuorb
"""
from __future__ import annotations

import importlib.metadata as md
import re
import shutil
import sys
from pathlib import Path

VENVS = {
    "nuorb": "/opt/nuorb/venv/lib/python3*/site-packages",
    "hermes": "/opt/hermes/.venv/lib/python3*/site-packages",
    "hermes-pm": "/opt/hermes/pm-runtime/lib/python3*/site-packages",
}
LIC_FILE = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.I)


def license_of(m) -> str:
    lic = (m.get("License-Expression") or "").strip()
    if not lic:
        cls = [c.split(" :: ")[-1] for c in (m.get_all("Classifier") or []) if c.startswith("License ::")]
        lic = "; ".join(cls) or (m.get("License") or "").strip().split("\n")[0][:80]
    return lic or "see license file"


def main(dest: Path) -> None:
    rows = []
    for venv, pattern in VENVS.items():
        for sp in sorted(Path("/").glob(pattern.lstrip("/"))):
            for d in md.distributions(path=[str(sp)]):
                name, ver = d.metadata["Name"], d.metadata["Version"]
                rows.append((venv, name, ver, license_of(d.metadata)))
                target = dest / "python" / venv / f"{name}-{ver}"
                for f in d.files or []:
                    p = Path(f)
                    if ".dist-info" in str(p.parent) and LIC_FILE.match(p.name):
                        src = Path(d.locate_file(f))
                        if src.is_file():
                            target.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(src, target / p.name)
    rows.sort(key=lambda r: (r[0], r[1].lower()))
    (dest / "python-packages.tsv").write_text(
        "venv\tpackage\tversion\tlicense\n" + "".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")
    print(f"[nuorb-licenses] {len(rows)} Python packages listed in {dest}/python-packages.tsv")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/share/doc/nuorb"))
