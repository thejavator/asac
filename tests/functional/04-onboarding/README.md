# 04 — Scénario « Onboarding » (`docs/scenarios/onboarding.md`)

Sara rejoint l'équipe : elle copie le modèle de valeurs, choisit son outil (`dev_harness`),
puis valide, consulte le statut et le plan. Le manifeste est celui de `payments-service` (identique à `02-feature`).

## Contenu du dossier

| Fichier | Rôle |
|---|---|
| `asac.yaml` | Manifeste (steps `development` et `release` en `delegate`) |
| `asac.assist.yaml` | Même manifeste, tous les steps en `assist` |
| `asac.vars.yaml.example` | Modèle que Sara copie en `asac.vars.yaml` |
| `vars/sara-cursor.yaml` | `dev_harness: cursor` (le cas de la doc) |
| `vars/sara-bob.yaml` | `dev_harness: bob` (autre outil headless) |
| `vars/sara-copilot.yaml` | `dev_harness: copilot` (non headless : refusé en `delegate`) |

## 0. Préparation

```bash
export PATH="/Users/tahrielmedhi/IBM/sldc-agentic/asac/.venv/bin:$PATH"
export ASAC_AUTORUN=0
SRC=/Users/tahrielmedhi/IBM/sldc-agentic/asac/tests/functional/04-onboarding
WORK=$(mktemp -d) && cp -R "$SRC/." "$WORK" && cd "$WORK"
export ASAC_STATE_DIR="$WORK/.asac-state"
```

## 1. Parcours de Sara

```bash
cp asac.vars.yaml.example asac.vars.yaml          # 1. copier le modèle
asac vars diff                                    # exit 0 : rien de manquant
cp vars/sara-cursor.yaml asac.vars.yaml           # 2. dev_harness: cursor (équivaut à éditer la ligne)
asac validate                                     # exit 0, "0 error(s), 0 warning(s)"
asac status                                       # exit 0, "no runs"
asac plan -p feature                              # exit 0, 4 steps, development agent=dev mode=delegate
```

Attendu pour `plan` : `requirements` (gate human `product_owner`), `development` (delegate), `verification` (gate quality `qa_engineer`), `release` (delegate, gate `product_owner`).

## 2. Premier run en mode hand-off

Un harnais réel en `assist` ne lance rien : il écrit un brief et attend une personne.

```bash
asac apply -f asac.assist.yaml -p feature --run-id SARA-1
```

Attendu : exit **2**, `run SARA-1: requirements handed to a person (brief: …/briefs/SARA-1/requirements.md)`.
Le brief existe : `ls .asac-state/briefs/SARA-1/`.

Premier run sans outil (`fake`) pour voir la mécanique : `asac apply -p feature --run-id SARA-2 --harness fake` → exit 2 sur la gate `requirements`.

## 3. Choix du harnais : ce qui est accepté ou refusé

| Fichier de valeurs | Manifeste `asac.yaml` (delegate) | Manifeste `asac.assist.yaml` |
|---|---|---|
| `vars/sara-cursor.yaml` | exit 0 | exit 0 |
| `vars/sara-bob.yaml` | exit 0 | exit 0 |
| `vars/sara-copilot.yaml` | exit **1** : ASAC013 (×2 : `development`, `release`) | exit 0 |

```bash
for v in sara-cursor sara-bob sara-copilot; do
  echo "== $v (delegate)"; asac validate --vars vars/$v.yaml; echo "exit=$?"
  echo "== $v (assist)";   asac validate -f asac.assist.yaml --vars vars/$v.yaml; echo "exit=$?"
done
```

Message pour copilot : `error ASAC013 pipelines.feature.steps.development.mode: harness 'copilot' is not headless, cannot delegate`.

## 4. Fichiers montés par harnais (assist)

Après un `apply -f asac.assist.yaml` avec le harnais choisi pour l'agent `ba` (premier step, skill `spec`), vérifier à la racine
(les skills des steps suivants sont montés quand ces steps s'exécutent). Pour tester un harnais, remplacer les 3 lignes
`*_harness:` de `asac.vars.yaml` par ce harnais :

| Harnais | Fichier |
|---|---|
| codex | `AGENTS.md` |
| cursor | `.cursor/rules/asac-<skill>.mdc` |
| bob | `.bob/skills/<skill>/SKILL.md` |
| claude-code | `.claude/skills/<skill>/SKILL.md` et `CLAUDE.md` |
| antigravity | `.agent/skills/<skill>/SKILL.md` |
| copilot | `.github/instructions/asac-<skill>.instructions.md` |

## 5. Portail (métriques)

```bash
ASAC_ENV=dev asac portal --data "$WORK/portal-data" --port 18081 &
sleep 3
curl -s localhost:18081/api/v1/login-options
kill %1
```

## 6. Nettoyage

```bash
cd / && rm -rf "$WORK"
```

## Écarts connus entre la doc et le CLI

- `onboarding.md` dit que Cursor est **IDE seulement** (donc refusé en `delegate`). Le catalogue (`asac/catalog`) le déclare **headless** :
  `asac validate` accepte `dev_harness: cursor` même avec un step `delegate` (pas d'ASAC013). Seuls `copilot` et `antigravity` sont non headless.
- La doc suggère que `asac validate` signale un harnais inadapté ; la détection ne s'applique donc qu'à copilot et antigravity.
