#!/bin/sh
# pre_tool hook: refuse to start if a tracked-looking file already holds a private key.
cd "$(dirname "$0")/../.." || exit 1
if grep -rIl --exclude-dir=.git --exclude-dir=.asac-state -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' . >/dev/null 2>&1; then
  echo "no-secrets: a private key is present in the working tree" >&2
  exit 1
fi
exit 0
