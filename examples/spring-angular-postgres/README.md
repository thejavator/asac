# Exemple : backend Java Spring, frontend Angular, base PostgreSQL

Une application à trois étages, livrée fonctionnalité par fonctionnalité : une spécification, une
migration Flyway, le backend et le frontend écrits en parallèle, une vérification d'intégration, une
livraison. Le résultat de chaque run est une branche `asac/<run>` qu'une personne fusionne.

```bash
cd examples/spring-angular-postgres
asac validate                                    # 0 error(s), 2 warning(s) : les deux ASAC027 attendus
asac plan -p feature                             # 6 étapes, 5 niveaux : backend et frontend au même niveau
cp asac.vars.yaml.example asac.vars.yaml         # puis remplacez les références ${vault.…}
asac vars check
```

## Les pipelines

| Pipeline | Étapes | Ce qu'il montre |
|---|---|---|
| `feature` | `requirements` → `database` → (`backend` ‖ `frontend`) → `verification` → `release` | Étapes en parallèle sur la même dépendance, une gate par rôle (PO, DBA, tech lead, QA), une gate **qualité** jugée par une politique Rego, une étape en **lecture seule** |
| `hotfix` | `fix` → `ship` | Un pipeline court, mêmes contrôles de base |

## Ce que chaque clé fait ici

| Clé | Utilisation dans l'exemple |
|---|---|
| `variables` | Deux outils distincts : `tool` (une personne conduit) et `dev_tool` (sans interface, pour `delegate`). Des secrets (`sensitive`), des valeurs par défaut. |
| `providers` + `mcp` | Un serveur MCP PostgreSQL **en lecture seule** (`--access-mode=restricted`), exposé au seul agent `dba`. Son secret est une référence `${vault…}` (`ASAC025` refuse une valeur). |
| `capabilities` / `evidenceTypes` | Six capacités, huit preuves : chaque étape en produit, la suivante en exige (`requiresEvidence`). |
| `skills` | Locaux (`.asac/skills/*.md`), avec des `params`. Un skill de registre donnerait l'avertissement `ASAC017` : pas de registre en 0.1. |
| `agents` | Un skill + un fournisseur + un outil, des `instructions` choisies agent par agent, des `tools` MCP. |
| `instructions` | Projetées dans `CLAUDE.md` / `AGENTS.md` du worktree. |
| `budgets` | Par run (jetons, coût, durée) et par étape (itérations). Un coût inconnu bloque. |
| `hooks` | Neuf contrôles : globaux (`pre_tool`, `post_step`) et par étape. Un seul est en `on_fail: warn` (`lint`). |
| `mode` | `assist` (une personne, aidée de l'agent) et `delegate` (un conteneur). |
| `execution` | `runner: docker` ; `fallback: assist` rend l'étape à une personne si Docker manque. |
| `autonomy` | `review` par défaut, `readonly` pour la vérification (l'agent lit, ne modifie rien). |
| `loop` | `until` + `max_iterations` : l'agent est relancé avec l'erreur du contrôle, jusqu'au plafond. |
| `gate` | `human` et `quality`, avec `role` et `timeout`. |
| `policies` | `no_regression` (fournie par ASAC) et `release-gate.rego`, avec ses tests `opa`. |

## Les contrôles (hooks)

Ils sont lus depuis le dépôt principal et lancés **sur le worktree** (`ASAC_WORKTREE`).

| Hook | Vérifie | Bloque ? |
|---|---|---|
| `no-secrets` (global, avant) | aucun secret évident dans le dépôt | oui |
| `deps-allowed` (global, après) | chaque dépendance Maven et npm est dans `allowed-deps.txt` | oui |
| `spec-present` | `SPEC.md` a ses cinq sections | oui |
| `migration-ok` | une migration `V…` **et** son annulation `U…`, pas de `DROP`, pas de `NOT NULL` sans défaut, aucun fichier Java ou TypeScript touché | oui |
| `backend-tests` | `mvn test` | oui |
| `frontend-tests` | `npm test` | oui |
| `coverage` | couverture JaCoCo ≥ 80 % | oui |
| `contract` | chaque route appelée par le frontend est dans `openapi.yaml` | oui |
| `lint` | pas de `System.out` en production | **non** (`warn`) |

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
