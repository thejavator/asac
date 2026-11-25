#!/bin/sh
# Étape requirements : SPEC.md existe et contient ses cinq sections.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
[ -s SPEC.md ] || { echo "SPEC.md est absent ou vide" >&2; exit 1; }
for section in "Contexte" "Acceptance criteria" "Contrat d'API" "Données" "Hors périmètre"; do
  grep -qi "$section" SPEC.md || { echo "SPEC.md n'a pas la section « $section »" >&2; exit 1; }
done
