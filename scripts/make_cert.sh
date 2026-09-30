#!/usr/bin/env bash
# Self-signed TLS certificate for serving the app over HTTPS (Q55): tls/cert.pem + tls/key.pem
# (gitignored). Valid for localhost, 127.0.0.1, ::1, this machine's hostname and its current LAN
# address, plus any extra DNS names or IP addresses given as arguments:
#
#   scripts/make_cert.sh                        # defaults
#   scripts/make_cert.sh 192.168.1.50 demo.lan  # + extra addresses / names (remembered)
#   scripts/make_cert.sh --if-needed            # only if missing, expiring within a day, or not
#                                               # valid for the current LAN address
#
# Every run replaces both the certificate and the key. Extra names are saved in tls/extra_names
# and reused by later runs (pass new ones to replace them). `scripts/demo.sh --https` runs
# `--if-needed` at startup, so a new network gets a new certificate automatically; browsers show
# the self-signed warning again after each change.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="$ROOT/tls"
EXTRA_FILE="$DIR/extra_names"
DAYS=397  # the longest validity browsers accept for a TLS certificate

command -v openssl >/dev/null || { echo "openssl not found" >&2; exit 1; }

# The address used for the default route, i.e. the one other devices on the LAN would use
lan_ip="$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' || true)"

if [[ "${1:-}" == "--if-needed" ]]; then
  reason=""
  if [[ ! -f "$DIR/cert.pem" || ! -f "$DIR/key.pem" ]]; then
    reason="no certificate yet"
  elif ! openssl x509 -in "$DIR/cert.pem" -noout -checkend 86400 >/dev/null; then
    reason="the certificate expires within a day"
  elif [[ -n "$lan_ip" ]] && ! openssl x509 -in "$DIR/cert.pem" -noout -ext subjectAltName \
      | grep -Eq "IP Address:${lan_ip//./\\.}(,|$)"; then
    reason="the LAN address is now $lan_ip"
  fi
  if [[ -z "$reason" ]]; then
    echo "TLS certificate: valid for this network (${lan_ip:-no LAN address})"
    exit 0
  fi
  echo "TLS certificate: regenerating ($reason)"
  shift
  extras=()
  [[ -f "$EXTRA_FILE" ]] && mapfile -t extras <"$EXTRA_FILE"
else
  extras=("$@")
fi

names=(localhost "$(hostname)" "$(hostname).local")
ips=(127.0.0.1 ::1)
[[ -n "$lan_ip" ]] && ips+=("$lan_ip")
for arg in "${extras[@]}"; do
  [[ -z "$arg" ]] && continue
  if [[ "$arg" =~ ^[0-9.]+$ || "$arg" == *:* ]]; then ips+=("$arg"); else names+=("$arg"); fi
done

san=""
for n in "${names[@]}"; do san+="DNS:$n,"; done
for i in "${ips[@]}"; do san+="IP:$i,"; done
san="${san%,}"

mkdir -p "$DIR"
umask 077  # the private key is readable by this user only
# Write to temporary files first: the old pair is replaced only if openssl succeeds
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
  -days "$DAYS" -subj "/CN=Urban Green Planner (local)" \
  -addext "subjectAltName=$san" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature" \
  -addext "extendedKeyUsage=serverAuth" \
  -keyout "$DIR/key.pem.new" -out "$DIR/cert.pem.new" 2>/dev/null
mv -f "$DIR/key.pem.new" "$DIR/key.pem"
mv -f "$DIR/cert.pem.new" "$DIR/cert.pem"
chmod 644 "$DIR/cert.pem"
printf '%s\n' "${extras[@]}" >"$EXTRA_FILE"

echo "wrote tls/cert.pem and tls/key.pem (new key, valid $DAYS days)"
openssl x509 -in "$DIR/cert.pem" -noout -enddate -ext subjectAltName | sed 's/^/  /'
