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

    def alt_pruefen(self, env_text: str) -> subprocess.CompletedProcess:
        d = T / f"alt-{abs(hash(env_text))}"
        d.mkdir(exist_ok=True)
        (d / ".env").write_text(env_text)
        skript = 'INST="$1"; D="$2"; set --; NUORB_LIB_ONLY=1; . "$INST"; DIR="$D"; old_install_check; echo WEITER'
        return self.bash(skript, str(INSTALL), str(d))

    def test_installation_von_vor_070_wird_angehalten(self):
        r = self.alt_pruefen("ALT_HOSTS=192.168.1.50\nALT_LANG=de\nTZ=Europe/Berlin\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("WEITER", r.stdout)
        self.assertIn("nuorb-umzug-0.7.0.sh", r.stderr + r.stdout)

    def test_neue_installation_laeuft_weiter(self):
        for text in ("NUORB_HOSTS=192.168.1.50\nNUORB_LANG=de\n", "TZ=Europe/Berlin\n"):
            with self.subTest(text=text):
                r = self.alt_pruefen(text)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("WEITER", r.stdout)

    def ohne_docker_path(self) -> str:
        """PATH mit allen Programmen aus /usr/bin außer docker und den Proxmox-Werkzeugen: beide Skripte halten so
        an derselben Stelle an, ohne etwas zu installieren."""
        d = T / "bin-ohne-docker"
        if not d.exists():
            d.mkdir()
            for p in Path("/usr/bin").iterdir():
                if not (p.name.startswith("docker") or p.name in ("pct", "pveam", "pvesm", "pvesh", "pveversion")):
                    (d / p.name).symlink_to(p)
        return str(d)

    def gleiches_ergebnis(self, datei: Path, name: str, args: list[str]):
        tag = "v9.9.4"
        z = T / "srv" / "download" / tag
        z.mkdir(parents=True, exist_ok=True)
        text = datei.read_text()
        self.assertIn('\nNUORB_RELEASE=""\n', text)
        (z / name).write_text(text.replace('\nNUORB_RELEASE=""\n', f'\nNUORB_RELEASE="{tag}"\n', 1))
        (z / "SHA256SUMS").write_text(f"{hashlib.sha256((z / name).read_bytes()).hexdigest()}  {name}\n")
        alt = T / f"main-{name}"     # wie vom Branch main geladen: ohne Tag, nicht in einem Checkout
        alt.write_text(text)
        env = {**os.environ, "NUORB_DL_BASE": self.base, "HOME": str(T), "LANG": "C.UTF-8", "TMPDIR": str(T),
               "PATH": self.ohne_docker_path()}
        vorher, Handler.latest = Handler.latest, tag
        try:
            a = subprocess.run(["bash", str(alt), *args], env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
            b = subprocess.run(["bash", str(z / name), *args], env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        finally:
            Handler.latest = vorher
        self.assertEqual(a.returncode, b.returncode, a.stderr + b.stderr)
        self.assertTrue((a.stdout + a.stderr).endswith(b.stdout + b.stderr) or b.stderr.strip() in a.stderr, (a.stdout, a.stderr, b.stdout, b.stderr))
        self.assertTrue(b.stderr.strip() or b.stdout.strip(), "das Skript hat etwas ausgegeben")
        return a, b

    def test_alter_einzeiler_install_sh(self):
        a, b = self.gleiches_ergebnis(INSTALL, "install.sh", ["--yes", "--lang", "de", "--dir", str(T / "nie")])
        self.assertIn("v9.9.4", a.stdout + a.stderr)
        self.assertIn("Docker", b.stderr)
        self.assertFalse((T / "nie").exists())

    @unittest.skipUnless(PROXMOX, "proxmox/ nur im öffentlichen Repo")
    def test_alter_einzeiler_nuorb_lxc(self):
        assert PROXMOX is not None
        a, b = self.gleiches_ergebnis(PROXMOX / "nuorb-lxc.sh", "nuorb-lxc.sh", ["--yes", "--lang", "de"])
        self.assertIn("root", b.stderr)

    def test_skript_laedt_nichts_vom_branch(self):
        text = INSTALL.read_text()
        self.assertNotIn("raw.githubusercontent.com", text)
        self.assertNotIn("/main/", text)


if __name__ == "__main__":
    unittest.main()


# Härtung 2, Phase 6: Sicherung vor dem Update und Rückkehr (install.sh --rollback). docker ist ein Stellvertreter,
# der jeden Aufruf protokolliert; „run“ legt die Sicherungsdatei an bzw. merkt sich die Wiederherstellung.
FAKE_DOCKER = r'''#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
case "$*" in
  *"config --images"*) echo "ghcr.io/anarki-lnx/nuorb:$(sed -n 's/^NUORB_VERSION=//p' .env 2>/dev/null | tail -1)" ;;
  *"ps -q"*) echo abc123 ;;
  "run "*)
    for a in "$@"; do case "$a" in *:/b|*:/b:ro) B="${a%%:/b*}" ;; esac; done
    case "$*" in *"tar czf"*) echo daten > "$B/data.tar.gz" ;; *"tar xzf"*) echo "RESTORE $B" >> "$FAKE_LOG" ;; esac ;;
esac
exit 0
'''


class SicherungUndRueckkehr(unittest.TestCase):
    def setUp(self):
        self.d = Path(temp_ordner("update"))
        self.log = self.d / "docker.log"
        fake = self.d / "docker"
        fake.write_text(FAKE_DOCKER)
        fake.chmod(0o755)
        (self.d / ".env").write_text("NUORB_VERSION=0.7.1\nNUORB_LANG=de\n")
        (self.d / "compose.yaml").write_text("name: nuorb\n# 0.7.1\n")

    def lauf(self, befehle: str) -> subprocess.CompletedProcess:
        skript = (f'set --; NUORB_LIB_ONLY=1; . "{INSTALL}"; DIR="{self.d}"; DOCKER=("{self.d}/docker"); YES=1; '
                  f'cd "{self.d}"; {befehle}')
        env = {**os.environ, "FAKE_LOG": str(self.log), "HOME": str(self.d), "LANG": "C.UTF-8"}
        return subprocess.run(["bash", "-c", skript], env=env, capture_output=True, text=True, timeout=60)

    def test_erstinstallation_sichert_nichts(self):
        (self.d / ".env").unlink()
        r = self.lauf("backup_before_update; echo FERTIG")
        self.assertIn("FERTIG", r.stdout, r.stderr)
        self.assertFalse((self.d / "backups").exists())

    def test_update_sichert_einstellungen_und_daten(self):
        r = self.lauf("backup_before_update")
        self.assertEqual(r.returncode, 0, r.stderr)
        (b,) = list((self.d / "backups").iterdir())
        self.assertTrue(b.name.endswith("-0.7.1"))
        for f in (".env", "compose.yaml", "data.tar.gz"):
            self.assertTrue((b / f).is_file(), f)
        self.assertEqual((self.d / "backups").stat().st_mode & 0o077, 0, "Sicherung nur für den Besitzer")
        log = self.log.read_text()
        self.assertIn("stop nuorb", log)
        self.assertIn("start nuorb", log)   # NuOrb läuft weiter, bis das Update wirklich startet
        self.assertIn("backup", (self.d / "update.log").read_text())

    def test_hoechstens_fuenf_sicherungen(self):
        for i in range(7):
            (self.d / "backups" / f"20260101-00000{i}-0.6.{i}").mkdir(parents=True)
        self.lauf("backup_before_update")
        self.assertEqual(len(list((self.d / "backups").iterdir())), 5)

    def test_rueckkehr_stellt_alte_version_und_daten_her(self):
        self.lauf("backup_before_update")
        (self.d / ".env").write_text("NUORB_VERSION=0.7.2\nNUORB_LANG=de\n")   # das Update
        (self.d / "compose.yaml").write_text("name: nuorb\n# 0.7.2\n")
        r = self.lauf("rollback")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("NUORB_VERSION=0.7.1", (self.d / ".env").read_text())
        self.assertIn("# 0.7.1", (self.d / "compose.yaml").read_text())
        log = self.log.read_text()
        self.assertIn("RESTORE", log)
        self.assertIn("up -d", log)
        self.assertIn("rollback", (self.d / "update.log").read_text())

    def test_rueckkehr_ohne_sicherung_bricht_ab(self):
        r = self.lauf("rollback")
        self.assertNotEqual(r.returncode, 0)


class Attestierung(unittest.TestCase):
    """verify_sums: ab v0.7.2 mit angemeldeter GitHub-CLI Pflicht, sonst SHA256SUMS wie bisher."""

    def lauf(self, release: str, gh: str | None, require: str = "") -> subprocess.CompletedProcess:
        d = Path(temp_ordner("attest"))
        (d / "sums").write_text("x  install.sh\n")
        g = d / "bin" / "gh"   # Stellvertreter: gh=None heißt „nicht angemeldet“
        g.parent.mkdir()
        auth = "1" if gh is None else "0"
        g.write_text(f"#!/bin/sh\ncase \"$1\" in auth) exit {auth} ;; attestation) exit {gh or 1} ;; esac\nexit 0\n")
        g.chmod(0o755)
        path = f"{g.parent}:{os.environ.get('PATH', '')}"
        skript = f'set --; NUORB_LIB_ONLY=1; . "{INSTALL}"; RELEASE={release}; verify_sums "{d}/sums"; echo WEITER'
        env = {**os.environ, "PATH": path, "LANG": "C.UTF-8", "NUORB_REQUIRE_ATTESTATION": require}
        return subprocess.run(["bash", "-c", skript], env=env, capture_output=True, text=True, timeout=30)

    def test_gueltige_attestierung(self):
        self.assertIn("WEITER", self.lauf("v0.7.2", "0").stdout)

    def test_falsche_attestierung_bricht_ab(self):
        r = self.lauf("v0.7.2", "1")
        self.assertNotIn("WEITER", r.stdout)
        self.assertNotEqual(r.returncode, 0)

    def test_aeltere_releases_ohne_attestierung(self):
        self.assertIn("WEITER", self.lauf("v0.7.1", "1").stdout)

    def test_ohne_gh_wie_bisher_ausser_pflicht(self):
        self.assertIn("WEITER", self.lauf("v0.7.2", None).stdout)
        self.assertNotIn("WEITER", self.lauf("v0.7.2", None, "1").stdout)
