#!/bin/sh
# Global, avant que l'agent travaille : aucun secret évident dans le dépôt du run.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
if grep -rEI --exclude-dir=vendor --exclude-dir=var --exclude-dir=node_modules --exclude-dir=.git \
     --exclude-dir=.asac-state --exclude='.env' --exclude='.env.dist' --exclude='.env.test' \
     -e 'AKIA[0-9A-Z]{16}' -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' -e 'sk_live_[0-9A-Za-z]{10,}' \
     -e 'pk_live_[0-9A-Za-z]{10,}' -e 'DATABASE_URL=.*:[^@/]{4,}@' . >/dev/null 2>&1; then
  echo "no-secrets: un secret ou une clé de production apparaît dans le dépôt" >&2
  exit 1
fi
