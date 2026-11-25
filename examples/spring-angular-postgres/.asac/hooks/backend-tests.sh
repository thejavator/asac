#!/bin/sh
# Les tests Maven du backend, sur le worktree. Rend le code de Maven.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}/backend" || { echo "backend/ est absent" >&2; exit 1; }
command -v mvn >/dev/null 2>&1 || { echo "mvn n'est pas installé" >&2; exit 1; }
mvn -q -B -ntp test >&2
