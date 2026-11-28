"""install.sh lädt nur aus einem Release und prüft gegen SHA256SUMS (audit P1.2). Mit einem nachgebauten Release-Server
auf 127.0.0.1 (latest leitet auf das Tag um, wie bei GitHub)."""
from __future__ import annotations

import hashlib
import http.server
import os
import subprocess
import threading
import unittest
from pathlib import Path

from _lade import DOCKER, temp_ordner

INSTALL = next(p for p in (DOCKER / "install.sh", DOCKER.parent / "install.sh") if p.is_file())
T = temp_ordner("release")
DATEIEN = {"compose.yaml": "name: nuorb\n", "env.example": "NUORB_HOSTS=\n", "README.md": "# NuOrb\n",
           "install.sh": "#!/bin/sh\necho install\n", "ct-setup.sh": "#!/bin/sh\necho ct\n"}
PROXMOX = next((p for p in (DOCKER.parent / "proxmox",) if (p / "ct-setup.sh").is_file()), None)


def release_anlegen(tag: str, kaputt: str | None = None) -> None:
    d = T / "srv" / "download" / tag
    d.mkdir(parents=True, exist_ok=True)
    sums = []
    for name, inhalt in DATEIEN.items():
        sums.append(f"{hashlib.sha256(inhalt.encode()).hexdigest()}  {name}")
        (d / name).write_text(inhalt + ("manipuliert\n" if name == kaputt else ""))
    (d / "SHA256SUMS").write_text("\n".join(sums) + "\n")


class Handler(http.server.SimpleHTTPRequestHandler):
    latest = "v9.9.9"

    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(T / "srv"), **k)

    def do_GET(self):  # noqa: N802
        if self.path == "/latest":
            self.send_response(302)
            self.send_header("Location", f"/tag/{self.latest}")
            self.end_headers()
        elif self.path.startswith("/tag/"):
            self.send_response(200)
            self.end_headers()
        else:
            super().do_GET()

    do_HEAD = do_GET

    def log_message(self, *a):
        pass


class ReleaseDateien(unittest.TestCase):
    base: str
    httpd: http.server.ThreadingHTTPServer

    @classmethod
    def setUpClass(cls):
        release_anlegen("v9.9.9")
        release_anlegen("v9.9.8")
        release_anlegen("v9.9.7", kaputt="compose.yaml")
        cls.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def holen(self, ziel: Path, *args: str) -> subprocess.CompletedProcess:
        skript = 'INST="$1"; ZIEL="$2"; PIN="${3:-}"; set --; NUORB_LIB_ONLY=1; . "$INST"; DIR="$ZIEL"; ' \
                 '[ -n "$PIN" ] && RELEASE="$PIN"; fetch_files; echo "RELEASE=$RELEASE"'
        env = {**os.environ, "NUORB_DL_BASE": self.base, "HOME": str(T), "LANG": "C.UTF-8"}
        pin = args[1] if len(args) > 1 and args[0] == "--release" else ""
        return subprocess.run(["bash", "-c", skript, "_", str(INSTALL), str(ziel), pin], env=env,
                              capture_output=True, text=True, timeout=60)

    def test_neuestes_release_mit_pruefsummen(self):
        ziel = T / "inst1"
        r = self.holen(ziel)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("RELEASE=v9.9.9", r.stdout)
        self.assertEqual((ziel / "compose.yaml").read_text(), DATEIEN["compose.yaml"])
        self.assertEqual((ziel / ".env.example").read_text(), DATEIEN["env.example"])

    def test_festes_release(self):
        r = self.holen(T / "inst2", "--release", "v9.9.8")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("RELEASE=v9.9.8", r.stdout)

    def test_manipulierte_datei_bricht_ab(self):
        ziel = T / "inst3"
        r = self.holen(ziel, "--release", "v9.9.7")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SHA256SUMS", r.stderr + r.stdout)
        self.assertFalse((ziel / "compose.yaml").exists())
        self.assertFalse((ziel / "compose.yaml.tmp").exists())

    def test_unbekanntes_release_bricht_ab(self):
        r = self.holen(T / "inst4", "--release", "v0.0.1")
        self.assertNotEqual(r.returncode, 0)

    def bash(self, skript: str, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "NUORB_DL_BASE": self.base, "HOME": str(T), "LANG": "C.UTF-8"}
        return subprocess.run(["bash", "-c", skript, "_", *args], env=env, capture_output=True, text=True, timeout=60)

    @unittest.skipUnless(PROXMOX, "proxmox/ nur im öffentlichen Repo")
    def test_proxmox_container_helfer(self):
        """ct-setup.sh schreibt /usr/local/lib/nuorb/release.sh für update und den ersten Start."""
        assert PROXMOX is not None
        text = (PROXMOX / "ct-setup.sh").read_text()
        a = text.index("cat > /usr/local/lib/nuorb/release.sh <<'EOF'\n") + len("cat > /usr/local/lib/nuorb/release.sh <<'EOF'\n")
        helfer = T / "release.sh"
        helfer.write_text(text[a:text.index("\nEOF\n", a)] + "\n")
        ok = self.bash('. "$1"; t=$(nuorb_release_latest); echo "TAG=$t"; nuorb_fetch_install "$t" "$2" && cat "$2"', str(helfer), str(T / "i1.sh"))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("TAG=v9.9.9", ok.stdout)
        self.assertIn("echo install", ok.stdout)
        release_anlegen("v9.9.6", kaputt="install.sh")
        boese = self.bash('. "$1"; nuorb_fetch_install v9.9.6 "$2"', str(helfer), str(T / "i2.sh"))
        self.assertNotEqual(boese.returncode, 0)
        self.assertFalse((T / "i2.sh").exists())

    @unittest.skipUnless(PROXMOX, "proxmox/ nur im öffentlichen Repo")
    def test_proxmox_host_skript(self):
        assert PROXMOX is not None
        skript = 'set --; NUORB_LIB_ONLY=1; . "$0"; RELEASE=$REL; release_file ct-setup.sh "$ZIEL" && cat "$ZIEL"'
        env = {**os.environ, "NUORB_DL_BASE": self.base, "HOME": str(T), "LANG": "C.UTF-8", "ZIEL": str(T / "ct1.sh"), "REL": "v9.9.9"}
        ok = subprocess.run(["bash", "-c", skript, str(PROXMOX / "nuorb-lxc.sh")], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("echo ct", ok.stdout)
        release_anlegen("v9.9.5", kaputt="ct-setup.sh")
        env.update(ZIEL=str(T / "ct2.sh"), REL="v9.9.5")
        boese = subprocess.run(["bash", "-c", skript, str(PROXMOX / "nuorb-lxc.sh")], env=env, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(boese.returncode, 0)
        self.assertFalse((T / "ct2.sh").exists())

    def test_skript_laedt_nichts_vom_branch(self):
        text = INSTALL.read_text()
        self.assertNotIn("raw.githubusercontent.com", text)
        self.assertNotIn("/main/", text)


if __name__ == "__main__":
    unittest.main()
