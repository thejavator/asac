#!/bin/sh
# Les tests de widget et d'intégration de Flutter.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
command -v flutter >/dev/null 2>&1 || { echo "flutter n'est pas installé" >&2; exit 1; }
[ -d test ] || { echo "le dossier test/ est absent" >&2; exit 1; }
flutter test >&2
