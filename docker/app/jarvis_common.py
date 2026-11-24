"""JARVIS LNX (Docker): gemeinsame Bausteine für UI- und Admin-Hülle.

- Pfade im Container
- Zertifikate (eigene Heim-CA + Server-Zertifikat, oder eigene Dateien)
- Kopplung: Einmal-Codes (Admin erzeugt), Geräte-Tokens (UI prüft)

Geheimnisse liegen nur als SHA-256 auf der Platte (Codes und Tokens), Dateien mit Modus 600.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import time
from pathlib import Path

# ------------------------------------------------------------------ Pfade
DATA = Path(os.environ.get("HERMES_HOME", "/opt/data"))          # Hermes-Daten (Volume)
J = DATA / "jarvis"                                              # alles von JARVIS LNX
CONF = J / "config"                                              # ui.json, internal.token, devices.json, pairing.json
CERTS = J / "certs"
MODELS = Path(os.environ.get("JARVIS_MODELS", "/opt/models"))    # Stimmen + STT-Modelle (Volume)
APP = Path(__file__).resolve().parent
DEVICES = CONF / "devices.json"
PAIRING = CONF / "pairing.json"

PRODUCT = "jarvis-lnx"
API_VERSION = 1
CODE_TTL = 600            # Kopplungscode: 10 Minuten, einmalig
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # ohne 0/O/1/I


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def lang() -> str:
    """Sprache: im Admin gewählt (ui.json "lang"), sonst JARVIS_LANG aus der .env."""
    v = _read_json(CONF / "ui.json", {}).get("lang") if (CONF / "ui.json").exists() else None
    if v not in ("de", "en"):
        v = "en" if env("JARVIS_LANG", "de").lower().startswith("en") else "de"
    return v


DEFAULT_VOICE = {"de": "de_DE-thorsten-medium", "en": "en_GB-alan-medium"}
# Stimmen, die der Assistent zur Auswahl anbietet (Piper, rhasspy/piper-voices); Lizenz je Stimme siehe README
VOICE_CHOICES = {
    "de": [("de_DE-thorsten-medium", "Thorsten (männlich, CC0)"), ("de_DE-thorsten-high", "Thorsten, hohe Qualität"),
           ("de_DE-kerstin-low", "Kerstin (weiblich)")],
    "en": [("en_GB-alan-medium", "Alan (British, male)"), ("en_US-ryan-high", "Ryan (US, male)"),
           ("en_US-amy-medium", "Amy (US, female)")],
}


def voice_name() -> str:
    v = _read_json(CONF / "ui.json", {}).get("piper_voice") if (CONF / "ui.json").exists() else None
    return v if isinstance(v, str) and v else (env("JARVIS_VOICE") or DEFAULT_VOICE[lang()])


MODELS_STATUS = J / "models-status.json"


def models_status() -> dict:
    return _read_json(MODELS_STATUS, {})


def set_models_status(**kw) -> None:
    d = models_status()
    d.update(kw, time=now_iso())
    _write_json(MODELS_STATUS, d)
    os.chmod(MODELS_STATUS, 0o644)


def ui_cfg() -> dict:
    return _read_json(CONF / "ui.json", {}) if (CONF / "ui.json").exists() else {}


def brand() -> str:
    """Produktname (ui.json brand_name vor BRAND_NAME), Standard NuOrb."""
    b = ui_cfg().get("brand_name")
    return (b if isinstance(b, str) and b.strip() else env("BRAND_NAME", "NuOrb") or "NuOrb").strip()[:40]


def assistant_name() -> str:
    """Name, mit dem man den Assistenten anspricht (ui.json assistant_name), Standard = Marke."""
    a = ui_cfg().get("assistant_name")
    if isinstance(a, str) and a.strip():
        return a.strip()[:40]
    return env("ASSISTANT_NAME")[:40] or brand()


def user_name() -> str:
    u = ui_cfg().get("user_name")
    return u.strip()[:40] if isinstance(u, str) else ""


def onboarded() -> bool:
    return ui_cfg().get("onboarded") is True


def server_name() -> str:
    return env("JARVIS_NAME") [:40] or assistant_name()


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _read_json(p: Path, default):
    with contextlib.suppress(FileNotFoundError, ValueError):
        return json.loads(p.read_text(encoding="utf-8"))
    return default


def _write_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{secrets.token_hex(4)}")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def allowed_nets() -> list:
    raw = env("JARVIS_ALLOWED_NETS") or "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10,fc00::/7,fe80::/10"
    return [ipaddress.ip_network(n.strip(), strict=False) for n in raw.split(",") if n.strip()]


def is_loopback(host: str | None) -> bool:
    try:
        return ipaddress.ip_address((host or "").split("%")[0]).is_loopback
    except ValueError:
        return False


# ------------------------------------------------------------------ Zertifikate
def hosts() -> list[str]:
    """Namen/IPs, unter denen der Server erreichbar ist (JARVIS_HOSTS, kommagetrennt)."""
    out = []
    for h in env("JARVIS_HOSTS").replace(" ", ",").split(","):
        h = h.strip().strip("[]")
        if h and h not in out:
            out.append(h)
    return out


def tls_mode() -> str:
    """selfsigned (Standard) | custom (eigene Dateien) | off (TLS macht ein Proxy davor, z. B. Caddy)"""
    m = env("JARVIS_TLS", "selfsigned").lower()
    return m if m in ("selfsigned", "custom", "off") else "selfsigned"


def cert_paths() -> tuple[Path, Path]:
    if tls_mode() == "custom":
        return Path(env("JARVIS_TLS_CERT", "/certs/fullchain.pem")), Path(env("JARVIS_TLS_KEY", "/certs/privkey.pem"))
    return CERTS / "server.crt", CERTS / "server.key"


def ensure_certs() -> None:
    """Heim-CA einmalig, Server-Zertifikat neu bei geänderten Namen oder < 30 Tage Restlaufzeit."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    CERTS.mkdir(parents=True, exist_ok=True)
    os.chmod(CERTS, 0o700)
    ca_key_p, ca_crt_p = CERTS / "jarvis-ca.key", CERTS / "jarvis-ca.crt"
    now = dt.datetime.now(dt.timezone.utc)

    def save_key(k, p):
        p.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
        os.chmod(p, 0o600)

    if not (ca_key_p.exists() and ca_crt_p.exists()):
        k = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"JARVIS LNX CA {secrets.token_hex(3)}"),
                          x509.NameAttribute(NameOID.ORGANIZATION_NAME, "JARVIS LNX (self-hosted)")])
        crt = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(k.public_key())
               .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=5))
               .not_valid_after(now + dt.timedelta(days=3650))
               .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
               .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(k.public_key()), critical=False)
               .sign(k, hashes.SHA256()))
        save_key(k, ca_key_p)
        ca_crt_p.write_bytes(crt.public_bytes(serialization.Encoding.PEM))
        os.chmod(ca_crt_p, 0o644)
        print(f"[jarvis] Neue Heim-CA erzeugt, Fingerabdruck {ca_fingerprint()}", flush=True)
    if tls_mode() != "selfsigned":
        return
    want = sorted(set(hosts() + ["localhost", "127.0.0.1", "jarvis"]))
    srv_crt_p, srv_key_p = CERTS / "server.crt", CERTS / "server.key"
    with contextlib.suppress(Exception):
        cur = x509.load_pem_x509_certificate(srv_crt_p.read_bytes())
        san = cur.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        have = sorted({str(v) for v in san.get_values_for_type(x509.DNSName)}
                      | {str(v) for v in san.get_values_for_type(x509.IPAddress)})
        if have == want and cur.not_valid_after_utc - now > dt.timedelta(days=30) and srv_key_p.exists():
            return
    ca_key = serialization.load_pem_private_key(ca_key_p.read_bytes(), None)
    ca_crt = x509.load_pem_x509_certificate(ca_crt_p.read_bytes())
    k = ec.generate_private_key(ec.SECP256R1())
    alt = []
    for h in want:
        try:
            alt.append(x509.IPAddress(ipaddress.ip_address(h)))
        except ValueError:
            alt.append(x509.DNSName(h))
    crt = (x509.CertificateBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, want[0] if hosts() else "jarvis")]))
           .issuer_name(ca_crt.subject).public_key(k.public_key()).serial_number(x509.random_serial_number())
           .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=825))
           .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
           .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
           .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
           .add_extension(x509.SubjectAlternativeName(alt), critical=False)
           .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
           .sign(ca_key, hashes.SHA256()))
    save_key(k, srv_key_p)
    srv_crt_p.write_bytes(crt.public_bytes(serialization.Encoding.PEM))
    os.chmod(srv_crt_p, 0o644)
    print(f"[jarvis] Server-Zertifikat für {', '.join(want)} erzeugt (825 Tage).", flush=True)


def ca_fingerprint() -> str:
    """SHA-256 über das CA-Zertifikat (DER), 64 Hex-Zeichen groß. Leer, wenn keine eigene CA im Spiel ist."""
    if tls_mode() != "selfsigned":
        return ""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    try:
        crt = x509.load_pem_x509_certificate((CERTS / "jarvis-ca.crt").read_bytes())
    except OSError:
        return ""
    return hashlib.sha256(crt.public_bytes(serialization.Encoding.DER)).hexdigest().upper()


def cert_names() -> list[str]:
    from cryptography import x509
    try:
        crt = x509.load_pem_x509_certificate(cert_paths()[0].read_bytes())
        san = crt.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        return [str(v) for v in san.get_values_for_type(x509.DNSName)] + \
               [str(v) for v in san.get_values_for_type(x509.IPAddress)]
    except Exception:
        return []


def ssl_kwargs() -> dict:
    if tls_mode() == "off":
        return {}
    c, k = cert_paths()
    return {"ssl_certfile": str(c), "ssl_keyfile": str(k)}


# ------------------------------------------------------------------ Kopplung
def _norm_code(c: str) -> str:
    return "".join(ch for ch in str(c).upper() if ch in CODE_ALPHABET)


def new_pairing_code(created_by: str) -> dict:
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    data = {k: v for k, v in _read_json(PAIRING, {}).items() if v.get("exp", 0) > time.time()}
    exp = time.time() + CODE_TTL
    data[_sha(code)] = {"exp": exp, "by": created_by[:40], "created": now_iso()}
    _write_json(PAIRING, data)
    return {"code": f"{code[:4]}-{code[4:]}", "expires": int(exp), "ttl": CODE_TTL}


def redeem_pairing_code(code: str) -> bool:
    c = _norm_code(code)
    if len(c) != 8:
        return False
    data = _read_json(PAIRING, {})
    h = _sha(c)
    hit = None
    for k, v in data.items():
        if hmac.compare_digest(k, h) and v.get("exp", 0) > time.time():
            hit = k
    if not hit:
        return False
    data.pop(hit, None)  # einmalig
    _write_json(PAIRING, {k: v for k, v in data.items() if v.get("exp", 0) > time.time()})
    return True


def devices() -> dict:
    return _read_json(DEVICES, {})


def add_device(name: str, platform: str, ip: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    did = "d_" + secrets.token_hex(6)
    d = devices()
    d[did] = {"name": (name or "Gerät")[:60], "platform": (platform or "unbekannt")[:20], "token": _sha(token),
              "created": now_iso(), "last_seen": now_iso(), "ip": ip}
    _write_json(DEVICES, d)
    return did, token


_seen_cache: dict[str, float] = {}


def device_for_token(token: str, ip: str = "") -> str | None:
    if not token or len(token) > 200:
        return None
    h = _sha(token)
    d = devices()
    for did, v in d.items():
        if hmac.compare_digest(v.get("token", ""), h):
            if time.time() - _seen_cache.get(did, 0) > 300:  # „zuletzt gesehen“ höchstens alle 5 min schreiben
                _seen_cache[did] = time.time()
                v["last_seen"], v["ip"] = now_iso(), ip
                _write_json(DEVICES, d)
            return did
    return None


def revoke_device(did: str) -> bool:
    d = devices()
    if did in d:
        d.pop(did)
        _write_json(DEVICES, d)
        return True
    return False


def pairing_required() -> bool:
    return env("JARVIS_REQUIRE_PAIRING", "1") != "0"
