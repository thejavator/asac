#!/bin/sh
# Étape design : DESIGN.md décrit les états, l'accessibilité et le texte agrandi.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
[ -s DESIGN.md ] || { echo "DESIGN.md est absent ou vide" >&2; exit 1; }
for want in "chargement" "erreur" "hors ligne" "accessibilité" "200"; do
  grep -qi "$want" DESIGN.md || { echo "DESIGN.md ne parle pas de « $want »" >&2; exit 1; }
done
