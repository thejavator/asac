#!/bin/sh
# Étape database : une migration Flyway valide, avec son annulation, et rien d'autre de modifié.
cd "${ASAC_WORKTREE:-$(dirname "$0")/../..}" || exit 1
dir=backend/src/main/resources/db/migration
# Le point de départ du run : là où la branche asac/<run> s'est détachée de la branche principale.
# Un hook ne doit pas deviner « le premier commit du dépôt » : ce n'est pas celui du run.
base=$(git merge-base HEAD "$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || echo main)" 2>/dev/null \
       || git merge-base HEAD master 2>/dev/null || git rev-list --max-parents=0 HEAD | tail -1)
# Ajoutés depuis le départ (déjà commités par un tour précédent), ou pas encore commités.
new=$({ git diff --name-only --diff-filter=A "$base" -- "$dir"; git ls-files --others --exclude-standard "$dir"; } | sort -u)
ups=$(printf '%s\n' "$new" | grep '/V[0-9]\{12\}__[a-z0-9_]*\.sql$' | sort -u)
[ -n "$ups" ] || { echo "aucune migration V<yyyyMMddHHmm>__nom.sql n'a été ajoutée dans $dir" >&2; exit 1; }
for up in $ups; do
  down=$(printf '%s' "$up" | sed 's#/V\([0-9]*__\)#/U\1#')
  [ -s "$down" ] || { echo "$up n'a pas d'annulation ($down)" >&2; exit 1; }
  if grep -Eiq 'drop +(table|column)' "$up"; then
    echo "$up contient un DROP : prévoyez la sauvegarde, puis faites valider par le DBA" >&2; exit 1
  fi
  if grep -Eiq 'add +column.* not null' "$up" && ! grep -Eiq 'add +column.* default' "$up"; then
    echo "$up ajoute une colonne NOT NULL sans valeur par défaut" >&2; exit 1
  fi
done
# Le code Java et Angular ne se touchent pas à cette étape.
# Fichiers suivis modifiés depuis le départ, et fichiers neufs un par un (`ls-files --others` ne
# replie pas un dossier neuf en une seule ligne, contrairement à `git status`).
others=$({ git diff --name-only "$base" ; git ls-files --others --exclude-standard; } | sort -u | grep -v "^$dir/" | grep -E '\.(java|ts|html)$' || true)
[ -z "$others" ] || { echo "cette étape ne modifie que la migration ; modifié : $others" >&2; exit 1; }
