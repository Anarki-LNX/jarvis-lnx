#!/usr/bin/env bash
# Erzeugt eine kleine Heim-CA + Server-Zertifikat fuer nuorb (als Benutzer nuorb, idempotent).
# Die CA (nuorb-ca.crt) wird einmal auf dem Handy als vertrauenswuerdig importiert.
# Eigenes Zertifikat fuer einen weiteren Dienst (z. B. nuorb-admin) aus derselben CA:
#   CA_DIR=~/nuorb-ui/certs ~/nuorb-ui/make-certs.sh ~/nuorb-admin/certs
set -euo pipefail
D="${1:-$HOME/nuorb-ui/certs}"; mkdir -p "$D"; D="$(cd "$D" && pwd)"
CA="$(cd "${CA_DIR:-$D}" && pwd)"; cd "$D"; umask 077
IP="${NUORB_SERVER_IP:?set NUORB_SERVER_IP (address of this LXC)}"
if [ ! -f "$CA/nuorb-ca.key" ]; then
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 3650 \
    -keyout "$CA/nuorb-ca.key" -out "$CA/nuorb-ca.crt" -subj "/CN=NuOrb Heim-CA/O=Xiaomi Rebirth" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" -addext "keyUsage=critical,keyCertSign,cRLSign"
fi
openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -keyout server.key -out server.csr -subj "/CN=nuorb"
cat > server.ext <<EXT
basicConstraints=CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=serverAuth
subjectAltName=IP:$IP,DNS:nuorb,DNS:nuorb.local,DNS:nuorb.lan,DNS:localhost,IP:127.0.0.1
EXT
# 825 Tage: Obergrenze, die Apple/Chrome fuer private CAs akzeptieren
openssl x509 -req -in server.csr -CA "$CA/nuorb-ca.crt" -CAkey "$CA/nuorb-ca.key" -CAserial "$CA/nuorb-ca.srl" -CAcreateserial -days 825 -sha256 -extfile server.ext -out server.crt
rm -f server.csr server.ext
[ "$CA" = "$D" ] || cp "$CA/nuorb-ca.crt" "$D/nuorb-ca.crt"
chmod 644 nuorb-ca.crt server.crt
openssl x509 -in server.crt -noout -subject -enddate -ext subjectAltName
openssl x509 -in "$CA/nuorb-ca.crt" -noout -fingerprint -sha256
