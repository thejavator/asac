#!/bin/sh
# L'analyse statique de Flutter, sur le worktree. Une alerte, même un « info », est un échec.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
command -v flutter >/dev/null 2>&1 || { echo "flutter n'est pas installé" >&2; exit 1; }
[ -f pubspec.yaml ] || { echo "pubspec.yaml est absent" >&2; exit 1; }
flutter pub get >&2 || exit 1
flutter analyze --fatal-infos >&2
