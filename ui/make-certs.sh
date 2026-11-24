#!/usr/bin/env bash
# Erzeugt eine kleine Heim-CA + Server-Zertifikat fuer jarvis (als Benutzer jarvis, idempotent).
# Die CA (jarvis-ca.crt) wird einmal auf dem Handy als vertrauenswuerdig importiert.
# Eigenes Zertifikat fuer einen weiteren Dienst (z. B. jarvis-admin) aus derselben CA:
#   CA_DIR=~/jarvis-ui/certs ~/jarvis-ui/make-certs.sh ~/jarvis-admin/certs
set -euo pipefail
D="${1:-$HOME/jarvis-ui/certs}"; mkdir -p "$D"; D="$(cd "$D" && pwd)"
CA="$(cd "${CA_DIR:-$D}" && pwd)"; cd "$D"; umask 077
IP="${JARVIS_IP:-${JARVIS_HOST:?set JARVIS_HOST or JARVIS_IP (address of this LXC)}}"
if [ ! -f "$CA/jarvis-ca.key" ]; then
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 3650 \
    -keyout "$CA/jarvis-ca.key" -out "$CA/jarvis-ca.crt" -subj "/CN=JARVIS Heim-CA/O=Xiaomi Rebirth" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" -addext "keyUsage=critical,keyCertSign,cRLSign"
fi
openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -keyout server.key -out server.csr -subj "/CN=jarvis"
cat > server.ext <<EXT
basicConstraints=CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=serverAuth
subjectAltName=IP:$IP,DNS:jarvis,DNS:jarvis.local,DNS:jarvis.lan,DNS:localhost,IP:127.0.0.1
EXT
# 825 Tage: Obergrenze, die Apple/Chrome fuer private CAs akzeptieren
openssl x509 -req -in server.csr -CA "$CA/jarvis-ca.crt" -CAkey "$CA/jarvis-ca.key" -CAserial "$CA/jarvis-ca.srl" -CAcreateserial -days 825 -sha256 -extfile server.ext -out server.crt
rm -f server.csr server.ext
[ "$CA" = "$D" ] || cp "$CA/jarvis-ca.crt" "$D/jarvis-ca.crt"
chmod 644 jarvis-ca.crt server.crt
openssl x509 -in server.crt -noout -subject -enddate -ext subjectAltName
openssl x509 -in "$CA/jarvis-ca.crt" -noout -fingerprint -sha256
