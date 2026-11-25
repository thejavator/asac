#!/bin/sh
# Avertissement seulement : chaque gabarit de page a un <title> et une URL canonique.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
[ -d templates ] || exit 0
status=0
for f in $(find templates -name '*.html.twig' -not -path '*/email/*' -not -name 'base.html.twig' 2>/dev/null); do
  grep -q 'extends' "$f" || continue
  grep -qE 'block +title' "$f" || { echo "seo-check: $f n'a pas de bloc title" >&2; status=1; }
done
[ -f templates/base.html.twig ] && ! grep -q 'rel="canonical"' templates/base.html.twig \
  && { echo "seo-check: templates/base.html.twig n'a pas d'URL canonique" >&2; status=1; }
exit $status
