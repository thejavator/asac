#!/bin/sh
# Accessibilité : chaque bouton ou icône interactive de lib/ porte un libellé.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
[ -d lib ] || { echo "le dossier lib/ est absent" >&2; exit 1; }
status=0
for f in $(grep -rlE '(IconButton|FloatingActionButton|GestureDetector|InkWell)\(' lib 2>/dev/null); do
  # un IconButton/FAB sans tooltip ni Semantics, ou un geste nu sans Semantics
  if grep -qE '(IconButton|FloatingActionButton)\(' "$f" && ! grep -qE 'tooltip:|Semantics\(' "$f"; then
    echo "a11y: $f a un bouton d'icône sans tooltip ni Semantics" >&2; status=1
  fi
  if grep -qE '(GestureDetector|InkWell)\(' "$f" && ! grep -qE 'Semantics\(|semanticLabel' "$f"; then
    echo "a11y: $f a une zone tactile sans Semantics" >&2; status=1
  fi
done
exit $status
