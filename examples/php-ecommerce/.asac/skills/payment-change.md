# Changement de paiement ou de prix

Ce changement est sous contrôle renforcé. Implémentez `SPEC.md` dans `src/Payment/` ou `src/Pricing/`.

- Les montants sont des entiers en **centimes** ou un type `Money` : jamais un `float`.
- Chaque appel au prestataire a un test pour le succès, le refus, le délai dépassé et la réponse en double.
- Une opération de paiement est idempotente : rejouée avec la même clé, elle ne débite pas deux fois.
- Utilisez la clé de TEST du prestataire. Aucune clé de production n'existe dans ce dépôt.

Ne modifiez rien en dehors de `src/Payment/`, `src/Pricing/`, `tests/Payment/` et `tests/Pricing/`.
