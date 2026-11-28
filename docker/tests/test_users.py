"""Getrennte Benutzer (v0.7.4): Zuordnung der Pfade zu nuorb oder hermes. Das eigentliche chown prüft der Image-Lauf
(.work/separation-check.sh), hier laufen die Tests ohne Rechte: dann darf nichts passieren."""
from __future__ import annotations

import os
import unittest
from pathlib import Path

from _lade import APP, lade, temp_ordner

T = temp_ordner("users")
jc = lade("nuorb_common_users_test", APP / "nuorb_common.py", {"HERMES_HOME": str(T), "NUORB_MODELS": str(T / "models")})


class Bereiche(unittest.TestCase):
    def test_geheimnisse_gehoeren_zum_nuorb_bereich(self):
        for rel in ("admin/auth.json", "admin/sessions.json", "certs/nuorb-ca.key", "certs/server.key", "config/devices.json",
                    "config/internal.token", "config/mcp.token", "config/weather.env", "logs/admin/current", "config"):
            self.assertTrue(jc.in_nuorb_area(jc.J / rel), rel)

    def test_von_hermes_geschriebene_ordner_im_nuorb_ordner(self):
        for rel in ("policy/rules.json", "policy/log.jsonl", "policy/fremd/x.json", "cache/weather/x.json", "logs/stt/current", "policy"):
            self.assertFalse(jc.in_nuorb_area(jc.J / rel), rel)

    def test_bereich_von_hermes_ausserhalb(self):
        for p in (T / "config.yaml", T / ".env", T / "SOUL.md", T / "memories/MEMORY.md", T / "skills/x/SKILL.md",
                  T / "smarthome.env", Path("/etc/passwd")):
            self.assertFalse(jc.in_nuorb_area(p), p)

    def test_nicht_auf_umwegen_hinein(self):
        self.assertFalse(jc.in_nuorb_area(jc.J / ".." / "config.yaml"))
        self.assertTrue(jc.in_nuorb_area(jc.J / "policy" / ".." / "admin" / "auth.json"))

    def test_lesedateien_fuer_hermes(self):
        self.assertEqual(set(jc.HERMES_READS), {"mcp.token", "weather.json", "weather.env", "ui.json"})


class OhneTrennung(unittest.TestCase):
    """In Tests und alten Images (kein Benutzer nuorb bzw. nicht als nuorb) ändern die Helfer nichts."""

    def test_nichts_passiert(self):
        self.assertFalse(jc.separated())
        f = T / "x.yaml"
        f.write_text("a: 1\n")
        before = os.stat(f)
        jc.fix_owner(f)
        self.assertEqual(jc.reclaim_hermes_files(T), 0)
        after = os.stat(f)
        self.assertEqual((before.st_uid, before.st_mode), (after.st_uid, after.st_mode))


if __name__ == "__main__":
    unittest.main()
