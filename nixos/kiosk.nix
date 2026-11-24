# NuOrb-Kiosk (Phosh variant). Needs ./nuorb-ca.crt = your home CA from ui/make-certs.sh (not in the repo).
#
# Browser: Epiphany (WebKitGTK). Firefox 158 hat auf phoc einen Resize-Bug (Inhalt folgt der
# Fenstergröße nicht, --kiosk greift nicht) – auf dem Gerät am 2026-11-24 per Screenshot bestätigt.
{ config, lib, pkgs, ... }:
let
  site = import ./site.nix;
  nuorbUrl = "https://${site.nuorbHost}:8443/";
  appId = "org.gnome.Epiphany.WebApp_nuorb";
  kiosk = pkgs.writeShellScript "nuorb-kiosk" ''
    export PATH=${lib.makeBinPath [ pkgs.curl pkgs.systemd pkgs.wtype pkgs.coreutils pkgs.procps pkgs.epiphany ]}:$PATH
    # Web-App-Profil fuer Epiphany (ohne Adressleiste) inkl. vorab erteilter Rechte fuer NuOrb
    D=$HOME/.local/share/${appId}
    mkdir -p "$D"
    touch "$D/.app"
    cat > "$D/${appId}.desktop" <<EOD
    [Desktop Entry]
    Name=NuOrb
    Exec=epiphany --application-mode --profile=$D ${nuorbUrl}
    Type=Application
    StartupWMClass=${appId}
    EOD
    cat > "$D/permissions.ini" <<EOD
    [org/gnome/epiphany/permissions/https/${site.nuorbHost}/8443]
    audio-device-permission='allow'
    autoplay-permission='allow'
    notifications-permission='allow'
    EOD
    # warten, bis NuOrb erreichbar ist (WLAN bzw. USB-Tunnel)
    for i in $(seq 1 90); do
      curl -sf --max-time 2 ${nuorbUrl}api/status >/dev/null && break
      sleep 2
    done
    while true; do
      epiphany --application-mode --profile="$D" ${nuorbUrl} &
      pid=$!
      # warten, bis die Sitzung entsperrt ist (nuorb-unlock.service), dann Vollbild
      for i in $(seq 1 60); do
        sid=$(loginctl show-seat seat0 -p ActiveSession --value 2>/dev/null)
        [ -n "$sid" ] && [ "$(loginctl show-session "$sid" -p LockedHint --value 2>/dev/null)" = no ] && break
        sleep 2
      done
      sleep 8
      # F13 = User-Geste -> die NuOrb-UI geht per requestFullscreen ins Element-Vollbild (ohne jede Leiste).
      # KEIN F11: Fenster-Vollbild verhindert das Element-Vollbild in Epiphany (auf dem Geraet getestet).
      wtype -k F13
      sleep 5
      # Vollbild dauerhaft halten: alle 20 s F13 (die UI ignoriert es, wenn schon Vollbild)
      while kill -0 $pid 2>/dev/null; do
        wtype -k F13
        sleep 20
      done
      wait $pid
      sleep 3               # bei Absturz/Schliessen neu starten
    done
  '';
in
{
  security.pki.certificateFiles = [ ./nuorb-ca.crt ];

  environment.systemPackages = [ pkgs.wtype pkgs.epiphany ];

  # Firefox bleibt als Reserve installiert (Policies wie von nuorb-ui vorgeschlagen)
  programs.firefox = {
    enable = true;
    policies = {
      Certificates = {
        ImportEnterpriseRoots = true;
        Install = [ "${./nuorb-ca.crt}" ];
      };
      Permissions = {
        Microphone = { Allow = [ "https://${site.nuorbHost}:8443" ]; Locked = false; };
        Autoplay = { Allow = [ "https://${site.nuorbHost}:8443" ]; Default = "block-audio-video"; };
      };
      DisableTelemetry = true;
      DisableFirefoxStudies = true;
      DisablePocket = true;
      OverrideFirstRunPage = "";
      OverridePostUpdatePage = "";
      DontCheckDefaultBrowser = true;
    };
  };

  # Nur für die Phosh-Oberfläche (Rückfall); cage-Kiosk siehe oberflaeche.nix
  # Phosh startet immer gesperrt; fuer den Assistenten-Dauerbetrieb nach dem Start entsperren
  systemd.services.nuorb-unlock = lib.mkIf (config.nuorb.oberflaeche == "phosh") {
    description = "NuOrb: Phosh-Sitzung nach dem Start entsperren";
    wantedBy = [ "graphical.target" ];
    after = [ "phosh.service" ];
    serviceConfig.Type = "simple";
    script = ''
      for i in $(seq 1 40); do
        sleep 3
        ${pkgs.systemd}/bin/loginctl unlock-sessions || true
      done
    '';
  };

  environment.etc."xdg/autostart/nuorb-kiosk.desktop" = lib.mkIf (config.nuorb.oberflaeche == "phosh") {
    text = ''
      [Desktop Entry]
      Type=Application
      Name=NuOrb
      Exec=${kiosk}
      X-GNOME-Autostart-enabled=true
    '';
  };

  # Kein Sperren/Abdunkeln (Dauerbetrieb als Assistent)
  programs.dconf.profiles.user.databases = [
    {
      settings = {
        "org/gnome/desktop/session".idle-delay = lib.gvariant.mkUint32 0;
        "org/gnome/desktop/screensaver".lock-enabled = false;
        "org/gnome/settings-daemon/plugins/power".sleep-inactive-ac-type = "nothing";
        "org/gnome/epiphany".restore-session-policy = "never";
      };
    }
  ];
}
