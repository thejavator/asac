# 01 — Scénario « Nouveau projet » (`docs/scenarios/new-project.md`)

On part d'un dépôt Java vide (juste un `pom.xml`), on crée le projet ASAC, on renseigne les valeurs,
on valide, on planifie, on lance un premier run et on ouvre le portail.

## Contenu du dossier

| Fichier | Rôle |
|---|---|
| `pom.xml` | Fixture : permet à `asac init` de détecter la stack `java` |
| `asac.vars.yaml.example` | Modèle des valeurs (secrets en `${vault.…}`) |
| `vars/team.yaml` | Valeurs prêtes à l'emploi (copie du modèle) |

Le gabarit `feature` est un projet complet à deux étapes ; le manifeste « payments » de `../02-feature/` (4 étapes, 3 gates) vient à l'étape 4.

## 0. Préparation

```bash
export PATH="$ASAC_HOME/.venv/bin:$PATH"
export ASAC_AUTORUN=0
SRC=$ASAC_HOME/tests/functional
WORK=$(mktemp -d) && cp "$SRC/01-new-project/pom.xml" "$WORK/" && cd "$WORK"
export ASAC_STATE_DIR="$WORK/.asac-state"
```

## 1. Créer le projet

```bash
asac init --template java-microservice     # exit 1 : modèle inconnu
asac init --template feature               # exit 0
ls -A
```

Attendus :

| Commande | Exit | Sortie |
|---|---|---|
| `init --template java-microservice` | **1** | `error: unknown template 'java-microservice' (minimal, feature)` |
| `init --template feature` | 0 | `created asac.yaml (stack: java, template: feature)`, puis `next: cp asac.vars.yaml.example asac.vars.yaml, then asac vars check` et `note: the tests-green hook runs python3 -m unittest; edit .asac/hooks/tests-green.sh for a java project` |

Résultat : `asac.yaml`, `asac.vars.yaml.example`, `.gitignore` (`asac.vars.yaml` et `.asac-state/`, une ligne chacun),
et `.asac/` avec `skills/` (`spec.md`, `impl.md`), `instructions/style.md` et `hooks/` (`no-secrets.sh`,
`spec-present.sh`, `tests-green.sh`, exécutables), à côté du `pom.xml`. La pile Java est détectée : `init` dit
d'adapter `tests-green.sh`, qui lance `python3 -m unittest`.

Relancer `init` sans `--force` quand un fichier du modèle existe refuse et ne change rien
(`error: .asac/hooks/no-secrets.sh exists (use --force)`) ; avec `--force` il remplace.

```bash
asac init --template feature               # exit 1 (déjà existant)
asac init --template minimal --force       # exit 0 : remplace asac.yaml par un manifeste vide
asac init --template feature --force       # revient au modèle feature
```

## 2. Renseigner les valeurs

Avant tout fichier de valeurs, `vars` liste ce qui manque au lieu d'échouer :

```bash
asac vars check          # exit 1 : "missing: tool"
asac vars diff           # exit 1 : "missing: tool"
cp asac.vars.yaml.example asac.vars.yaml
asac vars check          # exit 0
asac vars diff           # exit 0
```

`asac.vars.yaml` ne doit jamais être committé ; `init` l'a déjà ajouté au `.gitignore`.

## 3. Valider et planifier

```bash
asac validate            # exit 0 : "0 error(s), 0 warning(s)"
asac plan -p feature     # exit 0 : "pipeline feature: 2 steps in 2 levels", "estimated tokens: 40,000"
```

Le plan montre `requirements` (gate `human`, rôle `product_owner`, produit `spec_reviewed`) puis
`development` (requiert `spec_reviewed`, produit `tests_green`, même gate). Pour le parcours jusqu'à la
première gate, voir `docs/getting-started/quickstart.md` (et `tests/test_init_run.py`, qui le déroule).

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
- Le hook `tests-green.sh` du modèle `feature` est écrit pour Python : sur une pile Java, `init` le dit et il faut l'adapter.
