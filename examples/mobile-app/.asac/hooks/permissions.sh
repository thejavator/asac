#!/bin/sh
# Permissions : aucune n'est ajoutée à Android ou iOS en dehors d'une demande écrite dans SPEC.md.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
# Le point de départ du run : là où asac/<run> s'est détachée de la branche principale.
base=$(git merge-base HEAD "$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || echo main)" 2>/dev/null \
       || git merge-base HEAD master 2>/dev/null || git rev-list --max-parents=0 HEAD | tail -1)
status=0
added=""
for f in android/app/src/main/AndroidManifest.xml ios/Runner/Info.plist; do
  [ -f "$f" ] || continue
  # lignes ajoutées par rapport au commit de départ du run
  added="$added$(git diff "$base" -- "$f" 2>/dev/null | grep -E '^\+' | grep -E 'uses-permission|NS[A-Za-z]+UsageDescription' || true)"
done
if [ -n "$added" ]; then
  for perm in $(printf '%s\n' "$added" | grep -oE 'android\.permission\.[A-Z_]+|NS[A-Za-z]+UsageDescription' | sort -u); do
    grep -q "$perm" SPEC.md 2>/dev/null || { echo "permissions: $perm est ajoutée sans être demandée dans SPEC.md" >&2; status=1; }
  done
fi
exit $status
