# 03 — Scénario « Hotfix » (`docs/scenarios/hotfix.md`)

Pipeline `hotfix` accéléré pour un bug en production : `fix` → `sast` → `deploy`.
Pas de spec ni de couverture, mais le **SAST n'est jamais sauté** et le déploiement part directement en production.
Le pipeline `feature` du même manifeste reste disponible (pour vérifier que les deux cohabitent).

## Contenu du dossier

| Fichier | Rôle |
|---|---|
| `asac.yaml` | Manifeste avec 2 pipelines : `feature` (72h) et `hotfix` (timeout **4h**, wall clock 12h) |
| `asac.neg-no-sast.yaml` | Variante invalide : le step `sast` est retiré → ASAC009 sur `deploy` |
| `vars/team.yaml` | Valeurs (dev=claude-code, qa=claude-code, ba=copilot) |
| `.asac/policies/hotfix-sast.rego` | Bloque si `sast_high_count > 0` (SAST jamais ignoré) |
| `.asac/policies/hotfix-prod.rego` | Autorise le déploiement direct en prod seulement pour un `Bug` `P1` avec un `ticket` |

Les steps du pipeline `hotfix` sont en `assist`. Preuves : `tests_green` (fix), `sast_clean` (sast), `deployed` (deploy).
Seule gate : `fix`, rôle `developer`, timeout 1h.

## 0. Préparation

```bash
export PATH="/Users/tahrielmedhi/IBM/sldc-agentic/asac/.venv/bin:$PATH"
export ASAC_AUTORUN=0
SRC=/Users/tahrielmedhi/IBM/sldc-agentic/asac/tests/functional/03-hotfix
WORK=$(mktemp -d) && cp -R "$SRC/." "$WORK" && cd "$WORK"
export ASAC_STATE_DIR="$WORK/.asac-state"
cp vars/team.yaml asac.vars.yaml
```

Prérequis : binaire `opa` dans le `PATH` (policies OPA, fail closed sinon).

## 1. Validation et plan

```bash
asac validate                    # exit 0, "0 error(s), 0 warning(s)"
asac plan -p hotfix              # exit 0, 3 steps, "estimated tokens: 300,000 / budget 2,000,000"
asac validate -f asac.neg-no-sast.yaml   # exit 1, ASAC009 pipelines.hotfix.steps.deploy.requiresEvidence: 'sast_clean' …
```

Le plan `hotfix` doit afficher `fix` (gate human `developer`), `sast`, `deploy` et aucune étape de spec ni de couverture.
Il n'existe **pas** d'option `--trigger` (la doc utilise `asac apply --pipeline hotfix --trigger jira:PAY-BUG-89`) : on lance donc le pipeline à la main.

## 2. Cas nominal

Les champs que la policy `hotfix-prod` lit (`issue_type`, `priority`, `ticket`) sont normalement fournis par le harnais ;
avec `fake` on les injecte via `ASAC_FAKE_RESULT`.

```bash
asac apply -p hotfix --run-id PAY-BUG-89 --harness fake                   # exit 2, attend gate_PAY-BUG-89_fix
asac approve gate_PAY-BUG-89_fix --role developer --by dev1 --no-resume   # exit 0
ASAC_FAKE_RESULT='{"issue_type":"Bug","priority":"P1","ticket":"PAY-BUG-89"}' \
  asac apply --resume PAY-BUG-89 --harness fake                           # exit 0, "run PAY-BUG-89: completed"
asac status --run-id PAY-BUG-89
asac evidence show PAY-BUG-89
asac evidence verify PAY-BUG-89                                           # exit 0, "evidence ok"
```

Attendu : `fix`, `sast`, `deploy` tous `completed` ; 3 preuves `tests_green` (`approved_by=dev1`), `sast_clean`, `deployed`.
Les hooks `secret-scan`, `deps-verify`, `freeze-check` passent à chaque step (`asac logs PAY-BUG-89`).

## 3. Cas bloquants

### 3a. Déploiement refusé : pas un Bug P1 avec ticket

```bash
asac apply -p hotfix --run-id HF-1 --harness fake                         # exit 2
asac approve gate_HF-1_fix --role developer --by dev1 --no-resume         # exit 0
asac apply --resume HF-1 --harness fake                                   # exit 3
```

Attendu : `run HF-1: blocked at deploy: hotfix: a ticket must be attached; hotfix: issue type must be Bug; hotfix: priority must be P1`.
Le run est `blocked` ; on le reprend avec les bons champs :

```bash
ASAC_FAKE_RESULT='{"issue_type":"Bug","priority":"P1","ticket":"PAY-BUG-89"}' asac apply --resume HF-1 --harness fake   # exit 0, completed
```

### 3b. SAST : findings critiques → bloqué

```bash
asac apply -p hotfix --run-id HF-6 --harness fake                         # exit 2
ASAC_FAKE_RESULT='{"sast_high_count":2}' asac approve gate_HF-6_fix --role developer --by dev1 --harness fake
```

Attendu : `run HF-6: blocked at sast: hotfix: 2 high-severity SAST findings must be resolved` (statut `blocked`, `approve` sort en 0).
Aucun chemin ne contourne le SAST : `deploy` exige `sast_clean`, et `asac.neg-no-sast.yaml` (step retiré) est refusé par `validate`.

### 3c. Mauvais rôle sur la gate

```bash
asac apply -p hotfix --run-id HF-3 --harness fake
asac approve gate_HF-3_fix --role qa_engineer --by q1                     # exit 3
```

Attendu : `error: gate 'gate_HF-3_fix' requires role 'developer'`.

### 3d. Timeout du pipeline (4h) et expiration de la gate (1h)

```bash
asac apply -p hotfix --run-id HF-T --harness fake                         # exit 2
ASAC_FIXED_TIME=2099-01-01T00:00:00Z asac apply --resume HF-T --harness fake
```

Attendu : exit **1**, `run HF-T: failed at fix: gate gate_HF-T_fix expired` (la gate de 1h expire avant le timeout de 4h du pipeline).

### 3e. Le pipeline `feature` n'est pas affecté

```bash
asac plan -p feature             # 4 steps, "estimated tokens: 400,000 / budget 2,000,000"
```

## 4. Hand-off d'un vrai harnais (optionnel)

Le hotfix est en `assist` : avec un vrai harnais, `apply -p hotfix` écrit un brief dans `.asac-state/briefs/<run>/fix.md`
et sort en exit 2 (`handed to a person`). Pour le rejouer avec claude-code, remplacer `--harness fake` par rien et
`ASAC_AUTORUN=0` (déjà exporté) : aucun outil n'est lancé.

## 5. Nettoyage

```bash
cd / && rm -rf "$WORK"
```

## Écarts connus entre la doc et le CLI

- `asac apply --pipeline hotfix --trigger jira:PAY-BUG-89` : `--pipeline` (`-p`) existe, mais `--trigger` n'existe pas ; on lance le pipeline à la main.
- « Sauter la spec et la couverture » n'est pas une option du CLI : c'est le pipeline `hotfix` qui ne contient pas ces steps.
- « Le SAST n'est jamais sauté » n'est pas une règle moteur : il est garanti ici par la preuve `sast_clean` exigée par `deploy` (ASAC009) et la policy `hotfix-sast`.
- Un déclenchement manuel côté daemon (Jira « bug P1 ») n'est pas couvert : le trigger Jira du manifeste ne concerne que `feature`.
