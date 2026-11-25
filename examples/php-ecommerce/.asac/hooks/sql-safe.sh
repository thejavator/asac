#!/bin/sh
# Pas de SQL construit par concaténation ou interpolation dans src/.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
[ -d src ] || exit 0
hits=$(grep -rnE '(->(query|exec|executeQuery|executeStatement)|createQuery|createNativeQuery)\s*\(\s*("[^"]*\$|'"'"'[^'"'"']*'"'"'\s*\.\s*\$|"[^"]*"\s*\.\s*\$)' \
       --include='*.php' src 2>/dev/null || true)
[ -z "$hits" ] || { echo "sql-safe: du SQL est construit à partir d'une variable :" >&2; printf '%s\n' "$hits" | head -5 >&2; exit 1; }
