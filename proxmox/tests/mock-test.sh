#!/usr/bin/env bash
# Dry run of proxmox/nuorb-lxc.sh against mocked Proxmox commands.
#
#   proxmox/tests/mock-test.sh
#
# pct, pveam, pvesm, pvesh, pveversion, whiptail, id, dpkg and sleep are
# replaced by small scripts that log every call. Nothing touches a real host.
# Interactive dialogs run in a pseudo terminal (script(1)) with scripted answers.
# The mocks are written in single quotes on purpose: they expand when they run.
# shellcheck disable=SC2016
set -Eeuo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SCRIPT="$HERE/../nuorb-lxc.sh"
BASE="${NUORB_TEST_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/nuorb-lxc-test}"
rm -rf "$BASE"; mkdir -p "$BASE/bin"
BIN="$BASE/bin"
export MOCK_LOG="$BASE/calls.log" MOCK_STATE="$BASE/state"

# ------------------------------------------------------------------ mocks
mk() { printf '#!/usr/bin/env bash\n%s\n' "$2" > "$BIN/$1"; chmod +x "$BIN/$1"; }
mk id 'if [ "${1:-}" = -u ]; then echo "${MOCK_UID:-0}"; else exec /usr/bin/id "$@"; fi'
mk dpkg 'if [ "${1:-}" = --print-architecture ]; then echo "${MOCK_ARCH:-amd64}"; else exit 1; fi'
mk sleep ':'
mk pveversion 'echo "pve-manager/${MOCK_PVE:-8.4.1}/2a5fa54a8503f96d (running kernel: 6.8.12-4-pve)"'
mk pvesh 'echo "pvesh $*" >> "$MOCK_LOG"
if [ "$2" = /cluster/nextid ]; then
  if [ "${3:-}" = --vmid ]; then case " ${MOCK_USED_IDS:-} " in *" $4 "*) echo "400 VM $4 already exists" >&2; exit 2 ;; esac; echo "$4"
  else echo 105; fi
fi'
mk pvesm 'echo "pvesm $*" >> "$MOCK_LOG"
if [ "$1 $2" = "status -content" ]; then
  echo "Name             Type     Status           Total            Used       Available        %"
  if [ "$3" = rootdir ]; then
    echo "local-lvm     lvmthin     active       100000000         5000000        95000000    5.00%"
    echo "tank          zfspool     active       500000000        10000000       490000000    2.00%"
  else echo "local             dir     active        50000000        10000000        40000000   20.00%"; fi
elif [ "$1 $2" = "status -storage" ]; then
  echo "Name             Type     Status           Total            Used       Available        %"
  echo "$3     lvmthin     active       100000000         5000000        ${MOCK_FREE_KB:-95000000}    5.00%"
fi'
mk pveam 'echo "pveam $*" >> "$MOCK_LOG"
case "$1" in
  list) echo "NAME                                                         SIZE"
        [ -n "${MOCK_TEMPLATE:-}" ] && echo "local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst                    120.29MB" ;;
  available) printf "system          debian-11-standard_11.7-1_amd64.tar.zst\nsystem          debian-12-standard_12.2-1_amd64.tar.zst\nsystem          debian-12-standard_12.12-1_amd64.tar.zst\nsystem          debian-13-standard_13.1-2_amd64.tar.zst\n" ;;
esac'
mk pct 'echo "pct $*" >> "$MOCK_LOG"
case "$1" in
  list) echo "VMID       Status     Lock         Name"; [ -n "${MOCK_CTS:-}" ] && printf "%s\n" $MOCK_CTS | sed "s/,/ /g" ;;
  config) case " ${MOCK_NUORB_IDS:-} " in *" $2 "*) echo "tags: docker;nuorb" ;; *) echo "tags: other" ;; esac ;;
  status) case " ${MOCK_CT_IDS:-} ${MOCK_NUORB_IDS:-} ${MOCK_CREATED:-} " in *" $2 "*) echo "status: ${MOCK_CT_STATUS:-running}" ;; *) [ -f "$MOCK_STATE.created" ] && { echo "status: running"; exit 0; }; echo "Configuration file does not exist" >&2; exit 2 ;; esac ;;
  create) touch "$MOCK_STATE.created" ;;
  exec)
    shift 2; [ "$1" = -- ] && shift
    case "$*" in
      "getent hosts"*) exit 0 ;;
      "ip -4 -o addr"*) echo "2: eth0    inet ${MOCK_CT_IP:-192.168.1.50}/24 brd 192.168.1.255 scope global dynamic eth0" ;;
      "test -x /usr/local/bin/update") [ -n "${MOCK_HAS_UPDATE:-}" ]; exit ;;
      "docker exec nuorb cat"*) echo "${MOCK_CODE-K7QP-3XMD}" ;;
      sed*) : ;;
      *ct-setup.sh*) echo ":: ct-setup (mock)"; [ "${MOCK_FAIL:-}" = ct-setup ] && { echo "E: Unable to locate package docker-ce"; exit 100; }; exit 0 ;;
      *nuorb-install.sh*) echo "install.sh (mock): $*"; [ "${MOCK_FAIL:-}" = install ] && exit 1; exit 0 ;;
      *usr/local/bin/update*) echo "update (mock): $*"; exit 0 ;;
      *) echo "unexpected pct exec: $*" >&2; exit 99 ;;
    esac ;;
esac
exit 0'
# whiptail: answers from $MOCK_WT, one per call; "!cancel" = Cancel, "yes"/"no" for --yesno
mk whiptail 'echo "whiptail $*" >> "$MOCK_LOG"
n=$(cat "$MOCK_STATE.wt" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$MOCK_STATE.wt"
a=$(sed -n "${n}p" "$MOCK_WT")
case "$*" in *--yesno*) [ "$a" = yes ]; exit ;; esac
[ "$a" = "!cancel" ] && exit 1
[ "$a" = "=" ] && a=""
printf "%s" "$a" >&2'
mk ip 'if [ "$*" = "-o link show type bridge" ]; then printf "4: vmbr0: <BROADCAST> mtu 1500\n7: vmbr1: <BROADCAST> mtu 1500\n"; else exec /usr/bin/ip "$@"; fi'

# ------------------------------------------------------------------ helpers
PASS=0; FAIL=0
OUT="$BASE/out.txt"
reset() { rm -f "$MOCK_LOG" "$MOCK_STATE".*; : > "$MOCK_LOG"; }
runit() {   # runit [ENV=VAL...] -- ARGS : non interactive run, sets RC
  local envs=()
  while [ "$1" != -- ]; do envs+=("$1"); shift; done; shift
  reset
  set +e
  env PATH="$BIN:$PATH" NUORB_LXC_LOG="$BASE/lxc.log" LANG=C.UTF-8 LC_ALL=C.UTF-8 "${envs[@]}" bash "$SCRIPT" "$@" > "$OUT" 2>&1 < /dev/null
  RC=$?
  set -e
}
runtty() {  # runtty ANSWERFILE [ENV=VAL...] -- ARGS : in a pseudo terminal with whiptail answers
  local ans="$1"; shift
  local envs=()
  while [ "$1" != -- ]; do envs+=("$1"); shift; done; shift
  reset
  local cmd; cmd=$(printf '%q ' env PATH="$BIN:$PATH" NUORB_LXC_LOG="$BASE/lxc.log" MOCK_WT="$ans" LANG=C.UTF-8 LC_ALL=C.UTF-8 TERM=xterm "${envs[@]}" bash "$SCRIPT" "$@")
  set +e
  script -qec "$cmd" /dev/null > "$OUT" 2>&1 < /dev/null
  RC=$?
  set -e
}
check() {   # check NAME CONDITION...
  local name="$1"; shift
  if "$@"; then PASS=$((PASS + 1)); printf '  ok    %s\n' "$name"
  else FAIL=$((FAIL + 1)); printf '  FAIL  %s\n' "$name"; sed 's/^/        | /' "$OUT" | tail -n 15; fi
}
called() { grep -qE -- "$1" "$MOCK_LOG"; }
not_called() { ! grep -qE -- "$1" "$MOCK_LOG"; }
said() { grep -qE -- "$1" "$OUT"; }
rc_is() { [ "$RC" = "$1" ]; }
answers() { local f="$BASE/answers.$1"; shift; printf '%s\n' "$@" > "$f"; echo "$f"; }

echo "nuorb-lxc.sh mock tests ($BASE)"

# ------------------------------------------------------------------ install, defaults
runit -- --yes
check "install --yes ends with 0" rc_is 0
check "template list updated and Debian 12 downloaded (newest)" called 'pveam download local debian-12-standard_12\.12-1_amd64\.tar\.zst'
check "pct create with spec defaults" called 'pct create 105 local:vztmpl/debian-12-standard_12\.12-1_amd64\.tar\.zst --hostname nuorb --ostype debian --unprivileged 1 --features nesting=1,keyctl=1 --cores 4 --memory 6144 --swap 512 --rootfs local-lvm:24 --net0 name=eth0,bridge=vmbr0,ip=dhcp --onboot 1 --timezone host --tags nuorb'
check "container started" called '^pct start 105$'
check "ct-setup.sh copied and run" called 'pct push 105 .*ct-setup\.sh /root/ct-setup\.sh'
check "install.sh: --yes, no firewall, lang, IP, no brain, ports" called "nuorb-install\.sh.* _ https://raw\.githubusercontent\.com/Anarki-LNX/nuorb/main/install\.sh en 192\.168\.1\.50 none 8443,8444"
check "summary with admin URL and setup code" said 'https://192\.168\.1\.50:8444'
check "summary shows setup code" said 'K7QP-3XMD'
check "summary mentions pairing" said 'NuOrb app'
check "description set with addresses" called 'pct set 105 --description'

# ------------------------------------------------------------------ template present, options
runit MOCK_TEMPLATE=1 -- --yes --lang de --ctid 120 --hostname orb --cores 2 --ram 4096 --disk 16 --storage tank --bridge vmbr1 --ip 192.168.1.60/24 --gw 192.168.1.1 --vlan 20 --llm 192.168.1.50:11434 --ports 9443,9444
check "options: ends with 0" rc_is 0
check "existing template used, nothing downloaded" not_called 'pveam (download|update)'
check "options reach pct create" called 'pct create 120 local:vztmpl/debian-12-standard_12\.7-1_amd64\.tar\.zst --hostname orb .* --cores 2 --memory 4096 .* --rootfs tank:16 --net0 name=eth0,bridge=vmbr1,ip=192\.168\.1\.60/24,gw=192\.168\.1\.1,tag=20 '
check "static IP, language, brain URL and ports reach install.sh" called 'install\.sh de 192\.168\.1\.60 http://192\.168\.1\.50:11434 9443,9444'
check "German texts" said 'läuft in Container 120'
check "no DHCP tip with a static IP" bash -c "! grep -q 'DHCP-Reservierung' '$OUT'"

# ------------------------------------------------------------------ refusals
runit MOCK_ARCH=arm64 -- --yes
check "arm64 host refused with clear message" bash -c "[ $RC = 1 ] && grep -q 'amd64 (x86_64) only' '$OUT'"
check "arm64: nothing created" not_called 'pct create'
runit MOCK_PVE=7.4-3 -- --yes
check "Proxmox VE 7 refused" bash -c "[ $RC = 1 ] && grep -q 'too old' '$OUT'"
runit MOCK_UID=1000 -- --yes
check "non root refused" bash -c "[ $RC = 1 ] && grep -q 'as root' '$OUT'"
runit -- --yes --ip 192.168.1.60/24
check "static IP without gateway refused" bash -c "[ $RC = 1 ] && grep -q 'needs a gateway' '$OUT'"
runit -- --yes --ip 192.168.1.300/24 --gw 192.168.1.1
check "invalid IP refused" bash -c "[ $RC = 1 ] && grep -q 'IP: dhcp or' '$OUT'"
runit -- --yes --ram 1024
check "too little RAM refused" bash -c "[ $RC = 1 ] && grep -q 'RAM: at least' '$OUT'"
runit MOCK_USED_IDS=130 -- --yes --ctid 130
check "used ID refused" bash -c "[ $RC = 1 ] && grep -q 'already in use' '$OUT'"
check "used ID: nothing created" not_called 'pct create'
runit -- --yes --storage nope
check "unknown storage refused" bash -c "[ $RC = 1 ] && grep -q 'cannot hold containers' '$OUT'"
runit -- --bogus
check "unknown option refused" bash -c "[ $RC = 1 ] && grep -q 'Unknown option' '$OUT'"
runit -- --help
check "--help" bash -c "[ $RC = 0 ] && grep -q 'update \[ID\]' '$OUT'"
runit MOCK_FREE_KB=5000000 -- --yes
check "low free space only warns" bash -c "[ $RC = 0 ] && grep -q 'Only 4 GB free' '$OUT'"

# ------------------------------------------------------------------ failure keeps the container (non interactive)
runit MOCK_FAIL=ct-setup -- --yes
check "failed setup: exit code not 0" bash -c "[ $RC != 0 ]"
check "failed setup: log tail shown" said 'Unable to locate package docker-ce'
check "failed setup: container kept, destroy command shown" said 'pct destroy 105 --purge 1'
check "failed setup: not destroyed without asking" not_called '^pct destroy'
runit MOCK_FAIL=install -- --yes
check "failed install.sh: exit code not 0 and log named" bash -c "[ $RC != 0 ] && grep -q 'install.sh failed' '$OUT'"

# ------------------------------------------------------------------ update
runit MOCK_CTS="110,running,nuorb 111,running,web" MOCK_NUORB_IDS=110 MOCK_HAS_UPDATE=1 -- --yes
check "re-run with one NuOrb container updates it" bash -c "[ $RC = 0 ]"
check "update runs /usr/local/bin/update in 110" called 'pct exec 110 -- env NUORB_REF=main /usr/local/bin/update'
check "update creates nothing" not_called 'pct create'
runit MOCK_CTS="110,running,nuorb" MOCK_NUORB_IDS=110 -- update
check "update without update command installs it first" called 'pct push 110 .*ct-setup\.sh'
check "then runs it" called '/usr/local/bin/update'
runit MOCK_CTS="110,stopped,nuorb" MOCK_NUORB_IDS=110 MOCK_CT_STATUS=stopped MOCK_HAS_UPDATE=1 -- update 110
check "update of a stopped container starts it" called '^pct start 110$'
runit MOCK_CTS="110,running,nuorb 112,running,nuorb2" MOCK_NUORB_IDS="110 112" -- --yes
check "several NuOrb containers: asks for the ID" bash -c "[ $RC = 1 ] && grep -q 'update <ID> or install' '$OUT'"
runit MOCK_CTS="110,running,nuorb" MOCK_NUORB_IDS=110 -- install --yes
check "explicit install creates a new one next to it" called 'pct create 105'
runit -- update 999
check "update of a missing container refused" bash -c "[ $RC = 1 ] && grep -q 'does not exist' '$OUT'"

# ------------------------------------------------------------------ dialogs (pseudo terminal)
if command -v script >/dev/null; then
  A=$(answers std de standard yes)
  runtty "$A" --
  check "dialog standard: ends with 0" rc_is 0
  check "dialog standard: language asked, German chosen" bash -c "grep -q 'Language / Sprache' '$MOCK_LOG' && grep -q 'install\.sh de ' '$MOCK_LOG'"
  check "dialog standard: defaults created" called '--cores 4 --memory 6144 --swap 512 --rootfs local-lvm:24'

  A=$(answers adv en advanced 140 orb2 6 8192 32 tank vmbr0 192.168.1.70/24 192.168.1.1 = 8443,8444 http://192.168.1.50:8080 yes)
  runtty "$A" --
  check "dialog advanced: ends with 0" rc_is 0
  check "dialog advanced: values reach pct create" called 'pct create 140 .* --hostname orb2 .* --cores 6 --memory 8192 .* --rootfs tank:32 --net0 name=eth0,bridge=vmbr0,ip=192\.168\.1\.70/24,gw=192\.168\.1\.1 '
  check "dialog advanced: brain URL reaches install.sh" called 'install\.sh en 192\.168\.1\.70 http://192\.168\.1\.50:8080 8443,8444'

  A=$(answers cancel en '!cancel')
  runtty "$A" --
  check "dialog cancel: ends with 0, nothing created" bash -c "[ $RC = 0 ] && ! grep -q 'pct create' '$MOCK_LOG' && grep -q 'Cancelled' '$OUT'"

  A=$(answers no en standard no)
  runtty "$A" --
  check "dialog: No at the summary creates nothing" bash -c "[ $RC = 0 ] && ! grep -q 'pct create' '$MOCK_LOG'"

  A=$(answers menu 110)
  runtty "$A" MOCK_CTS="110,running,nuorb" MOCK_NUORB_IDS=110 MOCK_HAS_UPDATE=1 --
  check "dialog: existing container offered, update chosen" bash -c "[ $RC = 0 ] && grep -q '/usr/local/bin/update' '$MOCK_LOG' && ! grep -q 'pct create' '$MOCK_LOG'"

  A=$(answers menunew new en standard yes)
  runtty "$A" MOCK_CTS="110,running,nuorb" MOCK_NUORB_IDS=110 --
  check "dialog: existing container, new one chosen" called 'pct create 105'

  A=$(answers faildel en standard yes yes)
  runtty "$A" MOCK_FAIL=ct-setup --
  check "dialog: failed setup, delete confirmed" bash -c "[ $RC != 0 ] && grep -q '^pct destroy 105 --purge 1' '$MOCK_LOG'"

  A=$(answers failkeep en standard yes no)
  runtty "$A" MOCK_FAIL=ct-setup --
  check "dialog: failed setup, kept on No" bash -c "[ $RC != 0 ] && ! grep -q '^pct destroy' '$MOCK_LOG'"
else
  echo "  (script(1) missing, dialog tests skipped)"
fi

# ------------------------------------------------------------------ texts
check "no en or em dashes in the Proxmox scripts" bash -c "! grep -nP '[\\x{2013}\\x{2014}]' '$HERE/../nuorb-lxc.sh' '$HERE/../ct-setup.sh' '$HERE/../build-template.sh' 2>/dev/null"
check "no private addresses (only 192.168.1.x examples)" bash -c "! grep -nE '\b(10|172\.(1[6-9]|2[0-9]|3[01])|192\.168)\.[0-9]+\.[0-9]+' '$HERE/../nuorb-lxc.sh' '$HERE/../ct-setup.sh' | grep -vE '192\.168\.1\.(1|50|255)\b'"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
