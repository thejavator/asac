# Implémentation Symfony

Implémentez `SPEC.md` dans `src/` et `tests/`.

- PHP 8.3, `declare(strict_types=1);` dans chaque fichier. Contrôleurs fins : la logique va dans un service.
- Accès aux données par Doctrine (requêtes paramétrées) ; jamais de SQL concaténé.
- Un test PHPUnit par critère d'acceptation. PHPStan niveau 8 sans erreur.
- Aucun `var_dump`, `dump`, `dd` ni `die` dans `src/`.

Ne touchez ni à `src/Payment/` ni au calcul des prix : c'est un autre pipeline. Arrêtez-vous quand
`composer test` et `composer stan` passent.
