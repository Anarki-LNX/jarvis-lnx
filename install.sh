#!/usr/bin/env bash
# NuOrb server – one-command install, update and repair.
#
#   curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/install.sh | bash -s -- --lang de
#
# Works from any shell (bash runs the script). Run it again to update or repair. Options: --help
# Never opens ports to the internet, never runs sudo without asking.
set -Eeuo pipefail

REPO="Anarki-LNX/nuorb"
REF="${NUORB_REF:-main}"
RAW="https://raw.githubusercontent.com/${REPO}/${REF}/docker"

DIR="${HOME}/nuorb"
NAME="nuorb"                 # compose project / container name
UI_PORT=8443
ADMIN_PORT=8444
PORTS_SET=0
YES=0
LANG_SEL=""
FIREWALL=1
UNINSTALL=0
SOURCE=""                    # local docker/ folder instead of download (development, offline)
IMAGE=""                     # use this image instead of ghcr.io/anarki-lnx/nuorb (development)
IP=""
OLLAMA=""                    # URL des lokalen Gehirns (Ollama oder OpenAI-kompatibel), oder "none"
LLM_KEY=""

# ------------------------------------------------------------------ output
if [ -t 1 ]; then B=$'\e[1m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; C=$'\e[36m'; N=$'\e[0m'; else B=""; G=""; Y=""; R=""; C=""; N=""; fi
UL="en"
case "${LANG:-}${LC_ALL:-}" in de*|*de_*) UL="de" ;; esac
t() { if [ "$UL" = de ]; then printf '%s' "$2"; else printf '%s' "$1"; fi; }
step() { printf '\n%s==> %s%s\n' "$B$C" "$1" "$N"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$1"; }
warn() { printf '  %s!%s %s\n' "$Y" "$N" "$1"; }
fail() { printf '\n  %s✗ %s%s\n' "$R" "$1" "$N" >&2; [ $# -gt 1 ] && printf '%s\n' "${@:2}" | sed 's/^/    /' >&2; exit 1; }
cmdline() { printf '      %s%s%s\n' "$B" "$1" "$N"; }

TTY=""
if [ -r /dev/tty ] && [ -w /dev/tty ] && { : < /dev/tty; } 2>/dev/null; then TTY=/dev/tty; fi
# ask "question" "default" -> echo answer (Enter = default; without a terminal or with --yes: default)
ask() {
  local a=""
  if [ "$YES" = 1 ] || [ -z "$TTY" ]; then printf '%s\n' "$2"; return; fi
  printf '  %s?%s %s [%s]: ' "$C" "$N" "$1" "$2" > "$TTY"
  IFS= read -r a < "$TTY" || true
  printf '%s\n' "${a:-$2}"
}
# confirm "question" [default y|n] -> 0 = yes. With --yes: the default (sudo questions default to no).
confirm() {
  local d="${2:-y}" a
  if [ "$YES" = 1 ] || [ -z "$TTY" ]; then [ "$d" = y ]; return; fi
  printf '  %s?%s %s [%s]: ' "$C" "$N" "$1" "$([ "$d" = y ] && echo Y/n || echo y/N)" > "$TTY"
  IFS= read -r a < "$TTY" || true
  a="${a:-$d}"; case "$a" in y|Y|j|J|yes|ja) return 0 ;; *) return 1 ;; esac
}

usage() {
  cat <<EOF
NuOrb server installer (install, update, repair)

  --dir DIR         installation folder (default: ~/nuorb)
  --ports UI,ADMIN  ports for the app/UI and the admin panel (default: 8443,8444)
  --lang de|en      language of the assistant and the admin panel
  --ip IP           address of this server in your home network (default: detected)
  --llm URL|none    local brain: Ollama or OpenAI-compatible server (llama.cpp, vLLM, LM Studio)
                    (default: detected on this machine, otherwise ask); --ollama is the same
  --llm-key KEY     API key of that server, if it requires one
  --yes             no questions, use defaults (never runs sudo)
  --no-firewall     do not check or change the firewall
  --uninstall       remove NuOrb (asks; data only with an extra confirmation)
  --name NAME       other project/container name, for a second instance (default: nuorb)
  --help
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) DIR="$2"; shift ;;
    --ports) UI_PORT="${2%%,*}"; ADMIN_PORT="${2##*,}"; PORTS_SET=1; shift ;;
    --lang) LANG_SEL="$2"; UL="$2"; shift ;;
    --ip) IP="$2"; shift ;;
    --ollama|--llm) OLLAMA="$2"; shift ;;
    --llm-key) LLM_KEY="$2"; shift ;;
    --yes|-y) YES=1 ;;
    --no-firewall) FIREWALL=0 ;;
    --uninstall) UNINSTALL=1 ;;
    --name) NAME="$2"; shift ;;
    --source) SOURCE="$2"; shift ;;
    --image) IMAGE="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "$(t "Unknown option: $1" "Unbekannte Option: $1")" "$(usage)" ;;
  esac
  shift
done
case "$UI_PORT$ADMIN_PORT" in *[!0-9]*|"") fail "--ports UI,ADMIN" ;; esac
case "$NAME" in *[!a-z0-9_-]*|"") fail "--name: a-z 0-9 _ -" ;; esac
[ -n "$LANG_SEL" ] && case "$LANG_SEL" in de|en) ;; *) fail "--lang de|en" ;; esac
DIR="${DIR/#\~/$HOME}"
VOL_PREFIX=$([ "$NAME" = nuorb ] && echo jarvis-lnx || echo "$NAME")   # bis v0.3.x angelegte Volumes weiter nutzen
OLD_PROJECT="jarvis-lnx"
# Testhaken (nur für automatische Tests): alte Installation und Volume-Namen umlenken
[ -n "${NUORB_VOL_PREFIX:-}" ] && VOL_PREFIX="$NUORB_VOL_PREFIX"
[ -n "${NUORB_OLD_PROJECT:-}" ] && OLD_PROJECT="$NUORB_OLD_PROJECT"

# ------------------------------------------------------------------ system detection
OS_ID="" OS_LIKE="" OS_NAME=""
OSR="${NUORB_OS_RELEASE:-/etc/os-release}"
if [ -r "$OSR" ]; then   # in einer Subshell lesen: os-release setzt u. a. NAME
  # shellcheck disable=SC1090
  OS_ID=$(. "$OSR"; printf '%s' "${ID:-}"); OS_LIKE=$(. "$OSR"; printf '%s' "${ID_LIKE:-}")
  # shellcheck disable=SC1090
  OS_NAME=$(. "$OSR"; printf '%s' "${PRETTY_NAME:-${ID:-}}")
fi
FAMILY=other
case " $OS_ID $OS_LIKE " in
  *" debian "*|*" ubuntu "*) FAMILY=debian ;;
  *" fedora "*|*" rhel "*|*" centos "*) FAMILY=fedora ;;
  *" arch "*) FAMILY=arch ;;
  *" suse "*|*" opensuse "*|*opensuse*) FAMILY=suse ;;
  *" alpine "*) FAMILY=alpine ;;
esac
IN_LXC=0
if [ "$(systemd-detect-virt -c 2>/dev/null || true)" = lxc ] || grep -qa 'container=lxc' /proc/1/environ 2>/dev/null; then IN_LXC=1; fi

pkg_hint() {   # pkg_hint <what>  -> install command for this distribution
  case "$1:$FAMILY" in
    curl:debian) echo "sudo apt update && sudo apt install -y curl" ;;
    curl:fedora) echo "sudo dnf install -y curl" ;;
    curl:arch) echo "sudo pacman -S --needed curl" ;;
    curl:suse) echo "sudo zypper install -y curl" ;;
    curl:alpine) echo "sudo apk add curl" ;;
    docker:debian|docker:fedora) echo "curl -fsSL https://get.docker.com | sudo sh && sudo systemctl enable --now docker" ;;
    docker:arch) echo "sudo pacman -S --needed docker docker-compose && sudo systemctl enable --now docker" ;;
    docker:suse) echo "sudo zypper install -y docker docker-compose && sudo systemctl enable --now docker" ;;
    docker:alpine) echo "sudo apk add docker docker-cli-compose && sudo rc-update add docker && sudo service docker start" ;;
    compose:debian) echo "sudo apt install -y docker-compose-plugin   (or: docker-compose-v2)" ;;
    compose:fedora) echo "sudo dnf install -y docker-compose-plugin" ;;
    compose:arch) echo "sudo pacman -S --needed docker-compose" ;;
    compose:suse) echo "sudo zypper install -y docker-compose" ;;
    compose:alpine) echo "sudo apk add docker-cli-compose" ;;
    docker:*) echo "https://docs.docker.com/engine/install/" ;;
    compose:*) echo "https://docs.docker.com/compose/install/linux/" ;;
    *) echo "($1)" ;;
  esac
}

# ------------------------------------------------------------------ Docker
DOCKER=(docker)
dc() { (cd "$DIR" && "${DOCKER[@]}" compose "$@"); }

check_docker() {
  step "$(t "Checking requirements" "Voraussetzungen prüfen")"
  [ -n "$OS_NAME" ] && ok "$OS_NAME$([ "$IN_LXC" = 1 ] && echo " (LXC)")"
  command -v curl >/dev/null || fail "$(t "curl is missing." "curl fehlt.")" "$(pkg_hint curl)"
  if ! command -v docker >/dev/null; then
    local extra=""
    [ "$IN_LXC" = 1 ] && extra="$(t "Proxmox LXC: on the Proxmox host first run" "Proxmox-LXC: auf dem Proxmox-Host vorher") pct set <ID> -features nesting=1,keyctl=1"
    fail "$(t "Docker is not installed. Install it with:" "Docker ist nicht installiert. Installieren mit:")" "$(pkg_hint docker)" \
         "$(t "Then run this installer again." "Danach dieses Installationsskript erneut starten.")" $extra
  fi
  local err
  if ! err=$(docker info --format '{{.ServerVersion}}' 2>&1); then
    if printf '%s' "$err" | grep -qi 'permission denied'; then
      warn "$(t "Your user may not use Docker yet." "Dein Benutzer darf Docker noch nicht benutzen.")"
      cmdline "sudo usermod -aG docker $USER   $(t "# then log out and in again" "# danach ab- und wieder anmelden")"
      if confirm "$(t "Continue now with sudo docker instead?" "Jetzt stattdessen mit sudo docker weitermachen?")" n; then DOCKER=(sudo docker); sudo docker info >/dev/null || fail "sudo docker"
      else exit 1; fi
    else
      fail "$(t "Docker is installed but not running." "Docker ist installiert, läuft aber nicht.")" "sudo systemctl enable --now docker" \
           "$( [ "$IN_LXC" = 1 ] && echo "Proxmox-LXC: pct set <ID> -features nesting=1,keyctl=1" )"
    fi
  fi
  ok "Docker $("${DOCKER[@]}" info --format '{{.ServerVersion}}')"
  "${DOCKER[@]}" compose version >/dev/null 2>&1 || fail "$(t "Docker Compose v2 is missing:" "Docker Compose v2 fehlt:")" "$(pkg_hint compose)"
  ok "Docker Compose $("${DOCKER[@]}" compose version --short 2>/dev/null)"
  check_daemon_json
}

check_daemon_json() {
  local f=/etc/docker/daemon.json
  [ -r "$f" ] || return 0
  if grep -Eq '"iptables"[[:space:]]*:[[:space:]]*false|"bridge"[[:space:]]*:[[:space:]]*"none"' "$f"; then
    warn "$(t "$f switches off Docker networking (\"iptables\": false or \"bridge\": \"none\"). Containers then have no network at all." \
              "$f schaltet das Docker-Netz ab (\"iptables\": false oder \"bridge\": \"none\"). Container haben dann gar kein Netz.")"
    warn "$(t "Fix: remove both keys and restart Docker (all running containers restart; Docker then manages its firewall rules)." \
              "Lösung: beide Schlüssel entfernen und Docker neu starten (laufende Container starten neu; Docker verwaltet dann seine Firewall-Regeln).")"
    if command -v python3 >/dev/null && confirm "$(t "Fix it now with sudo (backup: $f.nuorb-backup)?" "Jetzt mit sudo beheben (Sicherung: $f.nuorb-backup)?")" n; then
      sudo cp -a "$f" "$f.nuorb-backup"
      sudo python3 -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p))
if d.get("iptables") is False: d.pop("iptables")
if d.get("bridge") == "none": d.pop("bridge")
open(p,"w").write(json.dumps(d, indent=2)+"\n")' "$f"
      sudo systemctl restart docker && ok "$(t "Docker restarted with networking." "Docker mit Netz neu gestartet.")"
    else
      cmdline "sudo nano $f   $(t "# remove \"iptables\": false and \"bridge\": \"none\"" "# \"iptables\": false und \"bridge\": \"none\" entfernen")"
      cmdline "sudo systemctl restart docker"
      fail "$(t "Please fix this first, then run the installer again." "Bitte zuerst beheben, dann das Installationsskript erneut starten.")"
    fi
  fi
}

# ------------------------------------------------------------------ uninstall
uninstall() {
  step "$(t "Uninstall NuOrb" "NuOrb entfernen")"
  [ -f "$DIR/compose.yaml" ] || fail "$(t "No installation in $DIR (use --dir)." "Keine Installation in $DIR (--dir angeben).")"
  confirm "$(t "Stop and remove the NuOrb container in $DIR?" "NuOrb-Container in $DIR stoppen und entfernen?")" n || exit 0
  dc down && ok "$(t "Container removed." "Container entfernt.")"
  if [ -n "$TTY" ] && [ "$YES" = 0 ]; then
    local a
    printf '  %s!%s %s ' "$Y" "$N" "$(t "Also delete ALL data (password, keys, memory, paired phones)? Type DELETE to confirm, Enter keeps the data:" \
                                         "Auch ALLE Daten löschen (Passwort, Schlüssel, Gedächtnis, gekoppelte Smartphones)? Zum Bestätigen LÖSCHEN eintippen, Enter behält sie:")" > "$TTY"
    IFS= read -r a < "$TTY" || true
    if [ "$a" = DELETE ] || [ "$a" = "LÖSCHEN" ]; then
      "${DOCKER[@]}" volume rm "${VOL_PREFIX}_data" "${VOL_PREFIX}_models" 2>/dev/null || true
      "${DOCKER[@]}" volume rm "${VOL_PREFIX}_ollama" 2>/dev/null || true
      ok "$(t "Data deleted." "Daten gelöscht.")"
    else ok "$(t "Data kept (volumes ${VOL_PREFIX}_data, ${VOL_PREFIX}_models)." "Daten behalten (Volumes ${VOL_PREFIX}_data, ${VOL_PREFIX}_models).")"; fi
  fi
  if confirm "$(t "Remove the folder $DIR?" "Ordner $DIR löschen?")" n; then rm -rf -- "$DIR"; ok "$DIR"; fi
  exit 0
}

# ------------------------------------------------------------------ files
fetch_files() {
  step "$(t "Preparing $DIR" "$DIR vorbereiten")"
  mkdir -p "$DIR"
  local f
  for f in compose.yaml .env.example README.md; do
    if [ -n "$SOURCE" ]; then cp "$SOURCE/$f" "$DIR/$f"
    else curl -fsSL --retry 3 "$RAW/$f" -o "$DIR/$f.tmp" || fail "$(t "Download failed: $RAW/$f" "Download fehlgeschlagen: $RAW/$f")"; mv "$DIR/$f.tmp" "$DIR/$f"; fi
  done
  ok "compose.yaml, .env.example, README.md"
  # zweite Instanz bzw. Entwicklungs-Image: eigene Namen über compose.override.yaml (wird von Compose automatisch gelesen)
  if [ "$NAME" != nuorb ] || [ -n "$IMAGE" ] || [ "$VOL_PREFIX" != jarvis-lnx ]; then
    {
      echo "# Written by install.sh ($(date +%F)). Do not edit, run the installer again instead."
      [ "$NAME" != nuorb ] && echo "name: $NAME"
      echo "services:"
      echo "  nuorb:"
      [ "$NAME" != nuorb ] && echo "    container_name: $NAME"
      if [ -n "$IMAGE" ]; then echo "    image: $IMAGE"; echo "    pull_policy: never"; fi
      if [ "$VOL_PREFIX" != jarvis-lnx ]; then
        echo "volumes:"
        for v in data models ollama; do printf '  %s:\n    name: %s_%s\n' "$v" "$VOL_PREFIX" "$v"; done
      fi
    } > "$DIR/compose.override.yaml"
    ok "compose.override.yaml ($NAME)"
  else rm -f "$DIR/compose.override.yaml"; fi
}

# ------------------------------------------------------------------ old installation (project jarvis-lnx, up to v0.3.x)
migrate_old() {
  [ "$NAME" = nuorb ] || [ "$OLD_PROJECT" != jarvis-lnx ] || return 0
  local old wd
  old=$("${DOCKER[@]}" ps -a --filter "label=com.docker.compose.project=$OLD_PROJECT" --format '{{.Names}}' | head -1 || true)
  [ -n "$old" ] || return 0
  wd=$("${DOCKER[@]}" inspect "$old" --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true)
  step "$(t "Older installation found ($old)" "Ältere Installation gefunden ($old)")"
  ok "$(t "Its data is kept: the new version uses the same volumes." "Die Daten bleiben: Die neue Version nutzt dieselben Volumes.")"
  if [ ! -f "$DIR/.env" ] && [ -n "$wd" ] && [ -r "$wd/.env" ]; then
    cp "$wd/.env" "$DIR/.env" && ok "$(t "Settings taken over from" "Einstellungen übernommen aus") $wd/.env"
  fi
  confirm "$(t "Stop the old container now (data stays)?" "Alten Container jetzt stoppen (Daten bleiben)?")" y || fail "$(t "Both cannot run at the same time (same ports)." "Beide können nicht gleichzeitig laufen (gleiche Ports).")"
  "${DOCKER[@]}" compose -p "$OLD_PROJECT" down && ok "$(t "Old container stopped (without deleting data)." "Alter Container gestoppt (ohne Daten zu löschen).")"
}

# ------------------------------------------------------------------ settings (.env)
detect_ip() {
  local ip
  ip=$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' | head -1 || true)
  [ -n "$ip" ] || ip=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
  printf '%s' "$ip"
}
set_env() {   # set_env KEY VALUE  (in $DIR/.env)
  local f="$DIR/.env" k="$1" v="$2"
  if grep -q "^$k=" "$f"; then
    local tmp; tmp=$(mktemp "$DIR/.env.XXXX")
    awk -v k="$k" -v v="$v" 'BEGIN{FS=OFS="="} $1==k {print k "=" v; next} {print}' "$f" > "$tmp" && cat "$tmp" > "$f" && rm -f "$tmp"
  else printf '%s=%s\n' "$k" "$v" >> "$f"; fi
}
get_env() { sed -n "s/^$1=//p" "$DIR/.env" 2>/dev/null | tail -1; }

# ------------------------------------------------------------------ lokales Gehirn: Ollama oder OpenAI-kompatibler Server
bind_of() {   # bind_of PORT -> "all" | "loopback"
  if command -v ss >/dev/null && ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "^(0\.0\.0\.0|\*|\[::\]):$1\$"; then echo all; else echo loopback; fi
}
json_ids() {  # stdin: JSON von /v1/models oder /api/tags -> eine ID pro Zeile
  if command -v python3 >/dev/null; then
    python3 -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: sys.exit(0)
for m in d.get("data") or d.get("models") or []:
    i = m.get("id") or m.get("name")
    if i: print(i)' 2>/dev/null || true
  else grep -o '"\(id\|name\)":"[^"]*"' | cut -d'"' -f4 || true; fi
}
llm_probe() {  # llm_probe BASE [KEY] -> "TYP|SERVER|HTTP"  (TYP ollama|openai|"", HTTP von /v1/models)
  local b="$1" k="${2:-}" code body auth=()
  [ -n "$k" ] && auth=(-H "Authorization: Bearer $k")
  # Merkmale immer am JSON prüfen: manche Web-Apps beantworten jeden Pfad mit HTML und Status 200
  if curl -fsS -m 3 "$b/api/version" 2>/dev/null | grep -q '"version"' && curl -fsS -m 3 "$b/api/tags" 2>/dev/null | grep -q '"models"'; then
    echo "ollama|Ollama|200"; return
  fi
  body=$(curl -s -m 4 -w '\n%{http_code}' "${auth[@]}" "$b/v1/models" 2>/dev/null || true)
  code=${body##*$'\n'}; body=${body%$'\n'*}
  case "$code" in
    401|403) echo "openai|OpenAI-kompatibel|$code"; return ;;
    200) printf '%s' "$body" | grep -q '"data"' || { echo "||nojson"; return; } ;;
    *) echo "||${code:-000}"; return ;;
  esac
  if printf '%s' "$body" | grep -q '"owned_by":"llamacpp"' || curl -fsS -m 3 "${auth[@]}" "$b/props" 2>/dev/null | grep -q default_generation_settings; then echo "openai|llama.cpp|200"
  elif printf '%s' "$body" | grep -q '"owned_by":"vllm"' || curl -fsS -m 3 "${auth[@]}" "$b/version" 2>/dev/null | grep -q '"version"'; then echo "openai|vLLM|200"
  elif curl -fsS -m 3 "${auth[@]}" "$b/api/v0/models" 2>/dev/null | grep -q '"data"'; then echo "openai|LM Studio|200"
  elif curl -fsS -m 3 -o /dev/null "$b/readyz" 2>/dev/null; then echo "openai|LocalAI|200"
  else echo "openai|OpenAI-kompatibel|200"; fi
}
local_llms() {  # Server auf diesem Rechner: "PORT|TYP|SERVER|BIND" je Zeile
  local p r
  for p in 11434 8080 8000 1234; do
    r=$(llm_probe "http://127.0.0.1:$p")
    case "$r" in ollama*|openai*) printf '%s|%s|%s|%s\n' "$p" "${r%%|*}" "$(printf '%s' "$r" | cut -d'|' -f2)" "$(bind_of "$p")" ;; esac
  done
}
listen_hint() {  # listen_hint SERVER -> wie man den Server im Netz lauschen lässt
  case "$1" in
    Ollama) cmdline "sudo systemctl edit ollama   $(t "# add:" "# eintragen:") [Service]  Environment=\"OLLAMA_HOST=0.0.0.0\"  Environment=\"OLLAMA_CONTEXT_LENGTH=65536\""
            cmdline "sudo systemctl restart ollama" ;;
    llama.cpp) cmdline "llama-server … --host 0.0.0.0 -c 65536 --jinja" ;;
    vLLM) cmdline "vllm serve … --host 0.0.0.0 --max-model-len 65536 --enable-auto-tool-choice --tool-call-parser hermes" ;;
    "LM Studio") cmdline "$(t "LM Studio: Developer → Server → “Serve on Local Network”; load the model with Context Length ≥ 65536" \
                             "LM Studio: Entwickler → Server → „Im lokalen Netzwerk bereitstellen“; Modell mit Context Length ≥ 65536 laden")" ;;
    *) cmdline "--host 0.0.0.0" ;;
  esac
}

configure() {
  step "$(t "Settings" "Einstellungen")"
  local new=0
  if [ ! -f "$DIR/.env" ]; then cp "$DIR/.env.example" "$DIR/.env"; chmod 600 "$DIR/.env"; new=1; fi
  if [ "$new" = 0 ]; then
    ok "$(t "Keeping your settings in $DIR/.env" "Deine Einstellungen in $DIR/.env bleiben")"
    [ "$PORTS_SET" = 1 ] && { set_env JARVIS_UI_PORT_PUBLIC "$UI_PORT"; set_env JARVIS_ADMIN_PORT_PUBLIC "$ADMIN_PORT"; }
    [ -n "$LANG_SEL" ] && { set_env JARVIS_LANG "$LANG_SEL"; set_env ADMIN_LANG "$LANG_SEL"; }
    UI_PORT=$(get_env JARVIS_UI_PORT_PUBLIC); UI_PORT=${UI_PORT:-8443}
    ADMIN_PORT=$(get_env JARVIS_ADMIN_PORT_PUBLIC); ADMIN_PORT=${ADMIN_PORT:-8444}
    IP=${IP:-$(get_env JARVIS_HOSTS | cut -d, -f1)}; IP=${IP:-$(detect_ip)}
    if [ -n "$OLLAMA" ] && [ "$OLLAMA" != none ]; then set_env JARVIS_INIT_OLLAMA_URL "$OLLAMA"; fi
    return 0
  fi
  local lang tz
  lang=${LANG_SEL:-$(ask "$(t "Language (de/en)" "Sprache (de/en)")" "$UL")}
  case "$lang" in de|en) ;; *) lang=en ;; esac
  UL=$lang
  IP=${IP:-$(ask "$(t "Address of this server in your home network" "Adresse dieses Servers im Heimnetz")" "$(detect_ip)")}
  [ -n "$IP" ] || fail "$(t "Could not detect the IP address, use --ip 192.168.1.50" "IP-Adresse nicht erkannt, bitte --ip 192.168.1.50 angeben")"
  tz=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo Europe/Berlin)
  set_env JARVIS_LANG "$lang"; set_env ADMIN_LANG "$lang"; set_env TZ "${tz:-Europe/Berlin}"
  set_env JARVIS_HOSTS "$IP"; set_env NUORB_HOST_IP "$IP"; set_env JARVIS_UI_PORT_PUBLIC "$UI_PORT"; set_env JARVIS_ADMIN_PORT_PUBLIC "$ADMIN_PORT"
  ok "$(t "Language" "Sprache") $lang · IP $IP · $(t "ports" "Ports") $UI_PORT/$ADMIN_PORT · TZ ${tz:-Europe/Berlin}"

  # Lokales Gehirn (optional; geht auch später im Einrichtungsassistenten): Ollama oder OpenAI-kompatibler Server
  local url="" found first ltype="" server="" code="" key="${LLM_KEY:-}"
  if [ -z "$OLLAMA" ]; then
    found=$(local_llms)
    if [ -n "$found" ]; then
      ok "$(t "Language model server on this machine:" "Sprachmodell-Server auf diesem Rechner:")"
      printf '%s\n' "$found" | while IFS='|' read -r p ty sv bd; do
        printf '      · %s  http://%s:%s%s\n' "$sv" "$IP" "$p" "$([ "$bd" = loopback ] && t "  (only 127.0.0.1, not reachable from the container)" "  (nur 127.0.0.1, vom Container nicht erreichbar)")"
      done
      first=$(printf '%s\n' "$found" | head -1)
      if [ "$(printf '%s' "$first" | cut -d'|' -f4)" = loopback ]; then
        warn "$(t "Let it listen on all interfaces:" "Auf allen Schnittstellen lauschen lassen:")"; listen_hint "$(printf '%s' "$first" | cut -d'|' -f3)"
      fi
      url=$(ask "$(t "Brain address (- = set up later)" "Adresse des Gehirns (- = später einrichten)")" "http://$IP:$(printf '%s' "$first" | cut -d'|' -f1)")
    else
      url=$(ask "$(t "Address of Ollama or an OpenAI-compatible server (llama.cpp, vLLM, LM Studio), e.g. http://192.168.1.50:11434. Enter = later / Claude only" \
                     "Adresse von Ollama oder einem OpenAI-kompatiblen Server (llama.cpp, vLLM, LM Studio), z. B. http://192.168.1.50:11434. Enter = später / nur Claude")" "-")
    fi
  elif [ "$OLLAMA" != none ]; then url="$OLLAMA"; fi
  case "$url" in ""|-|none) ok "$(t "Brain: choose in the setup wizard (local server or Claude)." "Gehirn: im Einrichtungsassistenten wählen (lokaler Server oder Claude).")"; return 0 ;; esac
  case "$url" in http://*|https://*) ;; *) url="http://$url" ;; esac
  url="${url%/}"; url="${url%/v1}"
  IFS='|' read -r ltype server code <<< "$(llm_probe "$url" "$key")"
  if [ "$code" = 401 ] || [ "$code" = 403 ]; then
    if [ -n "$TTY" ] && [ "$YES" = 0 ]; then
      printf '  %s?%s %s ' "$C" "$N" "$(t "The server requires an API key (input hidden):" "Der Server verlangt einen API-Key (Eingabe verdeckt):")" > "$TTY"
      IFS= read -rs key < "$TTY" || true; echo > "$TTY"
      IFS='|' read -r ltype server code <<< "$(llm_probe "$url" "$key")"
    fi
  fi
  if [ -z "$ltype" ] || [ "$code" != 200 ]; then
    set_env JARVIS_INIT_OLLAMA_URL "$url"
    warn "$(t "No language model server answers at $url (HTTP ${code:-none}). Check the address/port, that the server listens on the network and the firewall, or fix it later in the setup wizard." \
              "Unter $url antwortet kein Sprachmodell-Server (HTTP ${code:-keine}). Adresse/Port prüfen, ob der Server im Netz lauscht, und die Firewall, oder später im Einrichtungsassistenten ändern.")"
    return 0
  fi
  set_env JARVIS_INIT_LLM_TYPE "$ltype"; set_env JARVIS_INIT_OLLAMA_URL "$url"
  [ -n "$key" ] && set_env JARVIS_INIT_LLM_API_KEY "$key"
  local models model auth=()
  [ -n "$key" ] && auth=(-H "Authorization: Bearer $key")
  if [ "$ltype" = ollama ]; then models=$(curl -fsS -m 4 "$url/api/tags" 2>/dev/null | json_ids)
  else models=$(curl -fsS -m 4 "${auth[@]}" "$url/v1/models" 2>/dev/null | json_ids); fi
  if [ -n "$models" ]; then
    printf '%s\n' "$models" | head -12 | sed 's/^/      · /'
    model=$(ask "$(t "Model" "Modell")" "$(printf '%s\n' "$models" | head -1)")
    set_env JARVIS_INIT_OLLAMA_MODEL "$model"
    ok "$server $url · $model ($(t "needs at least 64k context" "braucht mindestens 64k Kontext"))"
  else
    warn "$(t "$server answers but lists no model. Choose it later in the setup wizard." "$server antwortet, nennt aber kein Modell. Später im Einrichtungsassistenten wählen.")"
  fi
}

# ------------------------------------------------------------------ ports
check_ports() {
  local p in_use
  for p in "$UI_PORT" "$ADMIN_PORT"; do
    in_use=$(ss -ltnH "sport = :$p" 2>/dev/null | head -1 || true)
    [ -z "$in_use" ] && continue
    # belegt von unserem eigenen Container (Update) -> in Ordnung
    if "${DOCKER[@]}" ps --format '{{.Names}} {{.Ports}}' | grep -E "^$NAME .*:$p->" >/dev/null; then continue; fi
    fail "$(t "Port $p is already in use by another program." "Port $p wird schon von einem anderen Programm benutzt.")" \
         "$(t "Use other ports, e.g.:" "Andere Ports nehmen, z. B.:") ... | bash -s -- --ports 9443,9444"
  done
  ok "$(t "Ports $UI_PORT/$ADMIN_PORT are free." "Ports $UI_PORT/$ADMIN_PORT sind frei.")"
}

# ------------------------------------------------------------------ firewall
FW_CMDS=()
firewall() {
  [ "$FIREWALL" = 1 ] || return 0
  local net lan ollama_url
  net=$(ip -4 -o addr show 2>/dev/null | awk -v ip="$IP" '$4 ~ "^"ip"/" {print $4}' | head -1 || true)
  lan=$([ -n "$net" ] && python3 -c 'import ipaddress,sys; print(ipaddress.ip_interface(sys.argv[1]).network)' "$net" 2>/dev/null || echo "192.168.0.0/16")
  ollama_url=$(get_env JARVIS_INIT_OLLAMA_URL)
  local lport; lport=$(printf '%s' "$ollama_url" | sed -n 's#^https\{0,1\}://[^/]*:\([0-9]*\).*#\1#p'); lport=${lport:-11434}
  if systemctl is-active --quiet ufw 2>/dev/null || grep -qs '^ENABLED=yes' /etc/ufw/ufw.conf; then
    step "$(t "Firewall (ufw)" "Firewall (ufw)")"
    grep -qs 'DEFAULT_FORWARD_POLICY="DROP"' /etc/default/ufw && FW_CMDS+=("sudo ufw default allow routed")
    FW_CMDS+=("sudo ufw allow from $lan to any port $UI_PORT,$ADMIN_PORT proto tcp")
    case "$ollama_url" in *"//$IP:"*|*//127.*|*//localhost*) FW_CMDS+=("sudo ufw allow from 172.16.0.0/12 to any port $lport proto tcp") ;; esac
    FW_CMDS+=("sudo ufw reload")
  elif systemctl is-active --quiet firewalld 2>/dev/null; then
    step "$(t "Firewall (firewalld)" "Firewall (firewalld)")"
    FW_CMDS+=("sudo firewall-cmd --permanent --add-rich-rule=\"rule family=ipv4 source address=$lan port port=$UI_PORT protocol=tcp accept\"")
    FW_CMDS+=("sudo firewall-cmd --permanent --add-rich-rule=\"rule family=ipv4 source address=$lan port port=$ADMIN_PORT protocol=tcp accept\"")
    case "$ollama_url" in *"//$IP:"*|*//127.*|*//localhost*) FW_CMDS+=("sudo firewall-cmd --permanent --zone=trusted --add-source=172.16.0.0/12") ;; esac
    FW_CMDS+=("sudo firewall-cmd --reload")
  else
    return 0
  fi
  printf '  %s\n' "$(t "So that the container has internet and your phone reaches NuOrb (home network $lan only):" \
                         "Damit der Container Internet hat und dein Smartphone NuOrb erreicht (nur Heimnetz $lan):")"
  local c; for c in "${FW_CMDS[@]}"; do cmdline "$c"; done
  if confirm "$(t "Run these commands with sudo now?" "Diese Befehle jetzt mit sudo ausführen?")" n; then
    for c in "${FW_CMDS[@]}"; do bash -c "$c" || warn "$c"; done
    ok "$(t "Firewall rules applied." "Firewall-Regeln gesetzt.")"
  else
    warn "$(t "Not changed. If the phone or the model download cannot connect, run the commands above." \
              "Nicht geändert. Wenn das Smartphone oder der Modell-Download keine Verbindung bekommt, die Befehle oben ausführen.")"
  fi
}

# ------------------------------------------------------------------ start
start() {
  step "$(t "Downloading and starting NuOrb" "NuOrb laden und starten")"
  if [ -z "$IMAGE" ]; then dc pull --quiet nuorb || fail "$(t "Image download failed (internet? Docker Hub/GHCR reachable?)." "Download des Images fehlgeschlagen (Internet? GHCR erreichbar?).")"; fi
  local img; img=$(dc config --images 2>/dev/null | head -1 || true)
  # Hat ein Container Internet? (ufw-Forwarding, daemon.json) – kurz mit dem NuOrb-Image testen
  if ! "${DOCKER[@]}" run --rm --entrypoint curl "$img" -fsS -m 10 -o /dev/null https://huggingface.co 2>/dev/null; then
    warn "$(t "Containers have no internet access. The speech models (~530 MB) cannot be downloaded." \
              "Container haben keinen Internetzugang. Die Sprachmodelle (~530 MB) lassen sich so nicht laden.")"
    if [ ${#FW_CMDS[@]} -gt 0 ]; then warn "$(t "Most likely the firewall, see the commands above." "Wahrscheinlich die Firewall, siehe Befehle oben.")"
    else cmdline "sudo ufw default allow routed && sudo ufw reload   $(t "# with ufw" "# bei ufw")"; fi
    confirm "$(t "Start anyway?" "Trotzdem starten?")" y || exit 1
  else ok "$(t "Container network ok." "Container-Netz ok.")"; fi
  dc up -d --remove-orphans 2>&1 | grep -v -i "already exists but was" | sed 's/^/    /' || true
  local cname; cname=$(dc ps -q nuorb 2>/dev/null | head -1 || true)
  [ -n "$cname" ] || fail "$(t "The container did not start:" "Der Container ist nicht gestartet:")" "cd $DIR && docker compose logs --tail 50"
  printf '  %s' "$(t "Waiting until NuOrb is ready " "Warte, bis NuOrb bereit ist ")"
  local i st prog
  for i in $(seq 1 150); do
    st=$("${DOCKER[@]}" inspect "$cname" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || echo "?")
    [ "$st" = healthy ] && break
    [ "$st" = exited ] && { echo; fail "$(t "The container stopped:" "Der Container hat sich beendet:")" "cd $DIR && docker compose logs --tail 50"; }
    if [ $((i % 5)) -eq 0 ]; then
      prog=$("${DOCKER[@]}" exec "$cname" sh -c 'cat /opt/data/jarvis/models-status.json 2>/dev/null' | tr -d '\n ' | sed -n 's/.*"done_mb":\([0-9]*\).*"total_mb":\([0-9]*\).*/\1\/\2 MB/p' || true)
      printf '%s' "${prog:+ [$prog]}"
    fi
    printf '.'; sleep 2
  done
  echo
  [ "$st" = healthy ] && ok "$(t "NuOrb is running." "NuOrb läuft.")" || warn "$(t "Still starting. Check with: docker compose ps" "Startet noch. Prüfen mit: docker compose ps")"
  # Ollama vom Container aus erreichbar?
  local ou; ou=$(get_env JARVIS_INIT_OLLAMA_URL)
  local ok_code; ok_code=$("${DOCKER[@]}" exec "$cname" curl -s -m 6 -o /dev/null -w '%{http_code}' "$ou/v1/models" 2>/dev/null || true)
  if [ -n "$ou" ] && [ "$ok_code" != 200 ] && [ "$ok_code" != 401 ] && [ "$ok_code" != 403 ]; then
    local op; op=$(printf '%s' "$ou" | sed -n 's#^https\{0,1\}://[^/]*:\([0-9]*\).*#\1#p')
    warn "$(t "The container cannot reach the language model server at $ou." "Der Container erreicht den Sprachmodell-Server unter $ou nicht.")"
    cmdline "$(t "# the server must listen on all interfaces (0.0.0.0), not only 127.0.0.1" "# der Server muss auf allen Schnittstellen lauschen (0.0.0.0), nicht nur auf 127.0.0.1")"
    cmdline "sudo ufw allow from 172.16.0.0/12 to any port ${op:-11434} proto tcp   $(t "# with ufw on that machine" "# bei ufw auf diesem Rechner")"
  fi
  CNAME="$cname"
}

finish() {
  local code
  code=$("${DOCKER[@]}" exec "$CNAME" sh -c 'cat /opt/data/jarvis/admin/setup-code.txt 2>/dev/null' || true)
  printf '\n%s' "$B$G"
  printf '  ══════════════════════════════════════════════════════════════\n'
  printf '   NuOrb %s\n' "$(t "is ready" "ist bereit")"
  printf '  ══════════════════════════════════════════════════════════════%s\n' "$N"
  printf '   %s  %shttps://%s:%s%s\n' "$(t "Admin panel:" "Verwaltung: ")" "$B" "$IP" "$ADMIN_PORT" "$N"
  if [ -n "$code" ]; then
    printf '   %s  %s%s%s\n\n' "$(t "Setup code: " "Einrichtungscode:")" "$B$Y" "$code" "$N"
    printf '   1. %s\n' "$(t "Open the address in a browser. The certificate warning is expected (own certificate). Continue." \
                             "Adresse im Browser öffnen. Die Zertifikatswarnung ist erwartet (eigenes Zertifikat). Fortfahren.")"
    printf '   2. %s\n' "$(t "Enter the setup code, choose a password, follow the setup (language, brain)." \
                             "Einrichtungscode eingeben, Passwort wählen, der Einrichtung folgen (Sprache, Gehirn).")"
    printf '   3. %s\n' "$(t "\"Pair device\": scan the QR code with the NuOrb app." "„Gerät koppeln“: QR-Code mit der NuOrb-App scannen.")"
  else
    printf '\n   %s\n' "$(t "Already set up. Log in with your password. Phones stay paired." "Schon eingerichtet. Mit deinem Passwort anmelden. Smartphones bleiben gekoppelt.")"
  fi
  local ms; ms=$("${DOCKER[@]}" exec "$CNAME" sh -c 'cat /opt/data/jarvis/models-status.json 2>/dev/null' 2>/dev/null | tr -d '\n ' || true)
  case "$ms" in *'"state":"ready"'*|"") ;; *)
    printf '\n   %s\n' "$(t "Speech models (~530 MB) are still downloading. The setup page shows the progress; voice works afterwards." \
                             "Die Sprachmodelle (~530 MB) laden noch. Die Einrichtung zeigt den Fortschritt; Sprache geht danach.")" ;;
  esac
  printf '\n   %s %s\n' "$(t "Folder:" "Ordner:")" "$DIR"
  printf '   %s curl -fsSL https://raw.githubusercontent.com/%s/main/install.sh | bash\n' "$(t "Update/repair:" "Update/Reparatur:")" "$REPO"
  printf '   %s\n\n' "$(t "Never open ports $UI_PORT/$ADMIN_PORT to the internet; use a VPN when away." "Ports $UI_PORT/$ADMIN_PORT nie ins Internet freigeben; unterwegs ein VPN nutzen.")"
}

# ------------------------------------------------------------------ main
# Für Tests: nur die Funktionen laden (NUORB_LIB_ONLY=1 source install.sh)
if [ "${NUORB_LIB_ONLY:-}" = 1 ]; then return 0 2>/dev/null || exit 0; fi
printf '%sNuOrb%s · %s\n' "$B" "$N" "$(t "self-hosted voice assistant · installer" "selbst gehosteter Sprachassistent · Installation")"
check_docker
[ "$UNINSTALL" = 1 ] && uninstall
fetch_files
migrate_old
configure
check_ports
firewall
start
finish
