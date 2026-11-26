#!/usr/bin/env bash
# Baut die NuOrb-Website am Desktop und überträgt das Image auf den VPS. NUR MIT FREIGABE DES PROJEKTINHABERS AUSFÜHREN.
# Auf dem VPS wird nie gebaut. Der Block nuorb.loopout.tech im äußeren Caddy muss einmalig eingetragen sein
# (deploy/outer-caddy-block.caddy, NUORB_DEPLOYMENT_GUIDE.md).
# Aufruf: deploy/ausrollen.sh                    bauen, prüfen, übertragen, starten
#         deploy/ausrollen.sh --zurueck <tag>    auf ein früheres Image zurückgehen
# Voraussetzungen: Docker lokal, SSH-Alias "vps" mit Docker-Rechten, Netz "web" auf dem VPS.
set -euo pipefail
cd "$(dirname "$0")/.."
ZIEL=/opt/nuorb-site

if [[ "${1:-}" == "--zurueck" ]]; then
	TAG="${2:?Tag angeben, z. B. 2026-11-27-1030}"
	ssh vps "cd $ZIEL && docker image inspect nuorb-site:$TAG >/dev/null && echo NUORB_SITE_TAG=$TAG > .env && docker compose up -d"
	echo "Zurück auf $TAG."; exit 0
fi

[[ -z "$(git status --porcelain -- .)" ]] || { echo "website/ nicht sauber: erst committen."; exit 1; }
TAG="$(date +%Y-%m-%d-%H%M)"
export TMPDIR="$PWD/.tmp"; mkdir -p "$TMPDIR"
nice -n 19 npm ci --no-audit --no-fund
nice -n 19 npm run build          # enthält scripts/check.mjs (Datenschutz-Scan, Links, i18n, keine Fremd-Ressourcen)
nice -n 19 npm run typecheck
nice -n 19 node tools/audit.mjs   # Browser-Prüfung (Konsole, CSP, Requests, Layout)
nice -n 19 docker build --pull -t "nuorb-site:$TAG" -f deploy/Dockerfile .
docker save "nuorb-site:$TAG" | gzip -1 | ssh vps 'gunzip | docker load -q'
ssh vps "test -d $ZIEL || sudo -n install -d -o \$USER -g \$USER $ZIEL"
scp -q deploy/docker-compose.vps.yml "vps:$ZIEL/docker-compose.yml"
ssh vps "cd $ZIEL && echo NUORB_SITE_TAG=$TAG > .env && docker compose up -d && sleep 6 && docker compose ps"
echo "Ausgerollt: nuorb-site:$TAG. Prüfen: deploy/pruefe-live.sh"
