# 01 — Scénario « Nouveau projet » (`docs/scenarios/new-project.md`)

On part d'un dépôt Java vide (juste un `pom.xml`), on crée le projet ASAC, on renseigne les valeurs,
on valide, on planifie, on lance un premier run et on ouvre le portail.

## Contenu du dossier

| Fichier | Rôle |
|---|---|
| `pom.xml` | Fixture : permet à `asac init` de détecter la stack `java` |
| `asac.vars.yaml.example` | Modèle des valeurs (secrets en `${vault.…}`) |
| `vars/team.yaml` | Valeurs prêtes à l'emploi (copie du modèle) |

Le manifeste complet vient de `../02-feature/` (étape 5) : `asac init` ne génère qu'un squelette.

## 0. Préparation

```bash
export PATH="/Users/tahrielmedhi/IBM/sldc-agentic/asac/.venv/bin:$PATH"
export ASAC_AUTORUN=0
SRC=/Users/tahrielmedhi/IBM/sldc-agentic/asac/tests/functional
WORK=$(mktemp -d) && cp "$SRC/01-new-project/pom.xml" "$WORK/" && cd "$WORK"
export ASAC_STATE_DIR="$WORK/.asac-state"
```

## 1. Créer le projet

```bash
asac init --template java-microservice     # exit 1 — voir « Écarts »
asac init --template feature               # exit 0
ls -A
```

Attendus :

| Commande | Exit | Sortie |
|---|---|---|
| `init --template java-microservice` | **1** | `error: unknown template 'java-microservice' (minimal, feature)` |
| `init --template feature` | 0 | `created asac.yaml (stack: java, template: feature)` |

Résultat : `asac.yaml` (1 pipeline `feature`, 1 step `development`) à côté du `pom.xml`.
Relancer `init` sans `--force` quand `asac.yaml` existe refuse (`error: asac.yaml exists (use --force)`) ; avec `--force` il écrase.

```bash
asac init --template feature               # exit 1 (déjà existant)
asac init --template minimal --force       # exit 0
asac init --template feature --force       # revient au template feature
```

## 2. Renseigner les valeurs

```bash
cp "$SRC/01-new-project/asac.vars.yaml.example" .
cp "$SRC/01-new-project/vars/team.yaml" asac.vars.yaml
asac vars check          # exit 0
asac vars diff           # exit 0
```

`asac.vars.yaml` ne doit jamais être committé ; les secrets restent des références `${vault.…}`.

## 3. Valider et planifier le squelette

```bash
asac validate            # exit 0 — "1 warning(s)" : ASAC017 registry reference not resolved (skill impl)
asac plan                # exit 0 — "pipeline feature: 1 steps in 1 levels", "estimated tokens: 20,000"
asac apply -p feature --run-id NP-1 --harness fake   # exit 0 — "run NP-1: completed"
```

L'avertissement ASAC017 est normal : le skill du template pointe vers un registre non résolu (pas d'erreur).

## 4. Passer au manifeste complet « payments »

On remplace le squelette par le manifeste de l'exemple (4 steps, 3 gates, hooks, policies).

```bash
cp "$SRC/02-feature/asac.yaml" asac.yaml
cp -R "$SRC/02-feature/.asac" .
asac validate            # exit 0, "0 error(s), 0 warning(s)"
asac plan -p feature     # 4 steps, "estimated tokens: 400,000 / budget 2,000,000"
asac apply -p feature --run-id PAY-1001 --harness fake   # exit 2, attend gate_PAY-1001_requirements
asac status --run-id PAY-1001                            # requirements gate_waiting
```

La suite (approbations, rejets, gouvernance) est décrite dans `../02-feature/README.md`.

## 5. Portail (mode dev)

```bash
ASAC_ENV=dev asac portal --data "$WORK/portal-data" --port 18080 &
sleep 3
curl -s localhost:18080/api/v1/login-options
kill %1
```

Attendu : JSON `{"mode":"dev","personas":[po, auditor, dev, admin],"organization":"Organization"}`.
La racine `/` répond par une redirection (303). Sans `ASAC_ENV=dev`, les personas de dev ne sont pas proposées.

## 6. Nettoyage

```bash
cd / && rm -rf "$WORK"
```

## Écarts connus entre la doc et le CLI

- `asac init --template java-microservice` n'existe pas : seuls `minimal` et `feature` sont disponibles.
- `asac plan --pipeline feature --trigger jira:PAY-1001` : `--trigger` n'existe pas (la commande est `asac plan -p feature`).
- `asac init` ne crée pas `asac.vars.yaml.example`, `.asac/policies/default.rego` ni `.gitignore`.
