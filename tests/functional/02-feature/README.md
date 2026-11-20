# 02 — Scénario « Feature » (`docs/scenarios/feature.md`)

Pipeline `feature` du service `payments-service` : `requirements` → `development` →
`verification` → `release`, avec 3 gates humaines, 3 hooks, des policies et des budgets.
Tout est rejoué avec le harnais **`fake`** (déterministe, 1000 tokens par step, aucun modèle appelé),
sauf la section 5 qui utilise les vrais harnais en mode *hand-off*.

## Contenu du dossier

| Fichier | Rôle |
|---|---|
| `asac.yaml` | Manifeste de référence (steps `development` et `release` en `delegate`) |
| `asac.assist.yaml` | Même manifeste, tous les steps en `assist` (pour les vrais harnais sans runner) |
| `asac.gov-budget.yaml` | Budget `per_run` à 2500 tokens (bloque au 3ᵉ step) |
| `asac.neg-*.yaml` | 6 manifestes invalides, un code d'erreur chacun |
| `asac.vars.yaml.example` | Modèle des valeurs (références `${vault.…}`) |
| `vars/team.yaml` | Valeurs nominales (ba=copilot, dev=claude-code, qa=claude-code) |
| `vars/handoff.yaml` | ba/dev=codex, qa=antigravity (hand-off) |
| `vars/bad-delegate-copilot.yaml` | `dev_harness: copilot` → ASAC013 en `delegate` |
| `vars/bad-harness.yaml` | `ba_harness: no-such-tool` → ASAC015 |
| `.asac/skills/` | 4 skills locales |
| `.asac/hooks/` | `secret-scan` (pre_tool), `deps-verify` et `freeze-check` (post_step) |
| `.asac/policies/` | `qa-gate.rego` (gate quality), `separation.rego` (dev ≠ qa) |

## 0. Préparation (à faire une fois par session de test)

On travaille toujours sur une **copie** pour ne pas polluer le dépôt.

```bash
export ASAC_BIN=/Users/tahrielmedhi/IBM/sldc-agentic/asac/.venv/bin
export PATH="$ASAC_BIN:$PATH"
export ASAC_AUTORUN=0   # n'exécute jamais un vrai outil, même si le vars le demande
SRC=/Users/tahrielmedhi/IBM/sldc-agentic/asac/tests/functional/02-feature
WORK=$(mktemp -d) && cp -R "$SRC/." "$WORK" && cd "$WORK"
export ASAC_STATE_DIR="$WORK/.asac-state"
cp vars/team.yaml asac.vars.yaml
asac version
```

Attendu : `asac 0.0.1 (spec 0.4)`.

## 1. Validation et plan

```bash
asac vars check          # exit 0
asac validate            # exit 0, "0 error(s), 0 warning(s)"
asac plan -p feature     # exit 0, 4 steps, "estimated tokens: 400,000 / budget 2,000,000"
```

> `asac plan` n'a **pas** d'option `--trigger` (la doc la mentionne) : `asac plan --trigger jira:X` → exit 2.

## 2. Cas nominal : run complet (3 gates)

```bash
asac apply -p feature --run-id PAY-1001 --harness fake        # exit 2, attend gate_PAY-1001_requirements
asac gates --status pending                                    # liste la gate, role=product_owner
asac approve gate_PAY-1001_requirements --role product_owner --by po1 --harness fake   # exit 0, s'arrête à la gate verification
asac approve gate_PAY-1001_verification --role qa_engineer   --by qa1 --harness fake   # exit 0, s'arrête à la gate release
asac approve gate_PAY-1001_release      --role product_owner --by po1 --harness fake   # exit 0, "run PAY-1001: completed"
asac status --run-id PAY-1001
asac evidence show PAY-1001
asac evidence verify PAY-1001
asac audit --run-id PAY-1001
```

Attendus :

| Commande | Exit | Sortie |
|---|---|---|
| `apply` | **2** | `run PAY-1001: waiting for gate gate_PAY-1001_requirements` |
| 1ʳᵉ `approve` | 0 | `gate … approved by po1` puis `waiting for gate gate_PAY-1001_verification` |
| 3ᵉ `approve` | 0 | `run PAY-1001: completed` |
| `evidence show` | 0 | 8 preuves (`spec_reviewed`, `tests_green`, `mr_created`, `deps_verified`, `coverage_passed`, `sast_clean`, `qa_approved`, `deployed`) |
| `evidence verify` | 0 | toutes les exigences satisfaites |

> `approve` **reprend automatiquement** le run ; son exit reste 0 même si la reprise se bloque (lire le message).
> Utilise `--no-resume` pour seulement enregistrer la décision, puis `asac apply --resume <run>`.

## 3. Gates : rôle, rejet, réouverture

```bash
# 3a. mauvais rôle → exit 3
asac apply -p feature --run-id RJ-1 --harness fake
asac approve gate_RJ-1_requirements --role developer --by dev1                 # exit 3 : requires role 'product_owner'

# 3b. rejet sans commentaire → exit 1
asac approve gate_RJ-1_requirements --role product_owner --by po1 --reject     # exit 1 : a rejection needs a comment

# 3c. rejet avec commentaire → run failed au prochain apply
asac approve gate_RJ-1_requirements --role product_owner --by po1 --reject --comment "spec incomplète"   # exit 0
asac apply --resume RJ-1 --harness fake                                         # exit 1 : failed at requirements: … rejected
asac apply --resume RJ-1 --reopen --harness fake                                # exit 2 : gate rouverte, attend à nouveau
```

> `--reopen` ne fonctionne que sur un run **failed** (sinon `only a failed run can be reopened`).

## 4. Gouvernance (chaque cas est un run indépendant)

### 4a. Budget de tokens

```bash
asac apply -f asac.gov-budget.yaml -p feature --run-id BUD-1 --harness fake                                  # exit 2
asac approve -f asac.gov-budget.yaml gate_BUD-1_requirements --role product_owner --by po1 --harness fake
```

Attendu : `run BUD-1: blocked at verification: token budget exceeded (3,000 > 2,500)`. Le run passe `blocked`
(le 3ᵉ step dépasse le budget). Penser à passer `-f` à `approve` sinon la reprise utilise l'`asac.yaml` nominal.

### 4b. Policy OPA bloquante (separation of duties)

`separation.rego` est portée par le step `verification` et lit le rapport du harnais.

```bash
asac apply -p feature --run-id SEP-1 --harness fake
ASAC_FAKE_RESULT='{"dev_agent":"x","qa_agent":"x"}' \
  asac approve gate_SEP-1_requirements --role product_owner --by po1 --harness fake
```

Attendu : `blocked at verification: separation of duties: agent 'x' cannot both develop and verify`.
Prérequis : binaire `opa` dans le `PATH` (sinon la policy échoue en *fail closed*).

### 4c. Hook post_step (gel de release)

```bash
asac apply -p feature --run-id FZ-1 --harness fake
touch FREEZE
asac approve gate_FZ-1_requirements --role product_owner --by po1 --harness fake
rm FREEZE
```

Attendu : `blocked at development: hook 'freeze-check' failed: freeze-check: release gelée (fichier FREEZE présent)`.
Le step `development` est bloqué. Après `rm FREEZE`, `asac apply --resume FZ-1 --harness fake` reprend :
exit 2, `waiting for gate gate_FZ-1_verification` (le step `development` passe alors).

### 4d. Kill

```bash
asac apply -p feature --run-id K-1 --harness fake
asac kill K-1 --by admin --reason "incident"      # exit 0, "run K-1 killed"
asac status --run-id K-1                          # K-1  feature  killed
asac apply --resume K-1 --harness fake            # exit 3, "run K-1: run was killed; it cannot be resumed"
```

### 4e. Step `delegate` sans runner

```bash
asac apply -p feature --run-id DEL-1 --harness fake
ASAC_FAKE_DELEGATE=1 asac approve gate_DEL-1_requirements --role product_owner --by po1 --harness fake
```

Attendu : `run DEL-1: failed at development: harness delegated the step but no runner is placed`.
L'`approve` sort en 0 (il reprend le run) ; c'est `asac status --run-id DEL-1` qui montre `failed`.
Avec un runner (`runner_kind: docker` dans les vars ou `ASAC_RUNNER=docker`), la commande est exécutée dans le conteneur.

### 4f. Expiration d'une gate

```bash
asac apply -p feature --run-id EXP-1 --harness fake                    # exit 2, gate requirements (timeout 24h)
ASAC_FIXED_TIME=2099-01-01T00:00:00Z asac apply --resume EXP-1 --harness fake   # exit 1
```

Attendu : `run EXP-1: failed at requirements: gate gate_EXP-1_requirements expired`.
L'expiration est constatée au `apply --resume` : `asac gates --status expired` ne liste rien, la gate reste `pending` tant qu'on ne reprend pas le run.

## 5. Vrais harnais en mode hand-off (sans les exécuter)

```bash
cp vars/handoff.yaml asac.vars.yaml
asac validate -f asac.assist.yaml                    # exit 0
asac apply -f asac.assist.yaml -p feature --run-id HO-1
```

Attendu : exit **2**, `requirements handed to a person (brief: …/briefs/HO-1/requirements.md)`.
Vérifier ensuite : `cat .asac-state/briefs/HO-1/requirements.md` et les fichiers montés par le harnais
(`AGENTS.md` pour codex, `.agent/skills/<s>/SKILL.md` pour antigravity).

Le fichier `AGENTS.md` (harnais codex) est monté à la racine.

Pour avancer sans agent, jouer le travail du harnais à la main (chaque `apply -f asac.assist.yaml` doit garder `-f`) :

```bash
asac evidence bootstrap HO-1 -f asac.assist.yaml --evidence spec_reviewed --by po1 --no-resume   # exit 0, "recorded spec_reviewed (bootstrapped by po1)"
asac apply -f asac.assist.yaml --resume HO-1                     # exit 2, la gate gate_HO-1_requirements s'ouvre
asac approve -f asac.assist.yaml gate_HO-1_requirements --role product_owner --by po1 --no-resume   # exit 0
asac apply -f asac.assist.yaml --resume HO-1                     # exit 2, "development handed to a person"
```

> L'`approve` avant le premier `resume` échoue : `error: gate 'gate_HO-1_requirements' not found` (exit 1).
> Chaque step suivant se rejoue de la même façon (preuves via `evidence bootstrap`, puis `resume`).

Repasser ensuite sur `cp vars/team.yaml asac.vars.yaml`.

## 6. Manifestes invalides (validation)

Chaque commande doit sortir **exit 1** avec le code indiqué :

```bash
for f in asac.neg-*.yaml; do echo "== $f"; asac validate -f "$f"; done
```

| Fichier | Code | Message |
|---|---|---|
| `asac.neg-unknown-agent.yaml` | ASAC002 | `unknown agent 'ghost'` |
| `asac.neg-cycle.yaml` | ASAC008 | `dependsOn contains a cycle` |
| `asac.neg-missing-evidence.yaml` | ASAC009 | `'qa_approved' is not produced by any upstream step` |
| `asac.neg-missing-policy.yaml` | ASAC011 | `path '.asac/policies/absent.rego' does not exist` |
| `asac.neg-gate-no-role.yaml` | ASAC020 | `human gate needs a role` |
| `asac.neg-bad-duration.yaml` | ASAC023 | `invalid duration '3 jours'` |

Variantes par fichier de valeurs :

```bash
asac validate --vars vars/bad-delegate-copilot.yaml   # exit 1, ASAC013 (×2 : development et release)
asac validate --vars vars/bad-harness.yaml            # exit 1, ASAC015 unknown harness 'no-such-tool'
asac validate -f asac.assist.yaml --vars vars/bad-delegate-copilot.yaml   # exit 0 : en assist, copilot est accepté
```

## 7. Déclenchement par webhook Jira (daemon)

```bash
cp vars/team.yaml asac.vars.yaml
ASAC_WEBHOOK_SECRET=s3cret asac daemon --port 18765 &     # choisir un port libre
sleep 3
curl -s localhost:18765/healthz                            # {"status":"ok"}

BODY='{"webhookEvent":"jira:issue_created","issue":{"key":"PAY-1001","fields":{"issuetype":{"name":"Story"},"labels":["asac-enabled"]}}}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac s3cret | sed 's/^.* //')

curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:18765/webhooks/jira \
  -H "Content-Type: application/json" -H "X-Hub-Signature-256: sha256=$SIG" -d "$BODY"     # 200
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:18765/webhooks/jira \
  -H "Content-Type: application/json" -H "X-Hub-Signature-256: sha256=00" -d "$BODY"       # 401

kill %1
```

Le trigger du manifeste filtre `issuetype: Story` et `labels: [asac-enabled]` (toutes les valeurs doivent être présentes).
Le run créé s'appelle `run_feature_PAY-1001` (le corps `Story` + label `asac-enabled` renvoie `{"status":"accepted",...}`).
Pour tester le filtre : `issuetype` = `Bug` ou label absent renvoient `{"status":"ignored","runs":[]}` (HTTP 200, aucun run créé).
Si le port est pris (`address already in use`), en choisir un autre.

## 8. Nettoyage

```bash
cd / && rm -rf "$WORK"
```

## Écarts connus entre la doc et le CLI

- `asac plan --trigger …` n'existe pas (exit 2).
- Le run id est auto-généré (`run_feature_0001`) si on ne passe pas `--run-id`, donc l'id de gate l'est aussi (`gate_run_feature_0001_requirements`).
- `approve` reprend automatiquement le run et retourne 0 même si la reprise se bloque ; seule la sortie texte (ou `asac status`) l'indique.
