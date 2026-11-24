# Übergangslösung ohne WLAN: NuOrb-UI (NUORB_SERVER_IP:8443) über das USB-Kabel erreichen.
# Auf dem PC läuft scripts/handy-usb-proxy.sh (SSH-Reverse-Tunnel -> Handy 127.0.0.1:8443).
# Das Handy leitet NUORB_SERVER_IP:8443 per Host-Route über usb0 und DNAT auf den PC um; URL und Zertifikat bleiben gültig.
# Entfernen, sobald WLAN eingerichtet ist.
{ ... }:
let
  site = import ./site.nix;
in
{
  systemd.network.networks."40-usb0".routes = [
    { Destination = "${site.nuorbHost}/32"; }
  ];

  networking.nftables.enable = true;
  networking.nftables.tables.nuorb-usb = {
    family = "ip";
    content = ''
      chain output {
        type nat hook output priority -100; policy accept;
        oifname "usb0" ip daddr ${site.nuorbHost} tcp dport 8443 dnat to 127.0.0.1:8443
      }
    '';
  };
}
