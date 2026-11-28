# Where the code lives

NuOrb started as a private project on one PC and a phone. This page says which folder in this repository holds which
part, which copy counts, and where to make a change.

## The server (Docker image)

| Folder | What is in it | Change it here? |
|---|---|---|
| `docker/src/ui/` | voice UI: FastAPI server (`server.py`) and the web interface (`static/`) | yes |
| `docker/src/admin/` | admin panel: server and web interface | yes |
| `docker/src/stt/` | speech-to-text router (OpenAI-compatible endpoint for Hermes) | yes |
| `docker/src/smarthome/` | Home Assistant and ioBroker tools (MCP server and skill) | yes |
| `docker/app/` | container start, first-run setup, shared helpers, settings pages that only exist in Docker | yes |
| `docker/tests/` | unit tests for `docker/src` and `docker/app` | yes |
| `docker/rootfs/`, `Dockerfile`, `compose*.yaml` | image layout and start files | yes |

**`docker/src` is the source for everyone outside the maintainer's PC.** Pull requests change it directly.

The maintainer keeps a private working copy of `ui`, `admin` and the STT router. It holds the same code with the
maintainer's own addresses and names. `docker/tools/prepare-src.py` copies that working copy into `docker/src`
and replaces every private value with a neutral placeholder. A check stops the script if anything private is left.
The rules for the private values are in a file that is never published, so the script cannot be run from this
repository, and it does not need to be. Changes from pull requests are carried back into the private working copy
by hand before the next run.

Two checks keep both sides in step. Before every commit to `docker/src` the maintainer runs
`prepare-src.py --check`, which builds `docker/src` from the working copy into a scratch folder and fails if the
committed folder differs. In this repository `docker/tests/test_source.py` runs in CI: every file the Dockerfile,
the start scripts and the pages refer to must exist, every route the image wraps must exist in `docker/src`, all
Python code must compile, and no private address or key may appear.

## Everything else

| Folder | What is in it |
|---|---|
| `install.sh`, `proxmox/` | installer and Proxmox LXC installer, template build |
| `nixos/` | NixOS configuration for the phone build (Xiaomi Mi 11 Lite 4G) |
| `scripts/` | helper scripts from the phone and the old LXC build |
| `voice/` | recording tools and sentence corpus for an own voice |
| `website/` | the project website, takes the orb and fonts from `docker/src/ui/static` |

## Removed in v0.7.1

Up to v0.7.0 the repository root also had `ui/` and `admin/` with deploy scripts and systemd units for the old
manual LXC setup without Docker, plus a copy of the STT router in `scripts/`. These were outdated copies of the code
that is now in `docker/src` (about 1,800 lines of changes behind). They were removed to have one source only. The old
files are still in the [v0.7.0 tag](https://github.com/Anarki-LNX/nuorb/tree/v0.7.0).

---

**Deutsch:** Der Server-Code steht in `docker/src` (Oberfläche, Admin-Panel, STT-Router, Smart Home) und
`docker/app` (Start, Einrichtung, Hilfen). Dort werden Änderungen gemacht, auch in Pull Requests. Der Maintainer
pflegt eine private Arbeitskopie mit eigenen Adressen. `docker/tools/prepare-src.py` überträgt sie nach `docker/src`
und ersetzt dabei alles Private durch Platzhalter. Die alten Kopien `ui/` und `admin/` im Wurzelverzeichnis sind seit
v0.7.1 entfernt und im Tag v0.7.0 noch zu finden.
