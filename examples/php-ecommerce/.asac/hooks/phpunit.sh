#!/bin/sh
# Les tests PHPUnit, sur le worktree. Rend le code de PHPUnit.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
command -v php >/dev/null 2>&1 || { echo "php n'est pas installé" >&2; exit 1; }
[ -x vendor/bin/phpunit ] || composer install --no-interaction --quiet >&2 || exit 1
vendor/bin/phpunit --testdox >&2
