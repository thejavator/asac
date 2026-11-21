# Tests fonctionnels du CLI `asac`

Un dossier par scénario de `docs/scenarios/`. Chaque dossier contient ses `asac*.yaml`, ses fichiers `vars/`
et un `README.md` avec les commandes à exécuter dans l'ordre, les codes de sortie et les sorties attendues.
Tout a été rejoué sur des copies temporaires avec le harnais `fake` (aucun modèle appelé) ; seuls les vrais harnais
sont utilisés en mode hand-off (`ASAC_AUTORUN=0`).

| Dossier | Scénario | Couvre |
|---|---|---|
| [`01-new-project`](01-new-project/README.md) | Nouveau projet | `init`, `vars check/diff`, `validate`, `plan`, premier `apply`, portail |
| [`02-feature`](02-feature/README.md) | Feature | Run complet à 3 gates, rejet/réouverture, rôles, budget, policy OPA, hooks, kill, delegate sans runner, expiration, hand-off, 6 manifestes invalides, daemon Jira |
| [`03-hotfix`](03-hotfix/README.md) | Hotfix | Pipeline accéléré, SAST jamais sauté, policy de déploiement prod, timeout et expiration |
| [`04-onboarding`](04-onboarding/README.md) | Onboarding | Modèle de valeurs, choix de harnais (cursor/bob/copilot), hand-off, fichiers montés |

## Prérequis

- CLI `asac` installé (dans `$ASAC_HOME/.venv/bin`) : `asac version` → `asac 0.0.1 (spec 0.4)`.
- `opa` dans le `PATH` pour les policies `.rego` (sans `opa`, les policies échouent en *fail closed*).
- `curl` et `openssl` pour les tests du daemon et du portail.

## Conventions

- Toujours travailler sur une **copie** (`mktemp -d`) et fixer `ASAC_STATE_DIR` pour isoler l'état SQLite.
- Codes de sortie : 0 terminé, 1 erreur, 2 en attente (gate / hand-off), 3 bloqué (policy, budget, hook, rôle, kill).
- `asac approve` reprend le run tout seul et sort en 0 même si la reprise se bloque : lire le message ou `asac status`.
- Quand on utilise un manifeste autre que `asac.yaml`, passer `-f` à **toutes** les commandes (`apply`, `approve`, `status`, `evidence`).

## Écarts doc / CLI constatés

| Doc | CLI réel | Impact |
|---|---|---|
| `asac init --template java-microservice` | seuls `minimal` et `feature` existent (exit 1) | README 01 utilise `feature` |
| `asac plan --trigger jira:…` et `asac apply --trigger …` | option inexistante (exit 2) | lancement manuel avec `-p` |
| `init` crée `asac.vars.yaml.example`, `default.rego`, `.gitignore` | seulement `asac.yaml` | à copier à la main |
| Cursor « IDE seulement » (non headless) | catalogue : `cursor` headless, ASAC013 ne se déclenche pas | seuls `copilot` et `antigravity` sont refusés en `delegate` |

> `ASAC_HOME` désigne la racine de ce dépôt (le dossier qui contient `pyproject.toml`) : `export ASAC_HOME="$(pwd)"` depuis cette racine.
