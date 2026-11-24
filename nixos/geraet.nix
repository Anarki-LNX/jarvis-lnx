# NuOrb-Gerätedienst (nur 127.0.0.1:8765) + Power-Knopf = Bildschirm an/aus.
{ lib, pkgs, ... }:
let
  site = import ./site.nix;
  geraetDir = pkgs.runCommand "nuorb-geraet" { } ''
    mkdir -p $out
    cp ${./geraet/geraetedienst.py} $out/geraetedienst.py
    substitute ${./geraet/notfall.html} $out/notfall.html --replace-fail NUORB_SERVER_IP ${site.nuorbHost}
    cp ${./geraet/nuorb-shell.py} $out/nuorb-shell.py
  '';

  # Power-Knopf (pm8941_pwrkey, KEY_POWER=116): Hintergrundbeleuchtung umschalten
  powerknopf = pkgs.writers.writePython3 "nuorb-powerknopf" { flakeIgnore = [ "E501" ]; } ''
    import glob
    import struct
    import syslog
    import time

    syslog.openlog("nuorb-geraet")
    dev = None
    for d in glob.glob("/sys/class/input/event*"):
        try:
            if open(d + "/device/name").read().strip() == "pm8941_pwrkey":
                dev = "/dev/input/" + d.rsplit("/", 1)[1]
        except OSError:
            pass
    if not dev:
        raise SystemExit("pm8941_pwrkey nicht gefunden")
    bl = sorted(glob.glob("/sys/class/backlight/*"))[0]
    fmt = "llHHi"
    size = struct.calcsize(fmt)
    letzte = 0.0
    with open(dev, "rb") as f:
        while True:
            _, _, typ, code, wert = struct.unpack(fmt, f.read(size))
            if typ == 1 and code == 116 and wert == 1 and time.time() - letzte > 0.4:
                letzte = time.time()
                an = open(bl + "/bl_power").read().strip() == "0"
                open(bl + "/bl_power", "w").write("4" if an else "0")
                syslog.syslog(syslog.LOG_NOTICE, "Power-Knopf: Bildschirm " + ("aus" if an else "an"))
  '';
in
{
  systemd.services.nuorb-geraet = {
    description = "NuOrb-Gerätedienst (lokale API für WLAN, Neustart, Helligkeit, Lautstärke, Bildschirm)";
    wantedBy = [ "multi-user.target" ];
    after = [ "NetworkManager.service" ];
    path = with pkgs; [ networkmanager iproute2 systemd util-linux wireplumber coreutils procps ];
    environment = {
      GERAET_NOTFALL = "${geraetDir}/notfall.html";
      GERAET_ORIGINS = "https://${site.nuorbHost}:8443 http://127.0.0.1:8765";
    };
    serviceConfig = {
      ExecStart = "${pkgs.python3}/bin/python3 -I ${geraetDir}/geraetedienst.py";
      Restart = "always";
      RestartSec = 2;
    };
  };

  systemd.services.nuorb-powerknopf = {
    description = "NuOrb: Power-Knopf schaltet den Bildschirm an/aus";
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      ExecStart = "${powerknopf}";
      Restart = "always";
      RestartSec = 2;
    };
  };

  # nuorb-shell (von Sitzung nuorb-ui, geprüfte Kopie): lokale UI-Kopie + Proxy zu nuorb und zum Gerätedienst.
  # Kiosk öffnet http://127.0.0.1:8770/ (sicherer Kontext, gleiche Origin -> kein Mixed-Content-Problem in WebKit)
  systemd.user.services.nuorb-shell = {
    description = "NuOrb-Shell (lokale UI + Proxy zu nuorb und Gerätedienst)";
    wantedBy = [ "default.target" ];
    unitConfig.ConditionUser = "nuorb";
    environment = {
      NUORB_URL = "https://${site.nuorbHost}:8443";
      DEVICE_URL = "http://127.0.0.1:8765";
      DEVICE_PREFIX = "/api/";
      DEVICE_ORIGIN = "https://${site.nuorbHost}:8443";
      SHELL_PORT = "8770";
      SSL_CERT_FILE = "/etc/ssl/certs/ca-certificates.crt";
    };
    serviceConfig = {
      ExecStart = "${pkgs.python3}/bin/python3 -I ${geraetDir}/nuorb-shell.py";
      Restart = "always";
      RestartSec = 2;
    };
  };

  # Power-Knopf nicht als Ausschalter/Suspend behandeln
  services.logind.settings.Login = {
    HandlePowerKey = "ignore";
    HandlePowerKeyLongPress = "poweroff";
  };
}
