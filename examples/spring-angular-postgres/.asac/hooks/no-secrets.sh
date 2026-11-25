#!/bin/sh
# Global, avant que l'agent travaille. Rend 1 si le dépôt du run contient déjà un secret évident.
# Les hooks reçoivent le worktree du run dans ASAC_WORKTREE (sinon, le dossier du projet).
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
if grep -rEI --exclude-dir=node_modules --exclude-dir=target --exclude-dir=.git --exclude-dir=.asac-state \
     -e 'AKIA[0-9A-Z]{16}' -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' \
     -e 'password *[:=] *["'"'"'][^"'"'"']{4,}["'"'"']' . >/dev/null 2>&1; then
  echo "no-secrets: un secret apparaît dans le dépôt" >&2
  exit 1
fi
