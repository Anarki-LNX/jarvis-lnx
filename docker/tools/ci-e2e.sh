#!/usr/bin/env bash
# End-to-End-Test in der CI (GitHub Actions) und lokal: Image bauen, Testcontainer mit compose.test.yaml und dem
# Mock-LLM starten, e2e-test.py laufen lassen, danach alles stoppen und die Testvolumes löschen.
#   docker/tools/ci-e2e.sh            (aus der Repo-Wurzel oder aus docker/)
# Braucht Docker mit Compose v2 und Python 3. Lädt beim ersten Start die Sprachmodelle (~530 MB).
set -Eeuo pipefail
cd "$(dirname "$0")/.."
P=nuorb-ci
C=(docker compose -p "$P" -f compose.yaml -f compose.test.yaml)
mkdir -p .work
cleanup() {
  local rc=$?
  [ "$rc" = 0 ] || "${C[@]}" logs --tail 80 nuorb 2>/dev/null | tail -80 || true
  [ -n "${MOCK:-}" ] && kill "$MOCK" 2>/dev/null
  if [ "${NUORB_CI_KEEP_VOLUMES:-0}" = 1 ]; then "${C[@]}" down >/dev/null 2>&1 || true   # lokal: Modelle behalten
  else "${C[@]}" down -v >/dev/null 2>&1 || true; fi
  exit "$rc"
}
trap cleanup EXIT

python3 tools/mock-llm.py 18434 > .work/ci-mock.log 2>&1 & MOCK=$!
"${C[@]}" build --build-arg NUORB_BUILD="${NUORB_BUILD:-ci}"
"${C[@]}" up -d
echo "Warte auf den Container"
for _ in $(seq 1 180); do
  curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:19444/api/auth/state 2>/dev/null | grep -q 200 && break
  sleep 2
done
# Modelle laden beim ersten Start; e2e-test.py prüft Sprache, also warten bis sie da sind
for _ in $(seq 1 300); do
  docker exec nuorb-test cat /opt/data/nuorb/models-status.json 2>/dev/null | grep -q '"state": *"ready"' && break
  sleep 2
done
CODE=$(docker exec nuorb-test cat /opt/data/nuorb/admin/setup-code.txt | tr -d '[:space:]')
PW=$(python3 -c 'import secrets; print("Ci-" + secrets.token_urlsafe(18))')
E2E_PASSWORD="$PW" python3 tools/e2e-test.py --ui https://127.0.0.1:19443 --admin https://127.0.0.1:19444 --setup-code "$CODE"
