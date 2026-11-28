"""Update-Hilfe auf dem Rechner (docker/nuorb-update-run, v0.7.3) mit Stellvertretern: Releases aus einem Ordner
(file://), install.sh und docker protokollieren nur, gh ist nicht angemeldet."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import unittest
from pathlib import Path

from _lade import DOCKER, temp_ordner

HELPER = DOCKER / "nuorb-update-run"
FAKE_INSTALL = """#!/usr/bin/env bash
echo "$*" >> "$CALLS"
case "$*" in *--rollback*) exit "${FAKE_RB_RC:-0}" ;; esac
exit "${FAKE_INSTALL_RC:-0}"
"""
FAKE_DOCKER = """#!/usr/bin/env bash
[ "$1" = inspect ] && echo "${FAKE_HEALTH:-healthy}"
exit 0
"""


class UpdateHilfe(unittest.TestCase):
    def setUp(self):
        self.t = Path(temp_ordner("helper"))
        self.d = self.t / "inst"
        (self.d / "control" / "request").mkdir(parents=True)
        (self.d / "control" / "status").mkdir(parents=True)
        (self.d / ".env").write_text("NUORB_VERSION=0.7.3\n")
        self.calls = self.t / "calls.log"
        bin_ = self.t / "bin"
        bin_.mkdir()
        (bin_ / "gh").write_text("#!/bin/sh\nexit 1\n")
        (bin_ / "docker").write_text(FAKE_DOCKER)
        for f in bin_.iterdir():
            f.chmod(0o755)
        self.release("v0.7.4")
        self.env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "NUORB_DL_BASE": f"file://{self.t}/rel",
                    "NUORB_DOCKER": str(bin_ / "docker"), "NUORB_UPDATE_HEALTH_WAIT": "5", "CALLS": str(self.calls),
                    "TMPDIR": str(self.t)}

    def release(self, tag, kaputt=False):
        r = self.t / "rel" / "download" / tag
        r.mkdir(parents=True, exist_ok=True)
        (r / "install.sh").write_text(FAKE_INSTALL)
        h = hashlib.sha256(FAKE_INSTALL.encode()).hexdigest()
        (r / "SHA256SUMS").write_text(("0" * 64 if kaputt else h) + "  install.sh\n")

    def anfordern(self, body):
        (self.d / "control" / "request" / "request.json").write_text(body if isinstance(body, str) else json.dumps(body, separators=(",", ":")))

    def lauf(self, **env):
        subprocess.run(["bash", str(HELPER), "--dir", str(self.d), "--name", "nuorbtest"], env={**self.env, **env},
                       capture_output=True, text=True, timeout=60)
        st = self.d / "control" / "status" / "status.json"
        return json.loads(st.read_text()) if st.exists() else {}

    def aufrufe(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_gueltige_anforderung_aktualisiert(self):
        self.anfordern({"action": "update", "release": "v0.7.4", "id": "a" * 32})
        st = self.lauf()
        self.assertEqual(st["state"], "done", st)
        self.assertEqual(st["verified"], "checksum")   # gh nicht angemeldet: nur die Prüfsumme
        self.assertEqual(self.aufrufe(), [f"--dir {self.d} --name nuorbtest --release v0.7.4 --yes --no-firewall"])

    def test_gleiche_anforderung_nur_einmal(self):
        self.anfordern({"action": "update", "release": "v0.7.4", "id": "b" * 32})
        self.lauf()
        self.lauf(NUORB_UPDATE_MIN_GAP="0")
        self.assertEqual(len(self.aufrufe()), 1)

    def test_ungueltige_anforderungen_werden_abgelehnt(self):
        for body in ('{"action":"update","release":"v0.7.4","id":"' + "c" * 32 + '","cmd":"rm -rf /"}',
                     '{"action":"update","release":"v0.7.4; id","id":"' + "c" * 32 + '"}',
                     '{"action":"install","release":"v0.7.4","id":"' + "c" * 32 + '"}',
                     "x" * 600):
            self.anfordern(body)
            st = self.lauf()
            self.assertEqual(st.get("state"), "refused", body[:40])
        self.assertEqual(self.aufrufe(), [])

    def test_symlink_wird_abgelehnt(self):
        target = self.t / "fremd.json"
        target.write_text(json.dumps({"action": "update", "release": "v0.7.4", "id": "d" * 32}))
        (self.d / "control" / "request" / "request.json").symlink_to(target)
        self.assertEqual(self.lauf()["state"], "refused")
        self.assertEqual(self.aufrufe(), [])

    def test_kein_downgrade_und_keine_gleiche_version(self):
        for tag in ("v0.7.3", "v0.7.2"):
            self.release(tag)
            self.anfordern({"action": "update", "release": tag, "id": hashlib.md5(tag.encode()).hexdigest()})
            self.assertEqual(self.lauf()["state"], "refused", tag)
        self.assertEqual(self.aufrufe(), [])

    def test_hoechstens_alle_zehn_minuten(self):
        self.anfordern({"action": "update", "release": "v0.7.4", "id": "e" * 32})
        self.lauf()
        (self.d / ".env").write_text("NUORB_VERSION=0.7.3\n")
        self.anfordern({"action": "update", "release": "v0.7.4", "id": "f" * 32})
        self.assertEqual(self.lauf()["state"], "refused")
        self.assertEqual(len(self.aufrufe()), 1)

    def test_falsche_pruefsumme_bricht_ab(self):
        self.release("v0.7.4", kaputt=True)
        self.anfordern({"action": "update", "release": "v0.7.4", "id": "1" * 32})
        self.assertEqual(self.lauf()["state"], "refused")
        self.assertEqual(self.aufrufe(), [])

    def test_attestierung_als_pflicht_ohne_gh(self):
        self.anfordern({"action": "update", "release": "v0.7.4", "id": "2" * 32})
        self.assertEqual(self.lauf(NUORB_REQUIRE_ATTESTATION="1")["state"], "refused")
        self.assertEqual(self.aufrufe(), [])

    def test_mit_angemeldetem_gh_auch_herkunft_geprueft(self):
        (self.t / "bin" / "gh").write_text("#!/bin/sh\nexit 0\n")   # angemeldet, Attestierung gültig
        self.anfordern({"action": "update", "release": "v0.7.4", "id": "6" * 32})
        st = self.lauf()
        self.assertEqual((st["state"], st["verified"]), ("done", "checksum+attestation"))

    def test_mit_angemeldetem_gh_und_falscher_herkunft_abgelehnt(self):
        (self.t / "bin" / "gh").write_text('#!/bin/sh\n[ "$1" = auth ] && exit 0\nexit 1\n')
        self.anfordern({"action": "update", "release": "v0.7.4", "id": "7" * 32})
        self.assertEqual(self.lauf()["state"], "refused")
        self.assertEqual(self.aufrufe(), [])

    def test_ungesund_dann_automatisch_zurueck(self):
        self.anfordern({"action": "update", "release": "v0.7.4", "id": "3" * 32})
        st = self.lauf(FAKE_HEALTH="unhealthy")
        self.assertEqual(st["state"], "rolled_back", st)
        self.assertIn("--rollback --yes", self.aufrufe()[-1])
        self.assertIn("rolled back", (self.d / "control" / "status" / "update.log").read_text())

    def test_ohne_automatischen_rueckweg_nur_hinweis(self):
        self.anfordern({"action": "update", "release": "v0.7.4", "id": "4" * 32})
        st = self.lauf(FAKE_HEALTH="unhealthy", NUORB_AUTO_ROLLBACK="0")
        self.assertEqual(st["state"], "failed")
        self.assertIn("--rollback", st["message"])
        self.assertEqual(len(self.aufrufe()), 1)

    def test_installer_fehler(self):
        self.anfordern({"action": "update", "release": "v0.7.4", "id": "5" * 32})
        st = self.lauf(FAKE_INSTALL_RC="1")
        self.assertEqual(st["state"], "failed")


if __name__ == "__main__":
    unittest.main()
