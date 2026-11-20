#!/bin/sh
# Hook de test : échoue si le fichier FREEZE existe à la racine du projet (gel de release).
# Contrat : exit 0 = OK, autre = échec.
if [ -f FREEZE ]; then
  echo "freeze-check: release gelée (fichier FREEZE présent)" >&2
  exit 1
fi
exit 0
