#!/bin/sh
# Avertissement seulement (on_fail: warn) : le style ne bloque pas une étape.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
bad=$(grep -rln --include='*.java' 'System\.out\.print' backend/src/main 2>/dev/null || true)
[ -z "$bad" ] || { echo "lint: System.out dans le code de production : $bad" >&2; exit 1; }
