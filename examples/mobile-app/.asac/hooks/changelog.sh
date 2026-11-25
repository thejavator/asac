#!/bin/sh
# Étape release : CHANGELOG.md a une entrée pour la version de pubspec.yaml.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
version=$(sed -n 's/^version: *\([0-9][0-9.]*\).*/\1/p' pubspec.yaml | head -1)
[ -n "$version" ] || { echo "pubspec.yaml n'a pas de version" >&2; exit 1; }
[ -f CHANGELOG.md ] || { echo "CHANGELOG.md est absent" >&2; exit 1; }
grep -qF "$version" CHANGELOG.md || { echo "CHANGELOG.md n'a pas d'entrée pour la version $version" >&2; exit 1; }
