#!/bin/sh
# Aucun montant en `float` dans le code de paiement et de prix : centimes (int) ou Money.
# Les commentaires (`//`, `#`, `/* … */` sur une ligne) sont ignorés : « float » dans une phrase
# n'est pas un montant manipulé en float.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
status=0
for d in src/Payment src/Pricing; do
  [ -d "$d" ] || continue
  hits=$(find "$d" -name '*.php' -exec awk '
    {
      line = $0
      gsub(/\/\*[^*]*\*\//, "", line)       # /* … */ sur une ligne
      sub(/\/\/.*/, "", line)               # // …
      sub(/#.*/, "", line)                  # # …
      if (line ~ /(^|[^A-Za-z_])float([^A-Za-z_]|$)/ || line ~ /floatval[ ]*\(/ || line ~ /round[ ]*\(/ || line ~ /number_format[ ]*\(/)
        print FILENAME ":" FNR ": " $0
    }' {} + ) || { echo "money-types: la lecture de $d a échoué" >&2; exit 1; }
  if [ -n "$hits" ]; then
    echo "money-types: un montant est manipulé en float dans $d :" >&2
    printf '%s\n' "$hits" | head -5 >&2
    status=1
  fi
done
exit $status
