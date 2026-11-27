# NuOrb on Proxmox VE (LXC)

[Deutsch](proxmox.de.md) · [Install guide](../INSTALL.md)

If you run [Proxmox VE](https://www.proxmox.com/en/proxmox-virtual-environment), NuOrb can live in its own
container (LXC) next to your other guests. You get the same NuOrb as with the Docker installer, but in a CT that you
back up, move and delete with the usual Proxmox tools.

There are two ways:

| | Way A: one-liner | Way B: ready-made template |
|---|---|---|
| How | one command in the Proxmox host shell, a dialog asks for the settings | download a template file, create the CT yourself (shell or web UI) |
| Good for | most people | offline setups, your own automation, people who want to see every step |
| Internet on the host | yes | only for the download (can be done on another computer) |

Both give you the same result: an unprivileged Debian 12 container with NuOrb, admin panel on port **8444**, app/UI
on port **8443**.

## 1. Requirements

| | Minimum |
|---|---|
| Proxmox VE | 8.x, host on **amd64** (x86_64). ARM hosts are not supported; the script stops with a clear message. |
| Free resources | 4 CPU cores, 6 GB RAM, 24 GB disk on a storage for containers (e.g. `local-lvm`, ZFS) |
| Network | a bridge (default `vmbr0`) with DHCP in your home network, or a free static IP |
| Internet | once, for the container image, NuOrb and the speech models (~530 MB) |
| Brain | an [Ollama](https://ollama.com) server or any OpenAI-compatible server (llama.cpp, vLLM, LM Studio) **or** an [Anthropic API key](https://console.anthropic.com) (Claude), or both |

All values can be changed in the dialog. NuOrb itself needs about 4 GB RAM; the rest is headroom for speech
recognition and updates.

The container is created **unprivileged** with the features `nesting=1` and `keyctl=1`. Both are needed because
NuOrb runs as a Docker container inside the CT. You do not have to set them yourself.

## 2. Way A: one-liner (recommended)

Open the shell of your Proxmox **host** (web UI: click the node, then *Shell*, or SSH as root) and run:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/proxmox/nuorb-lxc.sh)"
```

Run it on the host, not inside an existing container or VM.

The script:

1. checks that it runs on a Proxmox host as root and that the host is amd64;
2. opens a dialog with the defaults: Debian 12, 4 cores, 6 GB RAM, 24 GB disk, DHCP on `vmbr0`, next free CT ID.
   Choose *Default* to accept them or *Advanced* to change ID, hostname, storage, bridge, IP, cores, RAM and disk;
3. downloads the Debian 12 template if it is missing, creates and starts the CT;
4. installs NuOrb inside the CT, waits until it is ready and then shows **the admin address and the setup code**.

The whole run takes about 5 to 10 minutes, mostly downloads.

> Before running a script from the internet as root, read it:
> [`proxmox/nuorb-lxc.sh`](../proxmox/nuorb-lxc.sh).

## 3. Way B: download the template

The template is built automatically for every release. You find it at
**https://github.com/Anarki-LNX/nuorb/releases/latest** as two files:

- `nuorb-lxc-<version>-amd64.tar.zst` (the template)
- `nuorb-lxc-<version>-amd64.tar.zst.sha256` (its checksum)

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
  --net0 name=eth0,bridge=vmbr0,ip=dhcp --onboot 1
pct start 120
```

- `120` is the CT ID; take any free one (`pvesh get /cluster/nextid` shows the next free ID).
- `local-lvm` is the storage for the disk; use yours (e.g. `local-zfs`).
- Static IP instead of DHCP: `--net0 name=eth0,bridge=vmbr0,ip=192.168.1.50/24,gw=<your router>`.

### 3.3 Or create it in the web UI

1. *Create CT* (top right).
2. **General:** CT ID and hostname (`nuorb`), keep *Unprivileged container* ticked, set a root password or SSH key.
3. **Template:** storage `local`, template `nuorb-lxc-<version>-amd64.tar.zst`.
4. **Disks:** 24 GB. **CPU:** 4 cores. **Memory:** 6144 MB, swap 512 MB.
5. **Network:** bridge `vmbr0`, IPv4 *DHCP* (or a static address).
6. Finish **without** *Start after created*.
7. Select the new CT → *Options* → *Features* → tick **keyctl** and **Nesting** → OK.
8. *Options* → *Start at boot* → Yes (recommended). Then *Start*.

Without step 7 Docker cannot start inside the CT and NuOrb stays offline.

## 4. First start

On the first start the container creates its own certificates for its IP address and downloads the speech
models. Give it 1 to 2 minutes.

1. Find the IP: in the web UI under the CT → *Summary*, or on the host: `pct exec 120 -- hostname -I`.
2. Open `https://<ct-ip>:8444` (e.g. `https://192.168.1.50:8444`). The browser warns about the certificate:
   expected, NuOrb creates its own. Continue.
3. Enter the **setup code**. Way A shows it at the end. Otherwise read it on the host:
   ```bash
   pct exec 120 -- nuorb-setup-code
   ```
   (only available until a password is set).
4. Choose a password and follow the setup: name, language, voice, **brain**. How to prepare Ollama, llama.cpp,
   vLLM, LM Studio or Claude is described in the [install guide, section 4](../INSTALL.md#4-brain).

Tip: give the CT a fixed address (DHCP reservation in your router, or a static IP). The certificate and the paired
phones use this address; if it changes, phones have to be paired again.

## 5. Pairing

1. Install the **NuOrb** app on your phone, or use any browser in your home network.
2. Admin panel → *Pair device* → *Create pairing code*.
3. Scan the QR code with the app. The code is valid for 10 minutes and only once.
4. A browser is paired the same way: open `https://<ct-ip>:8443` and enter the code.

Paired devices are listed in the admin panel and can be unpaired there.

## 6. Update

Either way works and keeps your settings, password, paired devices and memory:

- **Inside the CT:** open the CT console (web UI → CT → *Console*) or run on the host
  ```bash
  pct exec 120 -- update
  ```
  It downloads the new NuOrb image and restarts NuOrb.
- **From the host:** run the one-liner from section 2 again and choose the existing CT. It updates instead of
  creating a new one.

Debian updates inside the CT: `pct exec 120 -- bash -c "apt update && apt -y full-upgrade"`.

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
  Restoring to a new ID with a new IP means pairing the phones again (see section 4, tip).

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
| Script: *this host is not amd64* | NuOrb's LXC is only built for amd64. On ARM use the [Docker installer](../INSTALL.md) in a VM. |
| Script: *must run on a Proxmox VE host* | You ran it inside a CT or VM. Run it in the host shell (node → *Shell*). |
| CT starts, but NuOrb stays offline | Features missing: `pct set 120 -features nesting=1,keyctl=1`, then `pct reboot 120`. Logs: `pct exec 120 -- docker logs nuorb --tail 50`. |
| CT gets no IP | DHCP in the network? Bridge correct (`vmbr0`)? VLAN tag needed? Check the CT's *Network* tab. |
| Template does not appear in *Create CT* | Wrong folder or storage. The storage needs the content type *CT Templates* (*Datacenter* → *Storage* → *Edit*). |
| `sha256sum` says `FAILED` | Download broken or file changed. Delete both files and download again. |
| Setup: speech models stuck, *no internet connection* | The CT has no internet: gateway and DNS of the CT (*Network*, *DNS* tab), Proxmox firewall rules for the CT. |
| Setup code not shown | NuOrb is still starting (1 to 2 minutes). Try `pct exec 120 -- nuorb-setup-code` again. Once a password is set there is no code any more. |
| Forgot the admin password | `pct exec 120 -- nuorb-reset-password` prints a new setup code. |
| Ollama *not reachable* | Ollama must listen on the network and allow the CT's IP in its firewall. The setup shows the exact commands. Details: [INSTALL.md, troubleshooting](../INSTALL.md#8-troubleshooting). |
| CT killed or very slow, *out of memory* in the host log | Too little RAM. Give the CT at least 6 GB: `pct set 120 -memory 6144`. |
| Wrong time in answers | Set the time zone in the CT: `pct exec 120 -- timedatectl set-timezone Europe/Berlin`. |
| `vzdump` snapshot mode fails | Storage without snapshots. Use `--mode stop` or `--mode suspend`. |
| App: certificate error after an IP change | The CT got a new address. Restart the CT so NuOrb creates certificates for the new IP, then pair again. Better: a fixed IP. |

## 10. Security

- **Never forward ports 8443 or 8444 on your router.** NuOrb is made for the home network.
- Away from home, connect through a **VPN** into your home network: WireGuard (e.g. on the router or in another CT),
  Tailscale or Headscale. Then the app works as if you were at home.
- The CT is **unprivileged**: root inside the CT is not root on the host. Keep it that way; NuOrb does not need a
  privileged container.
- Optional: limit access with the Proxmox firewall. CT → *Firewall* → *Options* → enable, then two rules
  *IN ACCEPT* for TCP ports 8443 and 8444 with source `192.168.1.0/24` (your home network).
- Keep the Proxmox web UI (port 8006) out of the internet as well.
- Update regularly (section 6). API keys entered in the admin panel stay inside the CT and are shown only masked.
- A backup (section 7) contains keys and memory: keep it private.

Questions or problems: [GitHub issues](https://github.com/Anarki-LNX/nuorb/issues).
