# Oberfläche umschaltbar: "cage" = NuOrb ist die einzige Oberfläche (Kiosk-Compositor, kein Phosh)
#                         "phosh" = bisheriger Stand (Phosh + Epiphany-Web-App), Rückfall
{ config, lib, pkgs, ... }:
let
  cfg = config.nuorb;
  site = import ./site.nix;
  nuorbUrl = "https://${site.nuorbHost}:8443/";
  shellUrl = "http://127.0.0.1:8770/";
  notfallUrl = "http://127.0.0.1:8765/notfall";

  kioskCage = pkgs.writeShellScript "nuorb-kiosk-cage" ''
    export PATH=${lib.makeBinPath (with pkgs; [ curl wtype wlr-randr coreutils procps epiphany util-linux grim ])}:$PATH
    wlr-randr --output DSI-1 --scale 2.5 || true
    # Display an/aus über den Gerätedienst (root); Ursprung = lokale Notfallseite (erlaubt)
    bildschirm() {
      curl -sf --max-time 3 -H 'Origin: http://127.0.0.1:8765' -H 'Content-Type: application/json' \
        -d "{\"an\": $1}" http://127.0.0.1:8765/api/bildschirm >/dev/null || true
    }
    # Ist unten die helle Epiphany-Leiste (Titel/Adresse/Navigation) zu sehen? Pixel bei (10,955) logisch.
    leiste() {
      set -- $(grim -g "10,955 1x1" -t ppm - 2>/dev/null | tail -c 3 | od -An -tu1)
      [ -n "$3" ] && [ $(($1 + $2 + $3)) -gt 450 ]
    }
    # Zwei Web-Apps (Epiphany-Web-App-Modus: stabil, ohne Adressleiste; Normalmodus stürzte unter cage ab):
    #   nuorb  = https://NUORB_SERVER_IP:8443/   notfall = lokale Seite des Gerätedienstes
    app() {  # $1=id $2=url
      D=$HOME/.local/share/org.gnome.Epiphany.WebApp_$1
      mkdir -p "$D"; touch "$D/.app"
      printf '[Desktop Entry]\nName=NuOrb\nExec=epiphany --application-mode --profile=%s %s\nType=Application\nStartupWMClass=org.gnome.Epiphany.WebApp_%s\n' "$D" "$2" "$1" > "$D/org.gnome.Epiphany.WebApp_$1.desktop"
      echo "$D"
    }
    J=$(app nuorb ${shellUrl})
    N=$(app notfall ${notfallUrl})
    cat > "$J/permissions.ini" <<EOD
    [org/gnome/epiphany/permissions/http/127.0.0.1/8770]
    audio-device-permission='allow'
    autoplay-permission='allow'
    notifications-permission='allow'
    EOD
    while true; do
      # NuOrb erreichbar? Sonst Notfallseite (WLAN an / Neustart); die beendet sich selbst über
      # /api/kiosk-neu, sobald NuOrb wieder antwortet -> diese Schleife startet dann NuOrb.
      prof=$N; url=${notfallUrl}
      for i in $(seq 1 15); do
        # nuorb-shell liefert die UI lokal (auch offline mit WLAN-Knopf); Notfallseite nur, wenn die Shell fehlt
        curl -sf --max-time 2 ${shellUrl}shell/status >/dev/null && { prof=$J; url=${shellUrl}; break; }
        sleep 2
      done
      # cage erbt von systemd die Ambient-Capability CAP_WAKE_ALARM; bubblewrap (WebKit-Sandbox) bricht dann ab
      # ("Unexpected capabilities but not setuid") -> vor dem Start alle vererbbaren Capabilities verwerfen
      # Browser-Optik verbergen: Display dunkel, bis die Seite im Element-Vollbild ist
      bildschirm false
      setpriv --inh-caps=-all --ambient-caps=-all epiphany --application-mode --profile="$prof" "$url" &
      pid=$!
      # 1) warten, bis das Epiphany-Fenster da ist (helle Leiste unten), höchstens 30 s
      for i in $(seq 1 60); do leiste && break; sleep 0.5; done
      # 2) F13 = Nutzergeste -> Seite geht ins Vollbild; wiederholen, bis die Leiste weg ist (höchstens 30 s)
      for i in $(seq 1 60); do leiste || break; wtype -k F13 2>/dev/null; sleep 0.5; done
      # 3) Epiphany-Hinweis "ESC drücken …" abwarten, dann Display an (in jedem Fall, auch nach Zeitüberschreitung)
      sleep 4.5
      bildschirm true
      # Danach alle 2 s prüfen: Leiste wieder sichtbar (z. B. nach Selbst-Update der UI) -> F13
      while kill -0 $pid 2>/dev/null; do
        leiste && wtype -k F13 2>/dev/null
        sleep 2
      done
      wait $pid
      sleep 1
    done
  '';
in
{
  options.nuorb.oberflaeche = lib.mkOption {
    type = lib.types.enum [ "cage" "phosh" ];
    default = "cage";
    description = "Grafische Oberfläche des Handys.";
  };

  config = lib.mkMerge [
    (lib.mkIf (cfg.oberflaeche == "phosh") {
      services.desktopManager.phosh = {
        enable = true;
        user = "nuorb";
        group = "users";
        phocConfig.outputs.DSI-1.scale = 2.5;
        # Unverändertes phosh aus cache.nixos.org (gmobile-Panel-Patch würde unter qemu gebaut, g-ir-scanner scheitert)
        package = lib.mkForce pkgs.phosh;
      };
    })

    (lib.mkIf (cfg.oberflaeche == "cage") {
      services.cage = {
        enable = true;
        user = "nuorb";
        program = "${kioskCage}";
        extraArguments = [ "-d" ];
        environment = {
          XKB_DEFAULT_LAYOUT = "de";
          GTK_THEME = "Adwaita:dark";
        };
      };
      systemd.services."cage-tty1" = {
        after = [ "nuorb-geraet.service" "NetworkManager.service" ];
        wants = [ "nuorb-geraet.service" ];
      };
      environment.systemPackages = with pkgs; [ wlr-randr wtype ];
    })
  ];
}
