{ config, lib, pkgs, modulesPath, ... }:
{
  imports = [ ./kiosk.nix ./admin-ctl.nix ./geraet.nix ./oberflaeche.nix ];  # usb-fallback.nix: nur ohne WLAN nötig

  # ---------- Geraet ----------
  hardware.courbet = {
    zapShader = ./firmware/a615_zap.mbn; # proprietär, aus der eigenen vendor-Partition extrahieren (nicht im Repo)
    ipaFirmware = ./firmware/ipa_fws.mbn; # dito
    sensors.enable = true;
    chargeLimit = {
      enable = true; # Dauerbetrieb am Netzteil -> Akku schonen
      start = 60;
      stop = 80;
    };
  };

  # Rootfs auf der (ehemaligen Android-)userdata-Partition, waechst beim Booten auf volle Groesse
  fileSystems."/" = {
    device = "/dev/disk/by-label/jarvis-root";
    fsType = "ext4";
    autoResize = true;
  };
  boot.growPartition = false;

  # Erststart: Store-Datenbank aus dem Image laden und System-Profil anlegen (wie sd-image)
  boot.postBootCommands = ''
    if [ -f /nix-path-registration ]; then
      ${config.nix.package.out}/bin/nix-store --load-db < /nix-path-registration
      touch /etc/NIXOS
      ${config.nix.package.out}/bin/nix-env -p /nix/var/nix/profiles/system --set /run/current-system
      rm -f /nix-path-registration
    fi
  '';

  system.build.rootfsImage = pkgs.callPackage (modulesPath + "/../lib/make-ext4-fs.nix") {
    storePaths = [ config.system.build.toplevel ];
    volumeLabel = "jarvis-root";
    populateImageCommands = ''
      mkdir -p ./files/etc
    '';
  };

  zramSwap.enable = true;

  # ---------- System ----------
  networking.hostName = "jarvis-handy";
  networking.networkmanager.enable = true;
  networking.firewall.allowedTCPPorts = [ 22 ];
  # iptables-Firewall scheitert (Kernel ohne xt_pkttype) -> nftables-Backend
  networking.nftables.enable = true;
  networking.firewall.trustedInterfaces = [ "usb0" ];

  time.timeZone = "Europe/Berlin";
  i18n.defaultLocale = "de_DE.UTF-8";
  console.keyMap = "de";
  services.xserver.xkb.layout = "de";

  nix.settings = {
    experimental-features = [ "nix-command" "flakes" ];
    trusted-users = [ "root" "jarvis" ];
  };

  # ---------- Benutzer ----------
  users.mutableUsers = true;
  users.users.jarvis = {
    isNormalUser = true;
    description = "JARVIS";
    extraGroups = [ "wheel" "networkmanager" "video" "audio" "input" "feedbackd" "dialout" ];
    hashedPassword = lib.removeSuffix "\n" (builtins.readFile ./jarvis.hash); # mkpasswd -m sha-512 > jarvis.hash (nicht im Repo)
    openssh.authorizedKeys.keyFiles = [ ./ssh-jarvis.pub ]; # eigener Public Key (nicht im Repo)
  };
  users.users.root.openssh.authorizedKeys.keyFiles = [ ./ssh-jarvis.pub ];
  security.sudo.wheelNeedsPassword = false;

  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      PermitRootLogin = "prohibit-password";
    };
  };

  # ---------- Oberflaeche ----------
  # Oberfläche: siehe oberflaeche.nix (jarvis.oberflaeche = "cage" | "phosh")


  services.pipewire = {
    enable = true;
    alsa.enable = true;
    pulse.enable = true;
    wireplumber.enable = true;
    # Mikrofon: PipeWire wählte S24LE -> stark verzerrtes Signal (STT leer). S16LE wie beim Lautsprecher.
    # Auf dem Gerät per Lautsprecher->Mikrofon->STT-Schleife bestätigt (2026-11-24).
    wireplumber.extraConfig."52-courbet-mic" = {
      "monitor.alsa.rules" = [
        {
          matches = [ { "node.name" = "~alsa_input.platform-sound.*"; } ];
          actions.update-props."audio.format" = "S16LE";
        }
      ];
    };
  };
  security.rtkit.enable = true;
  hardware.bluetooth.enable = true;
  hardware.graphics.enable = true;

  # Kiosk-Vorbereitung: Browser fuer die JARVIS-Oberflaeche (JARVIS_HOST)
  environment.systemPackages = with pkgs; [
    epiphany
    gnome-console
    htop
    git
    vim
    pciutils
    usbutils
    alsa-utils
    libqmi
  ];

  fonts.packages = with pkgs; [ noto-fonts noto-fonts-color-emoji ];

  documentation.enable = false;
  system.stateVersion = "26.11";
}
