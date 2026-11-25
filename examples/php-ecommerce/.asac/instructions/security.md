# Sécurité

- Aucun secret dans le code ni dans les tests. Tout vient de l'environnement (`.env.local`, ignoré).
- Les entrées sont validées par les contraintes Symfony côté serveur ; les sorties Twig sont échappées.
- Pas de SQL construit par concaténation. Pas de `unserialize` sur une donnée venue d'un utilisateur.
- Un nouveau paquet Composer se demande dans `SPEC.md` avant d'être ajouté.
