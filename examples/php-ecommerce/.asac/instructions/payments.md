# Paiement et prix

- Aucun `float` pour un montant : centimes (`int`) ou `Money`. L'arrondi se fait à un seul endroit.
- Aucune donnée de carte ne touche notre serveur : seul le jeton du prestataire est stocké.
- Les journaux ne contiennent ni numéro de carte, ni jeton, ni adresse complète.
- Une règle de prix a son test, y compris pour 0, un montant négatif et un très grand montant.
