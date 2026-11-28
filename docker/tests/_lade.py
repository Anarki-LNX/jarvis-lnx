"""Hilfen für die Unit-Tests: Server-Module mit Daten in einem Temp-Ordner laden.

Die Server lesen ihre Pfade beim Import aus der Umgebung. Darum setzt `lade()` die Variablen vor dem Import und
lädt das Modul jedes Mal frisch unter eigenem Namen.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
DOCKER = HIER.parent
SRC = Path(os.environ.get("NUORB_TEST_SRC", DOCKER / "src"))
APP = DOCKER / "app"


def temp_ordner(name: str) -> Path:
    basis = os.environ.get("NUORB_TEST_TMP")  # nie /tmp erzwingen, aber erlauben (CI: RUNNER_TEMP)
    return Path(tempfile.mkdtemp(prefix=f"nuorb-{name}-", dir=basis))


def lade(modulname: str, datei: Path, env: dict[str, str]):
    os.environ.update(env)
    pfad = str(datei.parent)
    if pfad not in sys.path:
        sys.path.insert(0, pfad)
    spec = importlib.util.spec_from_file_location(modulname, datei)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modulname] = mod
    spec.loader.exec_module(mod)
    return mod
