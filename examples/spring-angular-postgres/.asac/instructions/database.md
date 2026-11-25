# Règles pour la base de données

- Le schéma ne change que par une migration Flyway. Jamais de DDL dans le code Java.
- Une migration publiée n'est jamais modifiée : on en écrit une nouvelle.
- Les noms de tables et colonnes sont en `snake_case`, au singulier pour les tables.
- Vous n'avez accès qu'à la base de développement du run, en lecture.
