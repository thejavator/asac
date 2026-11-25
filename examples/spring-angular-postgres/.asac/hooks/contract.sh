#!/bin/sh
# Le contrat d'API : chaque route appelée par le frontend existe dans openapi.yaml.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
spec=backend/src/main/resources/openapi.yaml
[ -s "$spec" ] || { echo "$spec est absent" >&2; exit 1; }
missing=0
for route in $(grep -rhoE "['\"\`]/api/[A-Za-z0-9_/{}.-]+" frontend/src 2>/dev/null | tr -d "'\"\`" | sort -u); do
  grep -qF "$route" "$spec" || { echo "le frontend appelle $route, absent de openapi.yaml" >&2; missing=1; }
done
exit $missing
