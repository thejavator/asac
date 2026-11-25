#!/bin/sh
# SPEC.md a ses critères d'acceptation et les trois impacts (prix, stock, données personnelles).
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
[ -s SPEC.md ] || { echo "SPEC.md est absent ou vide" >&2; exit 1; }
grep -qi "acceptance criteria" SPEC.md || { echo "SPEC.md n'a pas de section « Acceptance criteria »" >&2; exit 1; }
for impact in "Prix et taxes" "Stock" "Données personnelles"; do
  grep -qi "$impact" SPEC.md || { echo "SPEC.md n'évalue pas l'impact « $impact » (écrivez « aucun » s'il n'y en a pas)" >&2; exit 1; }
done
