# Conventions PHP

- PSR-12, `declare(strict_types=1);` partout, types de retour obligatoires.
- Pas de logique dans un contrôleur ni dans un template Twig.
- Les messages affichés au client passent par le traducteur, jamais en dur.
