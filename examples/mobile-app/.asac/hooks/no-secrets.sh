#!/bin/sh
# Global, avant que l'agent travaille : aucun secret évident dans le dépôt du run.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
if grep -rEI --exclude-dir=.dart_tool --exclude-dir=build --exclude-dir=.git --exclude-dir=.asac-state \
     --exclude-dir=Pods -e 'AKIA[0-9A-Z]{16}' -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' \
     -e 'AIza[0-9A-Za-z_-]{35}' -e 'storePassword *=' -e 'keyPassword *=' . >/dev/null 2>&1; then
  echo "no-secrets: un secret ou un mot de passe de signature apparaît dans le dépôt" >&2
  exit 1
fi
