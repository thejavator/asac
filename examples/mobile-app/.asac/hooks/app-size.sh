#!/bin/sh
# Taille du paquet Android (on_fail: warn : on prévient, on ne bloque pas).
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
limit="${ASAC_SIZE_BUDGET_MB:-45}"
aab=$(ls build/app/outputs/bundle/release/*.aab 2>/dev/null | head -1)
[ -n "$aab" ] || exit 0   # pas de paquet construit à cette étape : rien à mesurer
mb=$(( $(wc -c < "$aab") / 1048576 ))
echo "taille du paquet : ${mb} Mo (budget ${limit} Mo)" >&2
[ "$mb" -le "$limit" ]
