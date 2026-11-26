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
OLLAMA=""                    # URL, or "none"

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
  --ollama URL|none Ollama address (default: detected on this machine, otherwise ask)
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
    --ollama) OLLAMA="$2"; shift ;;
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
VOL_PREFIX=$([ "$NAME" = nuorb ] && echo nuorb || echo "$NAME")   # bis v0.3.x angelegte Volumes weiter nutzen
OLD_PROJECT="nuorb"
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
  if [ "$NAME" != nuorb ] || [ -n "$IMAGE" ] || [ "$VOL_PREFIX" != nuorb ]; then
    {
      echo "# Written by install.sh ($(date +%F)) – do not edit, run the installer again instead."
      [ "$NAME" != nuorb ] && echo "name: $NAME"
      echo "services:"
      echo "  nuorb:"
      [ "$NAME" != nuorb ] && echo "    container_name: $NAME"
      if [ -n "$IMAGE" ]; then echo "    image: $IMAGE"; echo "    pull_policy: never"; fi
      if [ "$VOL_PREFIX" != nuorb ]; then
        echo "volumes:"
        for v in data models ollama; do printf '  %s:\n    name: %s_%s\n' "$v" "$VOL_PREFIX" "$v"; done
      fi
    } > "$DIR/compose.override.yaml"
    ok "compose.override.yaml ($NAME)"
  else rm -f "$DIR/compose.override.yaml"; fi
}

# ------------------------------------------------------------------ old installation (project nuorb, up to v0.3.x)
migrate_old() {
  [ "$NAME" = nuorb ] || [ "$OLD_PROJECT" != nuorb ] || return 0
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

ollama_local() {   # Ollama auf diesem Rechner? -> "loopback" | "all" | ""
  curl -fsS -m 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1 || { echo ""; return; }
  if command -v ss >/dev/null && ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq '^(0\.0\.0\.0|\*|\[::\]):11434$'; then echo all; else echo loopback; fi
}

configure() {
  step "$(t "Settings" "Einstellungen")"
  local new=0
  if [ ! -f "$DIR/.env" ]; then cp "$DIR/.env.example" "$DIR/.env"; chmod 600 "$DIR/.env"; new=1; fi
  if [ "$new" = 0 ]; then
    ok "$(t "Keeping your settings in $DIR/.env" "Deine Einstellungen in $DIR/.env bleiben")"
    [ "$PORTS_SET" = 1 ] && { set_env NUORB_UI_PORT_PUBLIC "$UI_PORT"; set_env NUORB_ADMIN_PORT_PUBLIC "$ADMIN_PORT"; }
    [ -n "$LANG_SEL" ] && { set_env NUORB_LANG "$LANG_SEL"; set_env ADMIN_LANG "$LANG_SEL"; }
    UI_PORT=$(get_env NUORB_UI_PORT_PUBLIC); UI_PORT=${UI_PORT:-8443}
    ADMIN_PORT=$(get_env NUORB_ADMIN_PORT_PUBLIC); ADMIN_PORT=${ADMIN_PORT:-8444}
    IP=${IP:-$(get_env NUORB_HOSTS | cut -d, -f1)}; IP=${IP:-$(detect_ip)}
    if [ -n "$OLLAMA" ] && [ "$OLLAMA" != none ]; then set_env NUORB_INIT_OLLAMA_URL "$OLLAMA"; fi
    return 0
  fi
  local lang tz
  lang=${LANG_SEL:-$(ask "$(t "Language (de/en)" "Sprache (de/en)")" "$UL")}
  case "$lang" in de|en) ;; *) lang=en ;; esac
  UL=$lang
  IP=${IP:-$(ask "$(t "Address of this server in your home network" "Adresse dieses Servers im Heimnetz")" "$(detect_ip)")}
  [ -n "$IP" ] || fail "$(t "Could not detect the IP address, use --ip 192.168.1.50" "IP-Adresse nicht erkannt, bitte --ip 192.168.1.50 angeben")"
  tz=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo Europe/Berlin)
  set_env NUORB_LANG "$lang"; set_env ADMIN_LANG "$lang"; set_env TZ "${tz:-Europe/Berlin}"
  set_env NUORB_HOSTS "$IP"; set_env NUORB_UI_PORT_PUBLIC "$UI_PORT"; set_env NUORB_ADMIN_PORT_PUBLIC "$ADMIN_PORT"
  ok "$(t "Language" "Sprache") $lang · IP $IP · $(t "ports" "Ports") $UI_PORT/$ADMIN_PORT · TZ ${tz:-Europe/Berlin}"

  # Ollama (optional; geht auch später im Einrichtungsassistenten)
  local url="" lo
  if [ -z "$OLLAMA" ]; then
    lo=$(ollama_local)
    if [ -n "$lo" ]; then
      ok "$(t "Ollama is running on this machine." "Ollama läuft auf diesem Rechner.")"
      if [ "$lo" = loopback ]; then
        warn "$(t "It only listens on 127.0.0.1 – the container cannot reach it. Let it listen on all interfaces:" \
                  "Es lauscht nur auf 127.0.0.1 – der Container erreicht es so nicht. Auf allen Schnittstellen lauschen lassen:")"
        cmdline "sudo systemctl edit ollama   $(t "# add:" "# eintragen:") [Service]  Environment=\"OLLAMA_HOST=0.0.0.0\""
        cmdline "sudo systemctl restart ollama"
      fi
      url=$(ask "$(t "Ollama address (- = set up later)" "Ollama-Adresse (- = später einrichten)")" "http://$IP:11434")
    else
      url=$(ask "$(t "Ollama address, e.g. http://192.168.1.50:11434 (Enter = later / Claude only)" "Ollama-Adresse, z. B. http://192.168.1.50:11434 (Enter = später / nur Claude)")" "-")
    fi
  elif [ "$OLLAMA" != none ]; then url="$OLLAMA"; fi
  case "$url" in ""|-|none) ok "$(t "Brain: choose in the setup wizard (Ollama or Claude)." "Gehirn: im Einrichtungsassistenten wählen (Ollama oder Claude).")"; return ;; esac
  case "$url" in http://*|https://*) ;; *) url="http://$url" ;; esac
  url="${url%/}"; url="${url%/v1}"
  set_env NUORB_INIT_OLLAMA_URL "$url"
  local models model
  models=$(curl -fsS -m 4 "$url/api/tags" 2>/dev/null | grep -o '"name":"[^"]*"' | cut -d'"' -f4 || true)
  if [ -n "$models" ]; then
    printf '%s\n' "$models" | head -12 | sed 's/^/      · /'
    model=$(ask "$(t "Ollama model" "Ollama-Modell")" "$(printf '%s\n' "$models" | head -1)")
    set_env NUORB_INIT_OLLAMA_MODEL "$model"
    ok "Ollama $url · $model ($(t "needs at least 64k context: OLLAMA_CONTEXT_LENGTH=65536" "braucht mindestens 64k Kontext: OLLAMA_CONTEXT_LENGTH=65536"))"
  else
    warn "$(t "Ollama at $url does not answer from here – you can fix the address later in the setup wizard." \
              "Ollama unter $url antwortet von hier nicht – die Adresse lässt sich später im Einrichtungsassistenten ändern.")"
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
  ollama_url=$(get_env NUORB_INIT_OLLAMA_URL)
  if systemctl is-active --quiet ufw 2>/dev/null || grep -qs '^ENABLED=yes' /etc/ufw/ufw.conf; then
    step "$(t "Firewall (ufw)" "Firewall (ufw)")"
    grep -qs 'DEFAULT_FORWARD_POLICY="DROP"' /etc/default/ufw && FW_CMDS+=("sudo ufw default allow routed")
    FW_CMDS+=("sudo ufw allow from $lan to any port $UI_PORT,$ADMIN_PORT proto tcp")
    case "$ollama_url" in *"//$IP:"*|*//127.*|*//localhost*) FW_CMDS+=("sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp") ;; esac
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
    if [ ${#FW_CMDS[@]} -gt 0 ]; then warn "$(t "Most likely the firewall – see the commands above." "Wahrscheinlich die Firewall – siehe Befehle oben.")"
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
      prog=$("${DOCKER[@]}" exec "$cname" sh -c 'cat /opt/data/nuorb/models-status.json 2>/dev/null' | tr -d '\n ' | sed -n 's/.*"done_mb":\([0-9]*\).*"total_mb":\([0-9]*\).*/\1\/\2 MB/p' || true)
      printf '%s' "${prog:+ [$prog]}"
    fi
    printf '.'; sleep 2
  done
  echo
  [ "$st" = healthy ] && ok "$(t "NuOrb is running." "NuOrb läuft.")" || warn "$(t "Still starting – check with: docker compose ps" "Startet noch – prüfen mit: docker compose ps")"
  # Ollama vom Container aus erreichbar?
  local ou; ou=$(get_env NUORB_INIT_OLLAMA_URL)
  if [ -n "$ou" ] && ! "${DOCKER[@]}" exec "$cname" curl -fsS -m 6 -o /dev/null "$ou/api/version" 2>/dev/null; then
    warn "$(t "The container cannot reach Ollama at $ou." "Der Container erreicht Ollama unter $ou nicht.")"
    cmdline "OLLAMA_HOST=0.0.0.0   $(t "# Ollama must listen on all interfaces" "# Ollama muss auf allen Schnittstellen lauschen")"
    cmdline "sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp   $(t "# with ufw on the Ollama machine" "# bei ufw auf dem Ollama-Rechner")"
  fi
  CNAME="$cname"
}

finish() {
  local code
  code=$("${DOCKER[@]}" exec "$CNAME" sh -c 'cat /opt/data/nuorb/admin/setup-code.txt 2>/dev/null' || true)
  printf '\n%s' "$B$G"
  printf '  ══════════════════════════════════════════════════════════════\n'
  printf '   NuOrb %s\n' "$(t "is ready" "ist bereit")"
  printf '  ══════════════════════════════════════════════════════════════%s\n' "$N"
  printf '   %s  %shttps://%s:%s%s\n' "$(t "Admin panel:" "Verwaltung: ")" "$B" "$IP" "$ADMIN_PORT" "$N"
  if [ -n "$code" ]; then
    printf '   %s  %s%s%s\n\n' "$(t "Setup code: " "Einrichtungscode:")" "$B$Y" "$code" "$N"
    printf '   1. %s\n' "$(t "Open the address in a browser. The certificate warning is expected (own certificate) – continue." \
                             "Adresse im Browser öffnen. Die Zertifikatswarnung ist erwartet (eigenes Zertifikat) – fortfahren.")"
    printf '   2. %s\n' "$(t "Enter the setup code, choose a password, follow the setup (language, brain)." \
                             "Einrichtungscode eingeben, Passwort wählen, der Einrichtung folgen (Sprache, Gehirn).")"
    printf '   3. %s\n' "$(t "\"Pair device\": scan the QR code with the NuOrb app." "„Gerät koppeln“: QR-Code mit der NuOrb-App scannen.")"
  else
    printf '\n   %s\n' "$(t "Already set up – log in with your password. Phones stay paired." "Schon eingerichtet – mit deinem Passwort anmelden. Smartphones bleiben gekoppelt.")"
  fi
  local ms; ms=$("${DOCKER[@]}" exec "$CNAME" sh -c 'cat /opt/data/nuorb/models-status.json 2>/dev/null' 2>/dev/null | tr -d '\n ' || true)
  case "$ms" in *'"state":"ready"'*|"") ;; *)
    printf '\n   %s\n' "$(t "Speech models (~530 MB) are still downloading – the setup page shows the progress; voice works afterwards." \
                             "Die Sprachmodelle (~530 MB) laden noch – die Einrichtung zeigt den Fortschritt; Sprache geht danach.")" ;;
  esac
  printf '\n   %s %s\n' "$(t "Folder:" "Ordner:")" "$DIR"
  printf '   %s curl -fsSL https://raw.githubusercontent.com/%s/main/install.sh | bash\n' "$(t "Update/repair:" "Update/Reparatur:")" "$REPO"
  printf '   %s\n\n' "$(t "Never open ports $UI_PORT/$ADMIN_PORT to the internet; use a VPN when away." "Ports $UI_PORT/$ADMIN_PORT nie ins Internet freigeben; unterwegs ein VPN nutzen.")"
}

# ------------------------------------------------------------------ main
printf '%sNuOrb%s – %s\n' "$B" "$N" "$(t "self-hosted voice assistant · installer" "selbst gehosteter Sprachassistent · Installation")"
check_docker
[ "$UNINSTALL" = 1 ] && uninstall
fetch_files
migrate_old
configure
check_ports
firewall
start
finish
