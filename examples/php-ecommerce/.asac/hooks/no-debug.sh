#!/bin/sh
# Global, après chaque étape : aucun reste de débogage dans le code de production.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
[ -d src ] || exit 0
hits=$(grep -rnE '\b(var_dump|print_r|dump|dd|die|exit)\s*\(' --include='*.php' src 2>/dev/null \
       | grep -vE '^\s*//' || true)
[ -z "$hits" ] || { echo "no-debug: reste de débogage dans src/ :" >&2; printf '%s\n' "$hits" | head -5 >&2; exit 1; }
