#!/usr/bin/env python3
"""NuOrb (Docker): Vorbereitung bei jedem Containerstart, Grundkonfiguration nur beim ersten Start.

Läuft als Benutzer hermes, bevor Oberfläche, Admin und Spracherkennung starten. Idempotent:
  * Ordner und Symlinks (Stimmen im Modell-Volume, Hermes-Cache zeigt darauf)
  * Zertifikate (eigene Heim-CA), API-Schlüssel zwischen Oberfläche und Hermes
  * nur beim ersten Start: Hermes-Grundeinstellungen (Bestätigungen, Sprache, keine Telemetrie/Update-Checks),
    LLM aus der .env (NUORB_INIT_*), ui.json mit Persona in der gewählten Sprache
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nuorb_common as jc  # noqa: E402
import personas  # noqa: E402

DATA = jc.DATA
MARK = jc.CONF / "first-run.json"
ENV = DATA / ".env"
VOICES = jc.MODELS / "voices"


def log(msg: str) -> None:
    print(f"[nuorb-init] {msg}", flush=True)


def hermes(*args: str) -> tuple[int, str]:
    p = subprocess.run(["hermes", *args], capture_output=True, text=True, timeout=180,
                       env={**os.environ, "HOME": str(DATA), "NO_COLOR": "1", "TERM": "dumb"})
    return p.returncode, (p.stdout + p.stderr)[-2000:]


def env_lines() -> list[str]:
    return ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []


def env_get(name: str) -> str:
    for line in env_lines():
        if line.split("=", 1)[0].strip() == name:
            return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def env_set(values: dict[str, str]) -> None:
    lines, seen = [], set()
    for line in env_lines():
        k = line.split("=", 1)[0].strip()
        if k in values and not line.lstrip().startswith("#"):
            lines.append(f"{k}={values[k]}")
            seen.add(k)
        else:
            lines.append(line)
    lines += [f"{k}={v}" for k, v in values.items() if k not in seen]
    tmp = ENV.with_name(".env.tmp-nuorb")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ENV)


def dirs() -> None:
    for d in (jc.CONF, jc.CERTS, jc.J / "admin", jc.J / "ctl", VOICES, jc.MODELS / "stt", DATA / "cache"):
        d.mkdir(parents=True, exist_ok=True)
    for d in (jc.J, jc.CONF, jc.CERTS, jc.J / "admin"):
        os.chmod(d, 0o700)
    link = DATA / "cache/piper-voices"
    if link.is_symlink() or not link.exists():
        if link.is_symlink() and os.readlink(link) == str(VOICES):
            return
        link.unlink(missing_ok=True)
        link.symlink_to(VOICES)
    else:
        log(f"Note: {link} is a real folder, voices from {VOICES} are not shown there.")


def api_key() -> None:
    want = {"API_SERVER_ENABLED": "true", "API_SERVER_HOST": "127.0.0.1",
            "API_SERVER_PORT": jc.env("HERMES_API_PORT", "8642")}
    if not env_get("API_SERVER_KEY"):
        want["API_SERVER_KEY"] = secrets.token_hex(32)
    if any(env_get(k) != v for k, v in want.items()):
        env_set(want)
        log("Hermes API server enabled (127.0.0.1 inside the container only).")
        restart_gateways()
    k = jc.env("NUORB_INIT_ANTHROPIC_API_KEY")
    if k and not env_get("ANTHROPIC_API_KEY"):
        env_set({"ANTHROPIC_API_KEY": k})
        log("Anthropic key taken from .env (change it in the admin panel from now on).")


def restart_gateways() -> None:
    """Falls Hermes' Gateway schon vor dieser Vorbereitung lief, liest es die neue .env erst nach einem Neustart."""
    root = Path("/run/hermes-service")
    for slot in (sorted(root.glob("*")) if root.is_dir() else []):
        if (slot / "supervise").exists():
            subprocess.run(["s6-svc", "-r", str(slot)], check=False)
            log(f"Gateway {slot.name} restarted (new .env).")


def voice_name() -> str:
    return jc.env("NUORB_VOICE") or ("en_GB-alan-medium" if jc.lang() == "en" else "de_DE-thorsten-medium")


def first_config() -> None:
    lg = jc.lang()
    sets = [
        ("approvals.mode", "manual"),
        ("updates.check", "false"),
        ("telemetry.shared_metrics.enabled", "false"),
        ("telemetry.shared_metrics.send", "false"),
        ("stt.enabled", "true"),
        ("stt.provider", "openai"),
        ("stt.openai.base_url", f"http://127.0.0.1:{jc.env('STT_ROUTER_PORT', '8178')}/v1"),
        ("stt.openai.model", "parakeet"),
        ("stt.language", lg),
        ("stt.openai.language", lg),
        ("tts.provider", "piper"),
        ("tts.piper.voice", str(VOICES / f"{voice_name()}.onnx")),
    ]
    for k, v in sets:
        code, out = hermes("config", "set", k, v)
        if code != 0:
            log(f"hermes config set {k} failed: {out[-300:]}")
    # LLM aus der .env (optional; sonst Einrichtung im Admin-Panel)
    url = jc.env("NUORB_INIT_OLLAMA_URL").rstrip("/").removesuffix("/v1")
    model = jc.env("NUORB_INIT_OLLAMA_MODEL")
    ctx = int(jc.env("NUORB_INIT_CONTEXT", "65536") or 65536)
    os.environ.setdefault("NUORB_HOME", "/opt/nuorb/home")
    sys.path.insert(0, "/opt/nuorb/admin")
    import server as adm  # nuorb-admin: dieselbe Logik wie im Panel
    path = adm.FILES["config"][0]
    if url and model:
        data = adm.load_config_rt()
        adm.cfg_set(data, "providers.lan-ollama.api", f"{url}/v1")
        adm.cfg_set(data, "providers.lan-ollama.name", "Ollama")
        adm.cfg_set(data, "providers.lan-ollama.models", {model: {"context_length": ctx}})
        for k, v in (("provider", "custom:lan-ollama"), ("base_url", f"{url}/v1"), ("default", model),
                     ("context_length", ctx), ("ollama_num_ctx", ctx)):
            adm.cfg_set(data, f"model.{k}", v)
        adm.atomic_write(path, adm.dump_rt(data))
        adm.save_brain_saved({"local": {"provider": "custom:lan-ollama", "base_url": f"{url}/v1", "default": model}})
    has_key = bool(env_get("ANTHROPIC_API_KEY"))
    mode = jc.env("NUORB_INIT_BRAIN") or ("auto" if (url and model and has_key) else "remote" if has_key else "local")
    ui = {"mode": "live", "persona": personas.PERSONA[lg], "piper_voice": voice_name(), "length_scale": 0.95,
          "features_zuhause": False, "features_geraet": False, "lang": lg}
    if (url and model) or has_key:
        try:
            ch = adm.build_brain_change(mode, jc.env("NUORB_INIT_CLAUDE_MODEL") or None, jc.env("NUORB_INIT_CLAUDE_MODEL") or None)
            adm.atomic_write(path, ch["text"])
            adm.save_brain_saved(ch["saved"])
            ui.update(ch["ui"])
            jc._write_json(jc.CONF / "setup-done.json", {"time": jc.now_iso(), "mode": mode, "via": ".env"})
            log(f"Brain from .env: {ch['desc']}")
        except Exception as exc:  # z. B. Modus ohne Schlüssel
            log(f"Brain setting from .env skipped: {getattr(exc, 'detail', exc)}")
    code, out = hermes("config", "check")
    log("hermes config check: " + ("ok" if code == 0 else out[-400:]))
    adm.atomic_write(jc.CONF / "ui.json", json.dumps(ui, indent=2, ensure_ascii=False) + "\n", 0o600)
    jc._write_json(MARK, {"time": jc.now_iso(), "lang": lg})
    log(f"Base configuration done (language {lg}, voice {voice_name()}).")


def ensure_mcp() -> None:
    """MCP-Server „nuorb“ (Name ändern, Nutzername, Kennenlernen) bei jedem Start sicherstellen."""
    os.environ.setdefault("NUORB_HOME", "/opt/nuorb/home")
    sys.path.insert(0, "/opt/nuorb/admin")
    import server as adm
    data = adm.load_config_rt()
    want = {"command": "/opt/nuorb/venv/bin/python", "args": ["-I", "/opt/nuorb/app/nuorb_mcp.py"],
            "env": {"ADMIN_URL": os.environ.get("ADMIN_URL", "https://127.0.0.1:8444"),
                    "ADMIN_TOKEN_FILE": str(jc.CONF / "internal.token")},
            "trust": "full", "timeout": 15, "tools": {"resources": False, "prompts": False}}
    cur = adm.to_plain((data.get("mcp_servers") or {}).get("nuorb") or {})
    if {k: cur.get(k) for k in want} != want:
        adm.cfg_set(data, "mcp_servers.nuorb", want)
        adm.atomic_write(adm.FILES["config"][0], adm.dump_rt(data))
        log("MCP tool \"nuorb\" (name, onboarding) registered.")


def main() -> None:
    dirs()
    jc.ensure_certs()
    api_key()
    if not MARK.exists():
        first_config()
    try:
        ensure_mcp()
    except Exception as exc:
        log(f"MCP \"nuorb\" not registered: {exc}")
    log(f"Ready. Home CA fingerprint: {jc.ca_fingerprint() or '(own certificate)'}")


if __name__ == "__main__":
    main()
