# Security policy

NuOrb runs in your home network and controls a language model with tools, so security reports are very welcome.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private reporting instead:

1. Open the [Security tab](https://github.com/Anarki-LNX/nuorb/security) of this repository.
2. Choose **Report a vulnerability** and describe the problem, how to reproduce it and which version you used.

Only the maintainer sees the report. You get an answer within a few days. Once a fix is released, the advisory is published, and you are credited if you like.

## Supported versions

Security fixes go into the **newest release** only. Please update before reporting, the one-liner always installs the newest release:

```bash
curl -fsSL https://github.com/Anarki-LNX/nuorb/releases/latest/download/install.sh | bash
```

## What NuOrb already does

- The admin panel needs a password (scrypt), sessions are stored as hashes, cookies are HttpOnly, Secure and SameSite=Strict.
- Phones and browsers pair with a one-time code. The server refuses write requests from foreign web pages and unknown host names.
- Both servers answer only from home network addresses by default. This is an extra layer, password and pairing protect on their own.
- Every change in the admin panel is shown as a preview, backed up and can be undone. Secrets are hidden in previews and exports.
- The language model gets only the tools a voice assistant needs. Shell, files and browser are off unless switched on in the admin panel. After it has read outside content (web search, web page, file), every action with an effect needs a confirmation, checked by a rule outside the model.
- Installer, Proxmox script and template load only from a release and check every file against `SHA256SUMS`. Speech models are checked against stored checksums.
- From v0.7.2 every release and image is attested by GitHub (build provenance). The installer checks the attestation of `SHA256SUMS` when the GitHub CLI is logged in, `NUORB_REQUIRE_ATTESTATION=1` makes it mandatory. Before an update the installer saves settings and data, `--rollback` goes back.
- Python packages are installed only with their pinned hashes. Every release is scanned (pip-audit, Grype) and ships an SBOM.
- No telemetry.

## Please do not

- open ports 8443 or 8444 to the internet. Use a VPN when you are away.
- test against installations that are not your own.

---

# Sicherheitsrichtlinie (Deutsch)

Sicherheitsmeldungen sind sehr willkommen. Bitte **kein öffentliches Issue** öffnen, sondern im Reiter [Security](https://github.com/Anarki-LNX/nuorb/security) auf **Report a vulnerability** gehen und Problem, Nachvollziehbarkeit und Version beschreiben. Nur der Maintainer sieht die Meldung, die Antwort kommt innerhalb weniger Tage. Korrekturen gibt es für das **neueste Release**. Die Ports 8443 und 8444 bitte nie ins Internet freigeben, unterwegs ein VPN nutzen.
