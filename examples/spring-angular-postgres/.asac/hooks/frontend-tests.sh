#!/bin/sh
# Les tests Angular, sur le worktree.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}/frontend" || { echo "frontend/ est absent" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "npm n'est pas installé" >&2; exit 1; }
[ -d node_modules ] || npm ci --silent >&2 || exit 1
npm test --silent -- --ci >&2
