#!/usr/bin/env bash
# NuOrb on Proxmox VE: creates a ready LXC container with one command.
#
# Run in the shell of the Proxmox VE host as root:
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/proxmox/nuorb-lxc.sh)"
#
# A dialog offers Standard (Debian 12, unprivileged, 4 cores, 6 GB RAM, 24 GB
# disk, DHCP on vmbr0) or Advanced (every value can be changed). The script
# downloads the Debian 12 template if needed, creates the container, installs
# Docker in it and starts NuOrb with install.sh, the same installer as for a
# plain Docker installation (same settings, ports 8443/8444 and volumes). At
# the end it shows the address of the admin panel and the setup code.
#
# Update: run the script again, or pass "update", or type "update" inside the
# container. It pulls the newest NuOrb image; settings and data stay.
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/proxmox/nuorb-lxc.sh)" _ update
#
# Options for scripted use (all optional, --help lists them): --yes, --ctid,
# --hostname, --cores, --ram, --disk, --storage, --bridge, --ip, --gw, --vlan,
# --lang, --llm, --ports.
set -Eeuo pipefail

REPO="Anarki-LNX/nuorb"
REF="${NUORB_REF:-main}"
RAW="https://raw.githubusercontent.com/${REPO}/${REF}"
GITHUB="https://github.com/${REPO}"
LOG="${NUORB_LXC_LOG:-/var/log/nuorb-lxc.log}"

# ------------------------------------------------------------------ defaults (see NUORB_PROXMOX_SPEC)
CMD="auto"
CTID=""
CT_HOSTNAME="nuorb"
CORES=4
RAM=6144
SWAP=512
DISK=24
STORAGE=""
TSTORAGE=""
BRIDGE="vmbr0"
NET_IP="dhcp"
GW=""
VLAN=""
NU_LANG=""
LLM=""
PORTS="8443,8444"
YES=0

# ------------------------------------------------------------------ output
UL="en"
case "${LC_ALL:-}${LANG:-}" in de*|*de_*) UL="de" ;; esac
# pct exec hands the host locale to the container, where it may not exist.
export LANG=C.UTF-8 LC_ALL=C.UTF-8
unset LANGUAGE

if [ -t 1 ]; then B=$'\e[1m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; C=$'\e[36m'; N=$'\e[0m'; else B=""; G=""; Y=""; R=""; C=""; N=""; fi
t() { if [ "$UL" = de ]; then printf '%s' "$2"; else printf '%s' "$1"; fi; }
step() { printf '\n%s==> %s%s\n' "$B$C" "$1" "$N"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$1"; }
warn() { printf '  %s!%s %s\n' "$Y" "$N" "$1" >&2; }
die()  { printf '\n  %s✗ %s%s\n' "$R" "$1" "$N" >&2; [ $# -gt 1 ] && printf '%s\n' "${@:2}" | sed 's/^/    /' >&2; exit 1; }

usage() {
  cat <<EOF
NuOrb on Proxmox VE: create a NuOrb LXC container, or update one.

  nuorb-lxc.sh [install | update [ID]] [options]

  install            create a new container (default when none exists)
  update [ID]        pull the newest NuOrb image in an existing container
                     (default when a NuOrb container exists)
  --yes              no dialog, use the defaults and the options below
  --lang de|en       language of the dialog and of NuOrb
  --ctid ID          container ID (default: next free ID)
  --hostname NAME    host name (default: nuorb)
  --cores N          CPU cores (default: 4)
  --ram MB           memory in MB (default: 6144)
  --disk GB          root disk in GB (default: 24)
  --storage NAME     storage for the root disk (default: local-lvm, local-zfs or the first one)
  --template-storage NAME  storage for the Debian template (default: local)
  --bridge NAME      network bridge (default: vmbr0)
  --ip dhcp|CIDR     dhcp or a static address like 192.168.1.50/24 (default: dhcp)
  --gw IP            gateway, needed with a static address
  --vlan TAG         VLAN tag (default: none)
  --llm URL          local language model server (Ollama or OpenAI compatible),
                     e.g. http://192.168.1.50:11434 (default: choose later in the setup)
  --ports UI,ADMIN   ports of the app and the admin panel (default: 8443,8444)
  --help
EOF
}

# ------------------------------------------------------------------ arguments
need_arg() { [ $# -ge 2 ] && [ -n "$2" ] || die "$(t "Option $1 needs a value." "Option $1 braucht einen Wert.")"; }
while [ $# -gt 0 ]; do
  case "$1" in
    install) CMD=install ;;
    update) CMD=update; if [ $# -ge 2 ] && [[ "$2" =~ ^[0-9]+$ ]]; then CTID="$2"; shift; fi ;;
    help|-h|--help) usage; exit 0 ;;
    --yes|-y) YES=1 ;;
    --lang) need_arg "$@"; NU_LANG="$2"; shift ;;
    --ctid) need_arg "$@"; CTID="$2"; shift ;;
    --hostname) need_arg "$@"; CT_HOSTNAME="$2"; shift ;;
    --cores) need_arg "$@"; CORES="$2"; shift ;;
    --ram) need_arg "$@"; RAM="$2"; shift ;;
    --disk) need_arg "$@"; DISK="$2"; shift ;;
    --storage) need_arg "$@"; STORAGE="$2"; shift ;;
    --template-storage) need_arg "$@"; TSTORAGE="$2"; shift ;;
    --bridge) need_arg "$@"; BRIDGE="$2"; shift ;;
    --ip) need_arg "$@"; NET_IP="$2"; shift ;;
    --gw) need_arg "$@"; GW="$2"; shift ;;
    --vlan) need_arg "$@"; VLAN="$2"; shift ;;
    --llm|--ollama) need_arg "$@"; LLM="$2"; shift ;;
    --ports) need_arg "$@"; PORTS="$2"; shift ;;
    *) die "$(t "Unknown option: $1" "Unbekannte Option: $1")" "$(usage)" ;;
  esac
  shift
done
if [ -n "$NU_LANG" ]; then
  case "$NU_LANG" in de|en) UL="$NU_LANG" ;; *) die "--lang de|en" ;; esac
fi

# Dialogs need whiptail and a terminal; --yes or no terminal: defaults and options only.
WT=0
if [ "$YES" = 0 ] && [ -t 0 ] && [ -t 1 ] && command -v whiptail >/dev/null; then WT=1; fi
BT="NuOrb · Proxmox VE"

# wt ARGS: dialog, answer in $A (whiptail answers on stderr). Cancel or Esc ends the script.
A=""
wt() {
  if ! A=$(whiptail --backtitle "$BT" "$@" 3>&1 1>&2 2>&3); then
    printf '\n%s\n' "$(t "Cancelled, nothing changed." "Abgebrochen, nichts geändert.")"
    exit 0
  fi
}
yesno() { whiptail --backtitle "$BT" --title "$1" --yesno "$2" "${3:-12}" 72; }

# ------------------------------------------------------------------ checks
is_uint() { [[ "$1" =~ ^[0-9]+$ ]]; }
is_ipv4() {
  local ip="$1" o
  [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  IFS=. read -r -a o <<< "$ip"
  for ip in "${o[@]}"; do [ "$ip" -le 255 ] || return 1; done
}
is_cidr() {
  [[ "$1" =~ ^([0-9.]+)/([0-9]+)$ ]] || return 1
  local addr="${BASH_REMATCH[1]}" bits="${BASH_REMATCH[2]}"
  is_ipv4 "$addr" && [ "$bits" -ge 1 ] && [ "$bits" -le 32 ]
}

validate() {
  is_uint "$CORES" && [ "$CORES" -ge 1 ] || die "$(t "Cores: a number of at least 1." "Kerne: eine Zahl ab 1.")"
  is_uint "$RAM" && [ "$RAM" -ge 2048 ] || die "$(t "RAM: at least 2048 MB (6144 recommended)." "RAM: mindestens 2048 MB (6144 empfohlen).")"
  is_uint "$DISK" && [ "$DISK" -ge 12 ] || die "$(t "Disk: at least 12 GB (24 recommended)." "Disk: mindestens 12 GB (24 empfohlen).")"
  [[ "$CT_HOSTNAME" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]] || die "$(t "Host name: letters, digits and hyphens." "Hostname: Buchstaben, Ziffern und Bindestriche.")"
  [ -z "$CTID" ] || { is_uint "$CTID" && [ "$CTID" -ge 100 ]; } || die "$(t "Container ID: a number of at least 100." "Container-ID: eine Zahl ab 100.")"
  [ -z "$VLAN" ] || { is_uint "$VLAN" && [ "$VLAN" -ge 1 ] && [ "$VLAN" -le 4094 ]; } || die "VLAN: 1-4094"
  [[ "$BRIDGE" =~ ^[a-zA-Z0-9._-]+$ ]] || die "$(t "Bridge: invalid name." "Bridge: ungültiger Name.")"
  if [ "$NET_IP" != dhcp ]; then
    is_cidr "$NET_IP" || die "$(t "IP: dhcp or an address with prefix, e.g. 192.168.1.50/24." "IP: dhcp oder eine Adresse mit Präfix, z. B. 192.168.1.50/24.")"
    is_ipv4 "$GW" || die "$(t "A static IP needs a gateway (--gw), e.g. 192.168.1.1." "Eine feste IP braucht ein Gateway (--gw), z. B. 192.168.1.1.")"
  fi
  [[ "$PORTS" =~ ^[0-9]+,[0-9]+$ ]] && [ "${PORTS%,*}" != "${PORTS#*,}" ] || die "$(t "Ports: UI,ADMIN, e.g. 8443,8444." "Ports: UI,ADMIN, z. B. 8443,8444.")"
  case "$LLM" in ""|none|http://*|https://*) ;; *) LLM="http://$LLM" ;; esac
}

check_host() {
  [ "$(id -u)" -eq 0 ] || die "$(t "Run this as root in the shell of the Proxmox VE host." "Bitte als root in der Shell des Proxmox-VE-Hosts ausführen.")"
  local c
  for c in pct pveam pvesm pvesh pveversion; do
    command -v "$c" >/dev/null || die "$(t "$c not found. This script runs on a Proxmox VE host." "$c nicht gefunden. Dieses Skript läuft auf einem Proxmox-VE-Host.")"
  done
  local arch; arch=$(dpkg --print-architecture 2>/dev/null || uname -m)
  case "$arch" in
    amd64|x86_64) ;;
    *) die "$(t "The NuOrb container is available for amd64 (x86_64) only, this host is $arch." "Den NuOrb-Container gibt es nur für amd64 (x86_64), dieser Host ist $arch.")" \
           "$(t "On other hardware install NuOrb with Docker:" "Auf anderer Hardware NuOrb mit Docker installieren:") curl -fsSL ${RAW}/install.sh | bash" ;;
  esac
  local v; v=$(pveversion 2>/dev/null | sed -n 's#^pve-manager/\([0-9]*\)\..*#\1#p')
  if [ -n "$v" ] && [ "$v" -lt 8 ]; then
    die "$(t "Proxmox VE $v is too old, version 8 or newer is needed." "Proxmox VE $v ist zu alt, nötig ist Version 8 oder neuer.")"
  fi
  touch "$LOG" 2>/dev/null || LOG=/dev/null
}

# Runs a command with its output in the log; on failure shows the end of the log.
run() {
  local what="$1"; shift
  printf '\n## %s  %s\n' "$(date '+%F %T')" "$what" >> "$LOG"
  if "$@" >> "$LOG" 2>&1; then ok "$what"; return 0; fi
  printf '  %s✗%s %s\n' "$R" "$N" "$what" >&2
  tail -n 25 "$LOG" | sed 's/^/    | /' >&2
  die "$(t "Failed. Full log:" "Fehlgeschlagen. Vollständiges Log:") $LOG"
}

# ------------------------------------------------------------------ existing NuOrb containers (tag nuorb)
nuorb_cts() {   # one line per container: "ID|name|status"
  local id st name
  pct list 2>/dev/null | awk 'NR>1 && $1 ~ /^[0-9]+$/ {print $1, $2, $NF}' | while read -r id st name; do
    if pct config "$id" 2>/dev/null | grep -Eq '^tags:.*(^|[ ;,])nuorb([;, ]|$)'; then printf '%s|%s|%s\n' "$id" "$name" "$st"; fi
  done
}

# ------------------------------------------------------------------ dialog
pick_storage() {   # pick_storage CONTENT PREFERRED... -> first active storage with that content
  local content="$1"; shift
  local avail s
  avail=$(pvesm status -content "$content" 2>/dev/null | awk 'NR>1 && $3=="active" {print $1}')
  for s in "$@" $avail; do
    if printf '%s\n' "$avail" | grep -qx -- "$s"; then printf '%s' "$s"; return 0; fi
  done
  return 0
}

dialog() {
  if [ -z "$NU_LANG" ]; then
    wt --title "NuOrb" --default-item "$UL" --menu "Language / Sprache" 12 60 2 en "English" de "Deutsch"; NU_LANG="$A"
    UL="$NU_LANG"
  fi
  local mode
  wt --title "$(t "NuOrb container" "NuOrb-Container")" --menu \
    "$(t "Standard: Debian 12, unprivileged, ${CORES} cores, $((RAM / 1024)) GB RAM, ${DISK} GB disk, DHCP on ${BRIDGE}, ports ${PORTS/,//}." \
         "Standard: Debian 12, unprivilegiert, ${CORES} Kerne, $((RAM / 1024)) GB RAM, ${DISK} GB Disk, DHCP an ${BRIDGE}, Ports ${PORTS/,//}.")" \
    14 72 2 standard "$(t "Standard settings" "Standardeinstellungen")" advanced "$(t "Advanced: choose every value" "Erweitert: alle Werte wählen")"; mode="$A"
  [ "$mode" = advanced ] || return 0

  local title; title=$(t "Advanced" "Erweitert")
  wt --title "$title" --inputbox "$(t "Container ID" "Container-ID")" 9 60 "$CTID"; CTID="$A"
  wt --title "$title" --inputbox "$(t "Host name" "Hostname")" 9 60 "$CT_HOSTNAME"; CT_HOSTNAME="$A"
  wt --title "$title" --inputbox "$(t "CPU cores" "CPU-Kerne")" 9 60 "$CORES"; CORES="$A"
  wt --title "$title" --inputbox "$(t "RAM in MB (at least 2048)" "RAM in MB (mindestens 2048)")" 9 60 "$RAM"; RAM="$A"
  wt --title "$title" --inputbox "$(t "Disk in GB (at least 12)" "Disk in GB (mindestens 12)")" 9 60 "$DISK"; DISK="$A"
  local list=() s
  while read -r s; do [ -n "$s" ] && list+=("$s" ""); done < <(pvesm status -content rootdir 2>/dev/null | awk 'NR>1 && $3=="active" {print $1}')
  if [ ${#list[@]} -gt 2 ]; then
    wt --title "$title" --default-item "$STORAGE" --menu "$(t "Storage for the container disk" "Speicher für die Container-Disk")" 16 60 6 "${list[@]}"; STORAGE="$A"
  fi
  list=()
  while read -r s; do [ -n "$s" ] && list+=("$s" ""); done < <(ip -o link show type bridge 2>/dev/null | awk -F': ' '{print $2}' | cut -d@ -f1 | grep -Ev '^(fwbr|docker|br-|virbr)')
  if [ ${#list[@]} -gt 2 ]; then
    wt --title "$title" --default-item "$BRIDGE" --menu "$(t "Network bridge" "Netzwerk-Bridge")" 16 60 6 "${list[@]}"; BRIDGE="$A"
  fi
  wt --title "$title" --inputbox "$(t "IPv4: dhcp or a fixed address with prefix, e.g. 192.168.1.50/24" "IPv4: dhcp oder eine feste Adresse mit Präfix, z. B. 192.168.1.50/24")" 9 72 "$NET_IP"; NET_IP="$A"
  if [ "$NET_IP" != dhcp ]; then
    wt --title "$title" --inputbox "$(t "Gateway, e.g. 192.168.1.1" "Gateway, z. B. 192.168.1.1")" 9 60 "$GW"; GW="$A"
  fi
  wt --title "$title" --inputbox "$(t "VLAN tag (empty = none)" "VLAN-Tag (leer = keiner)")" 9 60 "$VLAN"; VLAN="$A"
  wt --title "$title" --inputbox "$(t "Ports of the app and the admin panel (UI,ADMIN)" "Ports von App und Verwaltung (UI,ADMIN)")" 9 60 "$PORTS"; PORTS="$A"
  wt --title "$title" --inputbox "$(t "Local language model server (Ollama or OpenAI compatible), e.g. http://192.168.1.50:11434. Empty = choose later in the setup." \
                                           "Lokaler Sprachmodell-Server (Ollama oder OpenAI-kompatibel), z. B. http://192.168.1.50:11434. Leer = später in der Einrichtung wählen.")" 11 72 "$LLM"; LLM="$A"
}

# ------------------------------------------------------------------ template
TEMPLATE=""
find_template() {
  local re='^debian-12-standard_.*_amd64\.tar\.(zst|gz|xz)$'
  TEMPLATE=$(pveam list "$TSTORAGE" 2>/dev/null | awk 'NR>1 {print $1}' | sed 's#.*/##' | grep -E "$re" | sort -V | tail -n 1 || true)
  if [ -n "$TEMPLATE" ]; then ok "$(t "Template" "Template") $TEMPLATE ($TSTORAGE)"; return 0; fi
  run "$(t "Updating the template list" "Template-Liste aktualisieren")" pveam update
  TEMPLATE=$(pveam available --section system 2>/dev/null | awk '{print $2}' | grep -E "$re" | sort -V | tail -n 1 || true)
  [ -n "$TEMPLATE" ] || die "$(t "No Debian 12 template found in 'pveam available'." "Kein Debian-12-Template in 'pveam available' gefunden.")"
  run "$(t "Downloading template $TEMPLATE to $TSTORAGE" "Template $TEMPLATE nach $TSTORAGE laden")" pveam download "$TSTORAGE" "$TEMPLATE"
}

# ------------------------------------------------------------------ container
CREATED=""
WORK=""
cleanup() {
  local rc=$?
  [ -n "$WORK" ] && rm -rf "$WORK"
  if [ "$rc" -ne 0 ] && [ -n "$CREATED" ]; then
    warn "$(t "Setting up container $CREATED did not finish." "Die Einrichtung von Container $CREATED ist nicht fertig geworden.")"
    if [ "$WT" = 1 ] && yesno "$(t "Setup failed" "Einrichtung fehlgeschlagen")" \
         "$(t "Delete the unfinished container $CREATED? Choose No to keep it for a look inside (pct enter $CREATED)." \
              "Den unfertigen Container $CREATED löschen? Nein behält ihn, um hineinzuschauen (pct enter $CREATED).")" 10 --defaultno; then
      pct stop "$CREATED" >/dev/null 2>&1 || true
      pct destroy "$CREATED" --purge 1 >/dev/null 2>&1 && ok "$(t "Container $CREATED deleted." "Container $CREATED gelöscht.")"
    else
      warn "$(t "Kept. Look inside: pct enter $CREATED · delete: pct stop $CREATED; pct destroy $CREATED --purge 1" \
                "Behalten. Hineinschauen: pct enter $CREATED · löschen: pct stop $CREATED; pct destroy $CREATED --purge 1")"
    fi
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'printf "  %s(line %s)%s\n" "$R" "$LINENO" "$N" >&2' ERR

ct_ip() { pct exec "$1" -- ip -4 -o addr show dev eth0 scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n 1 || true; }

wait_network() {   # wait_network ID
  printf '  %s' "$(t "Waiting for the network " "Warte auf das Netz ")"
  for _ in $(seq 1 90); do
    if pct exec "$1" -- getent hosts deb.debian.org >/dev/null 2>&1; then echo; ok "$(t "Network ok" "Netz ok") ($(ct_ip "$1"))"; return 0; fi
    printf '.'; sleep 2
  done
  echo
  die "$(t "Container $1 has no network or DNS after 3 minutes. Check the bridge, DHCP or the static address." \
           "Container $1 hat nach 3 Minuten kein Netz oder DNS. Bridge, DHCP oder die feste Adresse prüfen.")"
}

# ct-setup.sh: next to this script in a checkout, otherwise from GitHub
fetch_ct_setup() {
  WORK=$(mktemp -d -p /var/tmp nuorb-lxc.XXXXXX)
  local here; here=$(dirname -- "${BASH_SOURCE[0]:-$0}")
  if [ -r "$here/ct-setup.sh" ]; then cp "$here/ct-setup.sh" "$WORK/ct-setup.sh"
  else curl -fsSL --retry 3 "$RAW/proxmox/ct-setup.sh" -o "$WORK/ct-setup.sh" || die "$(t "Download failed:" "Download fehlgeschlagen:") $RAW/proxmox/ct-setup.sh"
  fi
}

setup_ct() {   # setup_ct ID: Docker, update command, login notice
  fetch_ct_setup
  run "$(t "Copying the setup script" "Einrichtungsskript kopieren")" pct push "$1" "$WORK/ct-setup.sh" /root/ct-setup.sh --perms 0755
  # shellcheck disable=SC2016  # $1 expands inside the container
  run "$(t "Installing Debian updates and Docker (a few minutes)" "Debian-Updates und Docker installieren (einige Minuten)")" \
      pct exec "$1" -- bash -c 'NUORB_REF="$1" /root/ct-setup.sh; rc=$?; rm -f /root/ct-setup.sh; exit $rc' _ "$REF"
}

# install.sh output on screen up to its own summary (this script prints one for the container); all of it goes to the log
screen() { awk '/══════/ {skip = 1} !skip {print; fflush()}'; }

# install.sh inside the container, output live and in the log
install_nuorb() {   # install_nuorb ID IP
  local llm="${LLM:-none}"
  step "$(t "Installing NuOrb in container $1" "NuOrb in Container $1 installieren")"
  printf '\n## %s  install.sh in %s\n' "$(date '+%F %T')" "$1" >> "$LOG"
  # shellcheck disable=SC2016  # $1..$5 expand inside the container
  if ! pct exec "$1" -- env HOME=/root NUORB_REF="$REF" bash -c \
      'curl -fsSL --retry 3 "$1" -o /root/nuorb-install.sh && bash /root/nuorb-install.sh --yes --no-firewall --lang "$2" --ip "$3" --llm "$4" --ports "$5"; rc=$?; rm -f /root/nuorb-install.sh; exit $rc' \
      _ "$RAW/install.sh" "$NU_LANG" "$2" "$llm" "$PORTS" 2>&1 | tee -a "$LOG" | screen; then
    die "$(t "install.sh failed in container $1. Log:" "install.sh ist in Container $1 fehlgeschlagen. Log:") $LOG"
  fi
}

summary() {   # summary ID
  local id="$1" ip code ui admin
  ip=$(ct_ip "$id"); ip=${ip:-<IP>}
  ui=$(pct exec "$id" -- sed -n 's/^JARVIS_UI_PORT_PUBLIC=//p' /root/nuorb/.env 2>/dev/null | tail -n 1 || true); ui=${ui:-8443}
  admin=$(pct exec "$id" -- sed -n 's/^JARVIS_ADMIN_PORT_PUBLIC=//p' /root/nuorb/.env 2>/dev/null | tail -n 1 || true); admin=${admin:-8444}
  code=$(pct exec "$id" -- docker exec nuorb cat /opt/data/jarvis/admin/setup-code.txt 2>/dev/null || true)
  pct set "$id" --description "NuOrb, self-hosted voice assistant. Admin panel: https://${ip}:${admin} · App: https://${ip}:${ui} · Update: type update in the container. ${GITHUB}" >/dev/null 2>&1 || true
  printf '\n%s' "$B$G"
  printf '  ══════════════════════════════════════════════════════════════\n'
  printf '   NuOrb %s %s\n' "$(t "is running in container" "läuft in Container")" "$id"
  printf '  ══════════════════════════════════════════════════════════════%s\n' "$N"
  printf '   %-18s %shttps://%s:%s%s\n' "$(t "Admin panel" "Verwaltung")" "$B" "$ip" "$admin" "$N"
  printf '   %-18s https://%s:%s\n' "$(t "App address" "App-Adresse")" "$ip" "$ui"
  if [ -n "$code" ]; then
    printf '   %-18s %s%s%s\n\n' "$(t "Setup code" "Einrichtungscode")" "$B$Y" "$code" "$N"
    printf '   1. %s\n' "$(t "Open the admin panel in a browser. The certificate warning is expected (own certificate)." \
                             "Verwaltung im Browser öffnen. Die Zertifikatswarnung ist erwartet (eigenes Zertifikat).")"
    printf '   2. %s\n' "$(t "Enter the setup code, choose a password, follow the setup (language, brain)." \
                             "Einrichtungscode eingeben, Passwort wählen, der Einrichtung folgen (Sprache, Gehirn).")"
    # shellcheck disable=SC1111  # German quotation marks on purpose
    printf '   3. %s\n' "$(t "Pair your phone: \"Pair device\" in the admin panel, scan the QR code with the NuOrb app." \
                             "Smartphone koppeln: „Gerät koppeln“ in der Verwaltung, QR-Code mit der NuOrb-App scannen.")"
  else
    printf '\n   %s\n' "$(t "Already set up. Log in with your password. Paired phones stay paired." "Schon eingerichtet. Mit deinem Passwort anmelden. Gekoppelte Smartphones bleiben gekoppelt.")"
  fi
  printf '\n   %-18s pct enter %s\n' "Shell" "$id"
  printf '   %-18s %s\n' "Update" "$(t "type update in the container, or run this script again" "im Container update eingeben, oder dieses Skript erneut starten")"
  printf '   %s\n\n' "$(t "Never open these ports to the internet; use a VPN when away." "Diese Ports nie ins Internet freigeben; unterwegs ein VPN nutzen.")"
}

# ------------------------------------------------------------------ commands
cmd_install() {
  CTID=${CTID:-$(pvesh get /cluster/nextid 2>/dev/null || true)}
  STORAGE=${STORAGE:-$(pick_storage rootdir local-lvm local-zfs)}
  TSTORAGE=${TSTORAGE:-$(pick_storage vztmpl local)}
  [ "$WT" = 1 ] && dialog
  NU_LANG=${NU_LANG:-$UL}
  validate
  [ -n "$CTID" ] || die "$(t "No free container ID found, use --ctid." "Keine freie Container-ID gefunden, bitte --ctid angeben.")"
  pvesh get /cluster/nextid --vmid "$CTID" >/dev/null 2>&1 || die "$(t "ID $CTID is already in use." "Die ID $CTID ist schon vergeben.")"
  [ -n "$STORAGE" ] || die "$(t "No active storage for containers found, use --storage." "Kein aktiver Speicher für Container gefunden, bitte --storage angeben.")"
  [ -n "$TSTORAGE" ] || die "$(t "No storage for templates found, use --template-storage." "Kein Speicher für Templates gefunden, bitte --template-storage angeben.")"
  pvesm status -content rootdir 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx -- "$STORAGE" \
    || die "$(t "Storage $STORAGE cannot hold containers." "Speicher $STORAGE kann keine Container aufnehmen.")"
  local free; free=$(pvesm status -storage "$STORAGE" 2>/dev/null | awk 'NR==2 {print int($6/1048576)}' || true)
  if [ -n "$free" ] && [ "$free" -lt "$DISK" ]; then
    warn "$(t "Only ${free} GB free on $STORAGE, the container gets ${DISK} GB." "Nur ${free} GB frei auf $STORAGE, der Container bekommt ${DISK} GB.")"
  fi

  local net="name=eth0,bridge=${BRIDGE},ip=${NET_IP}"
  [ "$NET_IP" != dhcp ] && net="${net},gw=${GW}"
  [ -n "$VLAN" ] && net="${net},tag=${VLAN}"
  local text
  text=$(
    printf '%-11s %s\n' "Container" "${CTID} (${CT_HOSTNAME}), Debian 12, $(t "unprivileged" "unprivilegiert"), nesting, keyctl"
    printf '%-11s %s\n' "$(t "Resources" "Ressourcen")" "${CORES} $(t "cores" "Kerne"), ${RAM} MB RAM, ${DISK} GB $(t "on" "auf") ${STORAGE}"
    printf '%-11s %s\n' "$(t "Network" "Netz")" "${BRIDGE}, ${NET_IP}${GW:+, gw $GW}${VLAN:+, VLAN $VLAN}"
    printf '%-11s %s\n' "NuOrb" "$(t "language" "Sprache") ${NU_LANG}, $(t "ports" "Ports") ${PORTS/,//}, $(t "brain" "Gehirn") ${LLM:-$(t "choose in the setup" "in der Einrichtung wählen")}"
  )
  if [ "$WT" = 1 ]; then
    yesno "$(t "Create the NuOrb container?" "NuOrb-Container anlegen?")" "$text" 13 || { t "Nothing changed." "Nichts geändert."; echo; exit 0; }
  else
    step "$(t "NuOrb container" "NuOrb-Container")"; printf '%s\n' "$text" | sed 's/^/  /'
  fi

  step "$(t "Preparing the container" "Container vorbereiten")"
  find_template
  run "$(t "Creating container $CTID" "Container $CTID anlegen")" pct create "$CTID" "${TSTORAGE}:vztmpl/${TEMPLATE}" \
    --hostname "$CT_HOSTNAME" --ostype debian --unprivileged 1 --features nesting=1,keyctl=1 \
    --cores "$CORES" --memory "$RAM" --swap "$SWAP" --rootfs "${STORAGE}:${DISK}" \
    --net0 "$net" --onboot 1 --timezone host --tags nuorb \
    --description "NuOrb, self-hosted voice assistant. ${GITHUB}"
  CREATED="$CTID"
  run "$(t "Starting container $CTID" "Container $CTID starten")" pct start "$CTID"
  wait_network "$CTID"
  setup_ct "$CTID"

  local ip="${NET_IP%/*}"
  [ "$NET_IP" = dhcp ] && ip=$(ct_ip "$CTID")
  install_nuorb "$CTID" "$ip"
  CREATED=""
  summary "$CTID"
  [ "$NET_IP" = dhcp ] && printf '   %s\n\n' "$(t "Tip: give the container a fixed address in your router (DHCP reservation), so phones always find it." \
                                                  "Tipp: Dem Container im Router eine feste Adresse geben (DHCP-Reservierung), damit Smartphones ihn immer finden.")"
  return 0
}

cmd_update() {
  local id="$CTID"
  if [ -z "$id" ]; then
    local cts; cts=$(nuorb_cts)
    [ -n "$cts" ] || die "$(t "No NuOrb container (tag nuorb) found. Pass the ID: update <ID>" "Kein NuOrb-Container (Tag nuorb) gefunden. Bitte die ID angeben: update <ID>")"
    if [ "$(printf '%s\n' "$cts" | wc -l)" -eq 1 ]; then id=${cts%%|*}
    elif [ "$WT" = 1 ]; then
      local items=() l
      while IFS= read -r l; do items+=("${l%%|*}" "$(printf '%s' "$l" | cut -d'|' -f2,3 | tr '|' ' ')"); done <<< "$cts"
      wt --title "Update" --menu "$(t "Which NuOrb container?" "Welcher NuOrb-Container?")" 16 60 6 "${items[@]}"; id="$A"
    else
      die "$(t "Several NuOrb containers, pass the ID: update <ID>" "Mehrere NuOrb-Container, bitte die ID angeben: update <ID>")" "$(printf '%s\n' "$cts" | tr '|' ' ')"
    fi
  fi
  is_uint "$id" || die "$(t "Container ID: a number." "Container-ID: eine Zahl.")"
  pct status "$id" >/dev/null 2>&1 || die "$(t "Container $id does not exist." "Container $id gibt es nicht.")"
  step "$(t "Updating NuOrb in container $id" "NuOrb in Container $id aktualisieren")"
  if ! pct status "$id" | grep -q running; then
    run "$(t "Starting container $id" "Container $id starten")" pct start "$id"
    wait_network "$id"
  fi
  if ! pct exec "$id" -- test -x /usr/local/bin/update; then
    setup_ct "$id"
  fi
  printf '\n## %s  update in %s\n' "$(date '+%F %T')" "$id" >> "$LOG"
  local lang_arg=()
  [ -n "$NU_LANG" ] && lang_arg=(--lang "$NU_LANG")
  pct exec "$id" -- env NUORB_REF="$REF" /usr/local/bin/update "${lang_arg[@]}" 2>&1 | tee -a "$LOG" | screen \
    || die "$(t "Update failed in container $id. Log:" "Update in Container $id fehlgeschlagen. Log:") $LOG"
  summary "$id"
}

# ------------------------------------------------------------------ main
# For tests: load the functions only (NUORB_LIB_ONLY=1 source nuorb-lxc.sh)
# shellcheck disable=SC2317  # exit is reached when the file is run instead of sourced
if [ "${NUORB_LIB_ONLY:-}" = 1 ]; then trap - EXIT ERR; return 0 2>/dev/null || exit 0; fi
printf '%sNuOrb%s · %s\n' "$B" "$N" "$(t "self-hosted voice assistant · Proxmox VE container" "selbst gehosteter Sprachassistent · Proxmox-VE-Container")"
check_host
if [ "$CMD" = auto ]; then
  CMD=install
  existing=$(nuorb_cts)
  if [ -n "$existing" ]; then
    if [ "$WT" = 1 ]; then
      items=()
      while IFS= read -r l; do items+=("${l%%|*}" "$(t "Update" "Aktualisieren"): $(printf '%s' "$l" | cut -d'|' -f2,3 | tr '|' ' ')"); done <<< "$existing"
      items+=(new "$(t "Create a new NuOrb container" "Neuen NuOrb-Container anlegen")")
      wt --title "NuOrb" --menu "$(t "NuOrb containers on this host:" "NuOrb-Container auf diesem Host:")" 16 72 6 "${items[@]}"; choice="$A"
      if [ "$choice" != new ]; then CMD=update; CTID="$choice"; fi
    elif [ "$(printf '%s\n' "$existing" | wc -l)" -eq 1 ]; then
      CMD=update
    else
      die "$(t "Several NuOrb containers exist. Choose: update <ID> or install" "Es gibt mehrere NuOrb-Container. Bitte wählen: update <ID> oder install")" "$(printf '%s\n' "$existing" | tr '|' ' ')"
    fi
  fi
fi
case "$CMD" in
  install) cmd_install ;;
  update) cmd_update ;;
esac
