#!/bin/sh
# L'analyse statique PHPStan, niveau fixé par phpstan.neon du projet.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
command -v php >/dev/null 2>&1 || { echo "php n'est pas installé" >&2; exit 1; }
[ -x vendor/bin/phpstan ] || composer install --no-interaction --quiet >&2 || exit 1
vendor/bin/phpstan analyse --no-progress --error-format=raw >&2
