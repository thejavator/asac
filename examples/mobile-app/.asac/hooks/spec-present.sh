#!/bin/sh
# Étape requirements : SPEC.md a ses critères d'acceptation et déclare les permissions.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
[ -s SPEC.md ] || { echo "SPEC.md est absent ou vide" >&2; exit 1; }
grep -qi "acceptance criteria" SPEC.md || { echo "SPEC.md n'a pas de section « Acceptance criteria »" >&2; exit 1; }
grep -qi "permission" SPEC.md || { echo "SPEC.md ne dit rien des permissions (écrivez « aucune » s'il n'y en a pas)" >&2; exit 1; }
