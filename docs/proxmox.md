# NuOrb on Proxmox VE (LXC)

[Deutsch](proxmox.de.md) · [Install guide](../INSTALL.md)

If you run [Proxmox VE](https://www.proxmox.com/en/proxmox-virtual-environment), NuOrb can live in its own
container (LXC) next to your other guests. You get the same NuOrb as with the Docker installer, but in a CT that you
back up, move and delete with the usual Proxmox tools.

There are two ways:

| | Way A: one-liner | Way B: ready-made template |
|---|---|---|
| How | one command in the Proxmox host shell, a dialog asks for the settings | download a template file (~150 MB), create the CT yourself (shell or web UI) |
| Good for | most people | your own automation, people who want to see every step |
| Docker inside the CT | installed by the script | already included |

Both give you the same result: an unprivileged Debian 12 container with Docker and NuOrb, admin panel on port
**8444**, app/UI on port **8443**. Inside the CT NuOrb is installed with the normal
[installer](../INSTALL.md): same image, Compose folder `/root/nuorb`, Docker container `nuorb`.

## 1. Requirements

| | Minimum |
|---|---|
| Proxmox VE | version 8 or newer, host on **amd64** (x86_64). ARM hosts are not supported; the script stops with a clear message. |
| Free resources | 4 CPU cores, 6 GB RAM, 24 GB disk on a storage for containers (e.g. `local-lvm`, `local-zfs`) |
| Network | a bridge (default `vmbr0`) with DHCP in your home network, or a free static IP |
| Internet | for the CT on its first start: NuOrb image (~1.5 GB) and speech models (~530 MB) |
| Brain | an [Ollama](https://ollama.com) server or any OpenAI-compatible server (llama.cpp, vLLM, LM Studio) **or** an [Anthropic API key](https://console.anthropic.com) (Claude), or both |

All values can be changed. NuOrb itself needs about 4 GB RAM; the rest is headroom for speech recognition and
updates.

The container is **unprivileged** with the features `nesting=1` and `keyctl=1`. Both are needed because NuOrb runs as
a Docker container inside the CT. The one-liner sets them for you; with the template you tick them yourself.

## 2. Way A: one-liner (recommended)

Open the shell of your Proxmox **host** (web UI: click the node, then *Shell*, or SSH as root) and run:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/proxmox/nuorb-lxc.sh)"
```

Run it on the host, not inside an existing container or VM.

The script:

1. checks that it runs as root on a Proxmox VE 8+ host with amd64;
2. asks for the language, then *Default* or *Advanced*. *Default* uses: next free CT ID, hostname `nuorb`, 4 cores,
   6 GB RAM, 24 GB disk, DHCP on `vmbr0`, ports 8443/8444. *Advanced* lets you change ID, hostname, cores, RAM, disk,
   storage, bridge, static IP and gateway, VLAN, ports and your language model server (e.g. Ollama);
3. shows a summary and asks for your OK;
4. downloads the Debian 12 template if it is missing, creates and starts the CT (tag `nuorb`, start at boot, time
   zone of the host), installs Docker and NuOrb;
5. waits until NuOrb is ready and shows **the admin address, the app address and the setup code**.

The whole run takes about 5 to 10 minutes, mostly downloads. Everything is logged on the host in
`/var/log/nuorb-lxc.log`. If something fails during setup, the script asks whether to delete the unfinished CT
(default: no, so you can look inside).

> Before running a script from the internet as root, read it:
> [`proxmox/nuorb-lxc.sh`](../proxmox/nuorb-lxc.sh).

### Without dialog

All settings are also available as options. Add `_` and the options after the command:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/proxmox/nuorb-lxc.sh)" _ --yes --ctid 120
```

| Option | Meaning |
|---|---|
| `--yes` | no questions, take defaults for everything not given |
| `--lang de\|en` | language of the script and of NuOrb |
| `--ctid 120` | CT ID (default: next free one) |
| `--hostname nuorb` | hostname |
| `--cores 4` · `--ram 6144` · `--disk 24` | cores, RAM in MB, disk in GB |
| `--storage local-lvm` | storage for the disk (default `local-lvm`, `local-zfs` or the first suitable one) |
| `--template-storage local` | storage for the Debian template |
| `--bridge vmbr0` · `--vlan 10` | network bridge, optional VLAN tag |
| `--ip dhcp` or `--ip 192.168.1.50/24 --gw <router>` | DHCP or static IP with gateway |
| `--llm http://192.168.1.50:11434` | your language model server (Ollama or OpenAI-compatible) |
| `--ports 8443,8444` | ports for app/UI and admin panel |

## 3. Way B: download the template

The template is built automatically for every release. It already contains Debian 12 and Docker. The NuOrb image
itself is not inside (it would make the file more than 20 times bigger); the CT downloads it on its first start.

You find it at **https://github.com/Anarki-LNX/nuorb/releases/latest**:

- `nuorb-lxc-<version>-amd64.tar.zst` (the template, ~150 MB)
- `nuorb-lxc-<version>-amd64.tar.zst.sha256` (its checksum)
- `nuorb-lxc-<version>-amd64.packages.txt` (list of the Debian packages inside, for the curious)

### 3.1 Download and check on the host

In the Proxmox host shell (replace `<version>` with the version shown on the release page, e.g. `0.7.0`):

```bash
VER=<version>
cd /var/lib/vz/template/cache
wget https://github.com/Anarki-LNX/nuorb/releases/download/v$VER/nuorb-lxc-$VER-amd64.tar.zst
wget https://github.com/Anarki-LNX/nuorb/releases/download/v$VER/nuorb-lxc-$VER-amd64.tar.zst.sha256
sha256sum -c nuorb-lxc-$VER-amd64.tar.zst.sha256
```

The last command must print `OK`. If it prints `FAILED`, delete both files and download again. Never use a template
whose checksum does not match.

`/var/lib/vz/template/cache` is the template folder of the storage `local`. If you keep templates on another storage,
use its `template/cache` folder instead.

Downloaded on another computer? Check it there (`sha256sum -c …`, on Windows
`Get-FileHash nuorb-lxc-<version>-amd64.tar.zst`) and upload it in the web UI: storage `local` →
*CT Templates* → *Upload*.

### 3.2 Create the container in the shell

```bash
pct create 120 local:vztmpl/nuorb-lxc-$VER-amd64.tar.zst \
  --hostname nuorb --ostype debian --unprivileged 1 --features nesting=1,keyctl=1 \
  --cores 4 --memory 6144 --swap 512 --rootfs local-lvm:24 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp --onboot 1 --tags nuorb
pct start 120
```

- `120` is the CT ID; take any free one (`pvesh get /cluster/nextid` shows the next free ID).
- `local-lvm` is the storage for the disk; use yours (e.g. `local-zfs`).
- Static IP instead of DHCP: `--net0 name=eth0,bridge=vmbr0,ip=192.168.1.50/24,gw=<your router>`.
- The tag `nuorb` lets the one-liner find this CT later for updates.

### 3.3 Or create it in the web UI

1. *Create CT* (top right).
2. **General:** CT ID and hostname (`nuorb`), keep *Unprivileged container* ticked, set a root password (the
   template has none and no SSH server; without a password you get in with `pct enter <ID>` on the host).
3. **Template:** storage `local`, template `nuorb-lxc-<version>-amd64.tar.zst`.
4. **Disks:** 24 GB. **CPU:** 4 cores. **Memory:** 6144 MB, swap 512 MB.
5. **Network:** bridge `vmbr0`, IPv4 *DHCP* (or a static address).
6. Finish **without** *Start after created*.
7. Select the new CT → *Options* → *Features* → tick **keyctl** and **Nesting** → OK.
8. *Options* → *Start at boot* → Yes (recommended). Then *Start*.

Without step 7 Docker cannot start inside the CT and NuOrb stays offline.

### 3.4 First start of the template

On its first start the CT downloads the NuOrb image and the speech models and sets NuOrb up (service
`nuorb-firstboot`). This needs internet and takes a few minutes. Follow it on the host:

```bash
pct exec 120 -- tail -f /var/log/nuorb-firstboot.log
```

The template starts in English; you choose the language in the setup wizard.

## 4. First start

1. Find the IP: in the web UI under the CT → *Summary*, or on the host: `pct exec 120 -- hostname -I`.
   When you log in to the CT (`pct enter 120` or the web UI console), it shows its addresses and the setup code.
2. Open `https://<ct-ip>:8444` (e.g. `https://192.168.1.50:8444`). The browser warns about the certificate:
   expected, NuOrb creates its own. Continue.
3. Enter the **setup code**. Way A shows it at the end. Otherwise read it on the host:
   ```bash
   pct exec 120 -- nuorb-setup-code
   ```
   (only available until a password is set).
4. Choose a password and follow the setup: name, language, voice, **brain**. How to prepare Ollama, llama.cpp,
   vLLM, LM Studio or Claude is described in the [install guide, section 4](../INSTALL.md#4-brain).

**Give the CT a fixed address** (DHCP reservation in your router, or a static IP). NuOrb creates its certificate for
the address it has on the first start, and paired phones remember it.

## 5. Pairing

1. Install the **NuOrb** app on your phone, or use any browser in your home network.
2. Admin panel → *Pair device* → *Create pairing code*.
3. Scan the QR code with the app. The code is valid for 10 minutes and only once.
4. A browser is paired the same way: open `https://<ct-ip>:8443` and enter the code.

Paired devices are listed in the admin panel and can be unpaired there.

## 6. Update

Either way keeps your settings, password, paired devices and memory:

- **Inside the CT:** open the CT console (web UI → CT → *Console*) or run on the host
  ```bash
  pct exec 120 -- /usr/local/bin/update
  ```
  (inside the CT after `pct enter 120` just `update`). It updates Debian and Docker, downloads the new NuOrb image and restarts NuOrb.
- **From the host:** run the one-liner from section 2 again. It finds CTs with the tag `nuorb` and offers *Update*
  or *Create new*. Directly, without the dialog: `bash -c "$(curl -fsSL …/proxmox/nuorb-lxc.sh)" _ update 120`.

A new template on the release page is only needed for new installations. Existing CTs are updated with `update`.

## 7. Backup and restore

NuOrb keeps everything (settings, password, paired devices, memory, models) inside the CT, so a normal Proxmox
backup covers it.

```bash
vzdump 120 --mode snapshot --compress zstd --storage local
```

- In the web UI: CT → *Backup* → *Backup now*, or a scheduled job under *Datacenter* → *Backup*.
- `--mode snapshot` needs a storage that supports snapshots (LVM-thin, ZFS, Ceph). If it fails, use
  `--mode stop` (NuOrb is offline for about a minute).
- Restore: web UI → backup storage → *Backups* → *Restore*, or
  ```bash
  pct restore 121 /var/lib/vz/dump/vzdump-lxc-120-<date>.tar.zst --storage local-lvm
  ```
  Give the restored CT the same IP address as before; otherwise see *IP changed* in section 9.

A backup contains your API keys and conversation memory. Store it like a password file.

## 8. Uninstall

```bash
pct stop 120
pct destroy 120 --purge 1
```

This deletes the CT with all NuOrb data, including the admin password and paired devices. Make a backup first if
you might want it back. `--purge 1` also removes the CT from backup jobs and HA. In the web UI: CT → *More* →
*Remove*.

The downloaded template stays in `/var/lib/vz/template/cache`; delete it there or in the web UI if you no longer
need it.

## 9. Troubleshooting

| Problem | Cause and fix |
|---|---|
| *Run this as root in the shell of the Proxmox VE host.* | Open the host shell (node → *Shell*) or log in as root. |
| *pct not found. This script runs on a Proxmox VE host.* | You ran it inside a CT, a VM or on another computer. Run it in the host shell. |
| *The NuOrb container is available for amd64 (x86_64) only* | Your host is ARM. Use the [Docker installer](../INSTALL.md) in a VM instead. |
| *Proxmox VE … is too old* | Version 8 or newer is needed. Update Proxmox first. |
| Something failed during setup | Look at `/var/log/nuorb-lxc.log` on the host. Then run the one-liner again. |
| CT starts, but NuOrb stays offline | Features missing: `pct set 120 -features nesting=1,keyctl=1`, then `pct reboot 120`. Logs: `pct exec 120 -- docker logs nuorb --tail 50`. |
| Template CT: NuOrb does not appear | First start still running or no internet: `pct exec 120 -- tail -f /var/log/nuorb-firstboot.log`. |
| CT gets no IP | DHCP in the network? Bridge correct (`vmbr0`)? VLAN tag needed? Check the CT's *Network* tab. |
| Template does not appear in *Create CT* | Wrong folder or storage. The storage needs the content type *CT Templates* (*Datacenter* → *Storage* → *Edit*). |
| `sha256sum` says `FAILED` | Download broken or file changed. Delete both files and download again. |
| Setup: speech models stuck, *no internet connection* | The CT has no internet: gateway and DNS of the CT (*Network*, *DNS* tab), Proxmox firewall rules for the CT. |
| Setup code not shown | NuOrb is still starting (1 to 2 minutes). Try `pct exec 120 -- nuorb-setup-code` again. Once a password is set there is no code any more. |
| Forgot the admin password | `pct exec 120 -- nuorb-reset-password` (asks y/N, `--yes` without asking) shows a new setup code; the old password stops working (a copy of the old login data is kept as `auth.json.bak-<time>`). Settings, memory and paired phones stay. |
| Ollama *not reachable* | Ollama must listen on the network and allow the CT's IP in its firewall. The setup shows the exact commands. Details: [INSTALL.md, troubleshooting](../INSTALL.md#8-troubleshooting). |
| CT killed or very slow, *out of memory* in the host log | Too little RAM. Give the CT at least 6 GB: `pct set 120 -memory 6144`. |
| *IP changed*: app shows a certificate error | Best: give the CT its old address back (DHCP reservation). Otherwise add the new IP to `NUORB_HOSTS` in `/root/nuorb/.env` inside the CT, run `cd /root/nuorb && docker compose up -d` there and pair the phones again. |
| `vzdump` snapshot mode fails | Storage without snapshots. Use `--mode stop` or `--mode suspend`. |

## 10. Security

- **Never forward ports 8443 or 8444 on your router.** NuOrb is made for the home network.
- Away from home, connect through a **VPN** into your home network: WireGuard (e.g. on the router or in another CT),
  Tailscale or Headscale. Then the app works as if you were at home.
- The CT is **unprivileged**: root inside the CT is not root on the host. Keep it that way; NuOrb does not need a
  privileged container.
- The template has no root password and no SSH server. Set a strong password if you set one at all; `pct enter`
  from the host is enough for maintenance.
- Optional: limit access with the Proxmox firewall. CT → *Firewall* → *Options* → enable, then two rules
  *IN ACCEPT* for TCP ports 8443 and 8444 with source `192.168.1.0/24` (your home network).
- Keep the Proxmox web UI (port 8006) out of the internet as well.
- Update regularly (section 6). API keys entered in the admin panel stay inside the CT and are shown only masked.
- A backup (section 7) contains keys and memory: keep it private.

Questions or problems: [GitHub issues](https://github.com/Anarki-LNX/nuorb/issues).
