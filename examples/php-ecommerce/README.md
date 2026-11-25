# Exemple : site e-commerce PHP (Symfony)

Un site qui **touche à l'argent**. Ce que ce cas montre et que les autres ne montrent pas : un
pipeline à part pour tout changement de **paiement ou de prix**, avec des contrôles bloquants
supplémentaires et des rôles qui ne se confondent pas, plus des audits SEO et performance en
parallèle.

```bash
cd examples/php-ecommerce
asac validate                                    # 0 error(s), 0 warning(s)
asac plan -p payment-change
cp asac.vars.yaml.example asac.vars.yaml
asac vars check
```

## Les pipelines

| Pipeline | Étapes | Ce qu'il montre |
|---|---|---|
| `feature` | `requirements` → `implementation` → (`seo` ‖ `performance`) → `compliance` → `release` | Audits en parallèle, rôles marketing / tech lead / conformité / direction |
| `payment-change` | `requirements` → `payment-implementation` → `security-review` → `compliance` → `release` | Contrôles bloquants (montants, SQL, périmètre), **pas de repli vers une personne** (`fallback` absent), gate **qualité** tenue par la sécurité |
| `hotfix` | `fix` → `ship` | Correction d'un défaut visible, hors paiement |

`payment-implementation` est en `delegate` **sans** `fallback: assist` : un paiement ne se « fait pas
à la main » si Docker est absent, l'étape se bloque.

## Les contrôles (hooks)

| Hook | Vérifie | Bloque ? |
|---|---|---|
| `no-secrets` (global, avant) | pas de clé de production (`sk_live_…`), de clé privée, de mot de passe de base | oui |
| `no-debug` (global, après) | pas de `var_dump`, `dd`, `die` dans `src/` | oui |
| `spec-present` | critères d'acceptation et les trois impacts (prix, stock, données personnelles) | oui |
| `phpunit` / `phpstan` | PHPUnit et PHPStan | oui |
| `sql-safe` | pas de SQL construit par concaténation ou interpolation | oui |
| `money-types` | aucun montant en `float` dans `src/Payment` et `src/Pricing` (les commentaires sont ignorés) | oui |
| `payment-scope` | un changement de paiement ne sort pas de `src/Payment`, `src/Pricing` et leurs tests ; aucune clé de production | oui |
| `seo-check`, `perf-check` | `<title>`, URL canonique ; une requête dans une boucle | **non** (`warn`) |

## Séparation des tâches

Dans `payment-change`, la gate de la revue de sécurité est tenue par `security_officer`. Le product
owner qui a demandé le changement ne peut pas l'approuver : `asac approve` rend le code 3. C'est
testé (`tests/test_examples.py`).

## Ce que la v1 n'applique pas, et que cet exemple écrit quand même

`asac validate` le dit en avertissement (`ASAC027`) ; il ne le cache pas.

| Clé | Ce qui se passe en 0.1 |
|---|---|
| `knowledge` | Acceptée, jamais donnée à l'agent. |
| `pipelines.<p>.specLevel` | Vérifié par `validate` (`ASAC026`), jamais imposé par le moteur. |
| `pipelines.<p>.trigger` | Lu par le daemon, qui n'est pas supporté en 0.1 : `asac apply` l'ignore. |
| `gate: { type: automated }` | Acceptée par le modèle, ignorée par le moteur : cet exemple n'en écrit aucune. |
| `escalation: { raison: human }` | Aucun outil ne rapporte aujourd'hui de raison d'escalade : cet exemple n'en écrit pas. Une politique Rego qui rend `escalate` ouvre bien une gate d'escalade. |

## Ce que le réseau du conteneur ne fait pas

Les étapes `mode: delegate` tournent dans un conteneur sans réseau par défaut, ce qui coupe aussi le
modèle. Pour un vrai agent, vous nommez un réseau Docker (`runner_network`) que **vous** réglez
(pare-feu, proxy) pour joindre la passerelle du modèle. ASAC ne filtre pas par domaine et n'audite
pas les refus réseau sous Docker. Voir `docs/guides/delegate.md`.
