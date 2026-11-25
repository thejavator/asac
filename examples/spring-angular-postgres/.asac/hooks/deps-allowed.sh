#!/bin/sh
# Global, après chaque étape : aucune dépendance Maven ou npm hors de la liste autorisée.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
allowed="${ASAC_ROOT:-$(dirname "$0")/../..}/.asac/hooks/allowed-deps.txt"
[ -f "$allowed" ] || { echo "liste autorisée absente : $allowed" >&2; exit 1; }
status=0
if [ -f backend/pom.xml ]; then
  # <dependency> ... <groupId>g</groupId><artifactId>a</artifactId> ...
  for dep in $(tr -d ' \n\t' < backend/pom.xml | grep -o '<dependency><groupId>[^<]*</groupId><artifactId>[^<]*</artifactId>' \
               | sed 's#<dependency><groupId>\(.*\)</groupId><artifactId>\(.*\)</artifactId>#\1:\2#'); do
    grep -qxF "$dep" "$allowed" || { echo "deps-allowed: $dep n'est pas autorisée" >&2; status=1; }
  done
fi
if [ -f frontend/package.json ]; then
  for dep in $(python3 - <<'PY'
import json
d = json.load(open("frontend/package.json"))
for k in ("dependencies", "devDependencies"):
    for name in d.get(k, {}): print(name)
PY
  ); do
    grep -qxF "$dep" "$allowed" || { echo "deps-allowed: $dep n'est pas autorisée" >&2; status=1; }
  done
fi
exit $status
