"""Konsistenz der Quelle im öffentlichen Repo (v0.7.2, Phase 1).

docker/src ist für alle außer dem Maintainer die Quelle (SOURCES.md). Diese Tests prüfen, dass docker/src und
docker/app vollständig und in sich stimmig sind, ohne die private Arbeitskopie zu brauchen:
- jede Datei, die Startskripte und Docker-Einstieg unter /opt/nuorb erwarten, ist da,
- jede Datei, die die Seiten von Oberfläche und Admin-Panel laden, ist da,
- jede Original-Route, die docker/app umhüllt, gibt es in docker/src,
- jede Python-Datei lässt sich übersetzen,
- keine privaten Muster (gleiche generische Liste wie docker/tools/prepare-src.py).
Ob docker/src genau aus der privaten Quelle erzeugt ist, prüft der Maintainer vorher mit `prepare-src.py --check`.
"""
from __future__ import annotations

import py_compile
import re
import unittest

from _lade import APP, DOCKER, SRC

# Pfade im Image -> Ordner im Repo (Dockerfile, COPY-Zeilen)
IMAGE = {"/opt/nuorb/ui/": SRC / "ui", "/opt/nuorb/admin/": SRC / "admin", "/opt/nuorb/stt/": SRC / "stt",
         "/opt/nuorb/smarthome/": SRC / "smarthome", "/opt/nuorb/app/": APP}
PRIVAT = [r"\b192\.168\.(?!1\.50\b)\d+\.\d+\b(?!/)", r"\b10\.\d+\.\d+\.\d+\b(?!/)", r"sk-ant-[A-Za-z0-9]", r"id_ed25519\w*",
          r"-----BEGIN [A-Z ]*PRIVATE KEY"]


def text_files(*roots):
    for root in roots:
        for p in sorted(root.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".woff2", ".png", ".ico", ".tflite", ".onnx"):
                yield p


class Quelle(unittest.TestCase):
    def test_dockerfile_kopiert_nur_vorhandenes(self):
        df = (DOCKER / "Dockerfile").read_text(encoding="utf-8")
        for src in re.findall(r"^COPY\s+(?!--)(\S+)\s", df, re.M):
            self.assertTrue((DOCKER / src).exists(), f"Dockerfile kopiert {src}, gibt es nicht")

    def test_startskripte_finden_ihre_dateien(self):
        roots = [DOCKER / "rootfs", APP]
        fehlt = []
        for p in text_files(*roots):
            for ref in set(re.findall(r"/opt/nuorb/(?:ui|admin|stt|smarthome|app)/[\w./-]+\.(?:py|md|json)", p.read_text(errors="ignore"))):
                pre = next(k for k in IMAGE if ref.startswith(k))
                if not (IMAGE[pre] / ref[len(pre):]).exists():
                    fehlt.append(f"{p.relative_to(DOCKER)} -> {ref}")
        self.assertEqual(fehlt, [])

    def test_seiten_laden_nur_vorhandene_dateien(self):
        fehlt = []
        ui_static, adm_static = SRC / "ui/static", SRC / "admin/static"
        for page, base in ((ui_static / "index.html", ui_static), (adm_static / "index.html", adm_static),
                           *((p, APP / "pages") for p in sorted((APP / "pages").glob("*.html")))):
            for ref in re.findall(r'(?:src|href)="([^"#?]+)', page.read_text(encoding="utf-8")):
                if re.match(r"^(https?:|mailto:|data:)", ref) or ref == "/":
                    continue
                if ref.startswith("/ui/"):
                    target = ui_static / ref[4:]
                elif ref.startswith("/static/docker/"):
                    target = APP / "pages" / ref[15:]
                elif ref.startswith("/static/"):
                    target = adm_static / ref[8:]
                elif ref.startswith("/"):
                    continue   # Server-Routen (z. B. /favicon.ico) prüft die e2e
                else:
                    target = base / ref
                if not target.exists():
                    fehlt.append(f"{page.relative_to(DOCKER)} -> {ref}")
        self.assertEqual(fehlt, [])

    def test_umhuellte_routen_gibt_es_in_der_quelle(self):
        for entry, server in (("ui_main.py", SRC / "ui/server.py"), ("admin_main.py", SRC / "admin/server.py")):
            code = (APP / entry).read_text(encoding="utf-8")
            src = server.read_text(encoding="utf-8")
            for path, method in re.findall(r'original_endpoint\(app, "([^"]+)"(?:, "([A-Z]+)")?\)', code):
                method = (method or "GET").lower()
                self.assertRegex(src, rf'@app\.{method}\("{re.escape(path)}"', f"{entry}: {method.upper()} {path} fehlt in {server.name}")

    def test_python_uebersetzt(self):
        for p in [*SRC.rglob("*.py"), *APP.glob("*.py")]:
            py_compile.compile(str(p), doraise=True, cfile=str(DOCKER / ".pytest_cache" / "pyc" / (p.name + "c")))

    def test_keine_privaten_muster(self):
        funde = []
        for p in text_files(SRC, APP):
            text = p.read_text(encoding="utf-8", errors="ignore")
            for muster in PRIVAT:
                for m in re.finditer(muster, text, re.I):
                    funde.append(f"{p.relative_to(DOCKER)}: {m.group(0)}")
        self.assertEqual(funde, [])


class GetrennteBenutzerInit(unittest.TestCase):
    """v0.7.4: nuorb-init setzt Besitz und Rechte vor und nach first_run, first_run läuft als nuorb mit den Fähigkeiten des
    Admin-Panels. Das Verhalten prüft der Image-Lauf (.work/separation-check.sh), hier nur die Schritte."""

    def setUp(self):
        self.init = (DOCKER / "rootfs/opt/nuorb/bin/nuorb-init").read_text(encoding="utf-8")

    def test_rechte_vor_und_nach_first_run(self):
        fr = self.init.index("first_run.py")
        self.assertIn("\nperms\n", self.init[:fr])
        self.assertIn("\nperms\n", self.init[fr:])

    def test_first_run_als_nuorb_ohne_root(self):
        self.assertIn('setpriv --reuid="$NU" --regid="$NU" --init-groups --inh-caps="$CAPS" --ambient-caps="$CAPS"', self.init)
        self.assertIn("CAPS=+chown,+dac_override,+fowner", self.init)

    def test_bereich_von_hermes_zurueck_an_hermes(self):
        self.assertRegex(self.init, r'-path /opt/data/installs -o -path /opt/data/cache \\\) -prune -o -user "\$NU"')

    def test_update_anforderungen_nur_nuorb(self):
        self.assertIn('chown "$NU:$NU" /opt/nuorb/control/request', self.init)


class ComposeHaertung(unittest.TestCase):
    """Phase 2: Härtung des Containers in compose.yaml bleibt erhalten (gemessen und getestet im e2e-Lauf)."""

    def setUp(self):
        from ruamel.yaml import YAML
        self.svc = YAML(typ="safe").load((DOCKER / "compose.yaml").read_text(encoding="utf-8"))["services"]["nuorb"]

    def test_rechte(self):
        self.assertIn("no-new-privileges:true", self.svc["security_opt"])
        self.assertEqual(self.svc["cap_drop"], ["ALL"])
        self.assertEqual(sorted(self.svc["cap_add"]), ["CHOWN", "DAC_OVERRIDE", "DAC_READ_SEARCH", "FOWNER", "KILL", "SETGID", "SETUID"])
        self.assertNotIn("privileged", self.svc)

    def test_schreibschutz_und_grenzen(self):
        self.assertIs(self.svc["read_only"], True)
        self.assertEqual(sorted(t.split(":")[0] for t in self.svc["tmpfs"]), ["/run", "/tmp", "/var/tmp"])
        self.assertLessEqual(self.svc["pids_limit"], 4096)
        self.assertIn("mem_limit", self.svc)

    def test_keine_host_mounts_und_kein_docker_socket(self):
        for v in self.svc.get("volumes", []):
            src = str(v).split(":")[0]
            if src == "./control":   # einziger Host-Ordner: Austausch mit der Update-Hilfe (v0.7.3)
                self.assertEqual(str(v), "./control:/opt/nuorb/control")
                continue
            self.assertIn(src, ("data", "models"), f"Host-Mount {v}")
            self.assertNotIn("docker.sock", str(v))
        self.assertNotIn("network_mode", self.svc)


if __name__ == "__main__":
    unittest.main()
