#!/bin/sh
# Avertissement seulement : repère les requêtes dans une boucle (le N+1 classique).
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
[ -d src ] || exit 0
hits=$(awk 'FNR==1{depth=0} /foreach *\(|while *\(|for *\(/{depth++} depth>0 && /->(find|findOneBy|findBy|createQuery|getRepository)\(/ {print FILENAME":"FNR": "$0} /^\s*}\s*$/{if(depth>0)depth--}' \
       $(find src -name '*.php') 2>/dev/null | head -5)
[ -z "$hits" ] || { echo "perf-check: une requête est dans une boucle :" >&2; printf '%s\n' "$hits" >&2; exit 1; }
