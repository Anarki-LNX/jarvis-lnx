# nixos/: phone configuration (Xiaomi Mi 11 Lite 4G, `courbet`)

NixOS on top of [ElXreno/nixos-courbet](https://github.com/ElXreno/nixos-courbet) (device module, boot image)
and ElXreno's mainline kernel branch `courbet-7.3`.

| File | Purpose |
|---|---|
| `flake.nix`, `flake.lock` | builds `toplevel`, `boot-img`, `rootfs` (ext4, label `nuorb-root`) |
| `site.nix` | **edit first**: address of the backend (`nuorbHost`) |
| `configuration.nix` | base system: charge limit 60-80 %, rootfs on `userdata`, NetworkManager, nftables firewall, SSH (keys only), PipeWire (mic forced to S16LE), German locale |
| `oberflaeche.nix` | UI switch `nuorb.oberflaeche = "cage"` (default, NuOrb is the only UI) or `"phosh"` (fallback) |
| `kiosk.nix` | Phosh-variant kiosk (Epiphany web-app mode), home CA, Firefox policies as reserve |
| `geraet.nix`, `geraet/` | local device service on 127.0.0.1:8765 (Wi-Fi, reboot, power-off, brightness, volume, screen; origin-checked, logged), power-key handler, `nuorb-shell` user service on 127.0.0.1:8770 (local UI copy + proxy), emergency page |
| `admin-ctl.nix` | restricted SSH entry for the admin panel: own user, forced command, key only accepted from `nuorbHost` |
| `steuerung-handy.nix` | optional, not imported: older forced-command SSH entry for voice control (status / generations / reboot / rollback) |
| `usb-fallback.nix` | optional, not imported: reach the backend through the USB cable while there is no Wi-Fi |

## Files you have to provide yourself (not in the repo, git-ignored)

| File | How to create it |
|---|---|
| `nuorb.hash` | `mkpasswd -m sha-512 > nuorb.hash` (password/PIN of user `nuorb`) |
| `ssh-nuorb.pub` | your own SSH public key (root + nuorb) |
| `admin-handy.pub` | public key of the admin panel's phone key (`admin/` creates it on the backend); optional, the module skips it if absent |
| `nuorb-ca.crt` | home CA certificate created by `ui/make-certs.sh` on the backend |
| `firmware/a615_zap.mbn`, `firmware/ipa_fws.mbn` | proprietary Qualcomm blobs: extract them from **your own** device's vendor partition. They are not redistributable and therefore not included. |

Note: a flake only sees files that are tracked by git (or use a `path:` flake reference / a copy outside git).

## Building

The original build ran inside a `nixos/nix` Docker container with qemu-user registered only in a private user
namespace (nothing installed on the host): see `scripts/handy-nixos-build.sh`, `scripts/handy-nixos-build-inner.sh`,
`scripts/handy-userns-binfmt.sh`. The scripts expect this working layout (git-ignored `build/` next to the repo root):

```
build/handy-nixos/     copy of this directory (incl. the private files above)
build/nixos-courbet/   git clone https://github.com/ElXreno/nixos-courbet
build/linux-c0f2fd4/   ElXreno/linux @ c0f2fd4 (branch courbet-7.3)
```

```bash
scripts/handy-nixos-build.sh toplevel boot-img rootfs
```

## Flashing (destructive: read the safety notes in the main README first)

`fastboot boot` (RAM boot) does **not** work on courbet's ABL. What worked:

```bash
fastboot erase dtbo
fastboot flash boot   build/handy-nixos/out/boot-img
fastboot flash userdata build/handy-nixos/out/rootfs   # wipes Android data!
fastboot reboot
```

Afterwards updates go over the network without flashing: `PHONE_HOST=… scripts/handy-deploy.sh`
(`nix copy` + `switch-to-configuration`).
