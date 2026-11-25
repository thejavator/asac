# Règles de sécurité

- Aucun secret dans le code, les tests ou les journaux. Les secrets viennent de l'environnement.
- Toute entrée utilisateur est validée côté serveur, même si le frontend la valide aussi.
- Pas de requête SQL construite par concaténation : requêtes paramétrées ou Spring Data.
- N'ajoutez une dépendance qu'à partir de la liste `.asac/hooks/allowed-deps.txt`.
