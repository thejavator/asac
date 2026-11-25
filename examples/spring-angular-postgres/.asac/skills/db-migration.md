# Migration de base de données

Écrivez UNE migration Flyway dans `backend/src/main/resources/db/migration/`, nommée
`V<yyyyMMddHHmm>__<description>.sql`, à partir des tables décrites dans `SPEC.md`.

- Elle doit s'appliquer sur une base vide et sur la base courante.
- Écrivez aussi son annulation, `U<même version>__<description>.sql`, dans le même dossier.
- Pas de `DROP` sans sa sauvegarde ; pas de colonne `NOT NULL` ajoutée sans valeur par défaut.
- Vous pouvez lire le schéma courant par le serveur MCP `postgres-mcp` (lecture seule).

Ne touchez ni au code Java ni au code Angular.
