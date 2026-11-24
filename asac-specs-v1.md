# ASAC : spécifications fonctionnelles v1

**Statut : GELÉ le 2026-11-24.** Version 0.1.x du produit, version 1.0 de ce document.

Ce fichier est la source de référence pour construire la v1. Un thread d'exécution le lit de haut en bas, livre les fonctionnalités du § 6 dans l'ordre du § 7 et vérifie chacune avec ses critères d'acceptation. Le périmètre général reste `SCOPE_V1.md` ; pour la liste des fonctionnalités et leurs critères, ce fichier fait foi. Toute modification passe par une entrée au registre du § 17.

ASAC (Agentic SDLC as Code) décrit en code le cycle de développement d'une équipe qui travaille avec des agents IA : les étapes, les preuves exigées à chaque étape, les rôles qui approuvent, les règles qui encadrent l'agent et le budget. ASAC exécute ce cycle, pilote l'outil de l'agent, mesure son coût et tient un journal d'audit en ajout seul.

## 1. Besoin principal

Une équipe qui fait écrire du code par des agents veut :

1. décrire son cycle une fois, dans un fichier versionné et relisible ;
2. exiger une preuve à chaque étape, produite par un contrôle, une politique ou une personne ;
3. faire approuver par le bon rôle une version précise du code ;
4. garder une trace complète : qui a fait quoi, sur quel commit, à quel coût ;
5. tenir les règles hors de portée de l'agent qu'elles encadrent ;
6. choisir, pour chaque run, entre un travail manuel aidé par l'agent et un travail automatique ;
7. confier un run à un agent qui travaille seul, sur un serveur ou en CI.

**Le résultat d'un run est une branche git `asac/<run>` prête à fusionner**, dont chaque étape est approuvée sur un commit précis.

## 2. Parcours

```
asac init                          création du manifeste et de l'arborescence .asac/
asac vars check                    contrôle des valeurs
asac validate                      contrôle du manifeste
asac apply -p feature              création du run, du worktree et de la branche asac/<run>
  pour chaque étape, dans l'ordre de dependsOn :
    preuves requises présentes
    hooks pre_tool
    travail : la personne (assist), l'agent lancé par ASAC (autorun) ou l'agent d'un runner (delegate)
    boucle : contrôles de loop.until, relance de l'agent avec l'erreur, jusqu'au plafond
    hooks post_step, contrôle d'intégrité, budgets
    commit de l'étape par ASAC, sha enregistré
    gate sur ce sha : décision du rôle déclaré
asac approve <gate>                preuve liée au sha, étape suivante
asac audit / evidence verify       relecture
asac learn <run>                   proposition d'amélioration tirée des échecs
asac clean <run>                   retrait du worktree, branche conservée
```

## 3. Concepts

| Concept | Définition |
|---|---|
| **Pipeline** | Suite d'étapes ordonnée par `dependsOn`. Un pipeline par type de travail (`feature`, `hotfix`). |
| **Étape** (`step`) | Unité de travail : une capacité, un agent, un mode, des preuves requises et produites, une gate. |
| **Capacité** (`capability`) | Ce qui doit être accompli (spécification, implémentation) et les preuves attendues. |
| **Skill** | Consigne de travail rattachée à une capacité, écrite dans un fichier local. |
| **Agent** | Un skill, un fournisseur de modèle et un harness (l'outil qui travaille, par exemple Claude Code). |
| **Preuve** (`evidenceType`) | Attestation nommée qu'une étape est faite (`spec_reviewed`, `tests_green`). Immuable, datée, liée à un commit. |
| **Gate** | Point de décision attaché à une étape. Le run attend la décision. |
| **Run** | Une exécution d'un pipeline, avec son identifiant, son worktree et sa branche `asac/<run>`. |
| **Worktree** | Copie de travail git propre au run. Tout le travail du run y a lieu. |
| **Hook** | Contrôle déterministe : un script qui rend 0 pour réussir. |
| **Politique** | Règle Rego évaluée par OPA, en échec fermé. |
| **Budget** | Plafond par run ou par étape : tokens, coût, durée, itérations. |
| **Runner** | Environnement d'exécution d'une étape `delegate` (conteneur Docker en v1). |
| **Worker** | Processus qui prend des runs dans la file de jobs et les exécute. |
| **Audit** | Journal en ajout seul de tous les événements d'un run. |

## 4. Fichiers d'un projet

| Fichier | Contenu |
|---|---|
| `asac.yaml` | Manifeste : capacités, types de preuves, skills, agents, instructions, hooks, budgets, pipelines. Versionné. |
| `asac.vars.yaml` | Valeurs des variables et réglages d'exécution (outil, `autorun`, bac à sable, runner). Local, exclu de git. |
| `asac.vars.yaml.example` | Modèle des valeurs, versionné. |
| `.asac/skills/` | Skills, en Markdown. |
| `.asac/instructions/` | Instructions du projet : conventions, règles, contrat de sortie. |
| `.asac/hooks/` | Scripts de contrôle. |
| `.asac/policies/` | Politiques Rego. |
| `.asac/proposals/` | Propositions d'amélioration écrites par `asac learn`. |
| `.asac-state/` | État des runs : base SQLite, audit, livrables, worktrees, file de jobs. Local, exclu de git. |

## 5. Fonctionnalités disponibles

Ces fonctionnalités existent dans le code. Elles restent à contrôler par les scénarios du § 12.

### 5.1 Déclaration et validation

- **F1. Validation du manifeste.** `asac validate` contrôle la structure, les références croisées (capacités, skills, agents, hooks, preuves, instructions) et la compatibilité entre mode et harness. Chaque anomalie porte un code : `ASAC001` à `ASAC015` et `ASAC017` à `ASAC027` pour le contenu du manifeste, `ASAC000` pour un fichier illisible. Une clé acceptée et réservée à une version ultérieure produit un avertissement `ASAC027`.
- **F2. Manifeste strict.** Une clé inconnue est une erreur. Une clé écrite deux fois est une erreur.
- **F3. Variables.** Les valeurs viennent de `asac.vars.yaml` ou de l'environnement. `asac vars check` signale une variable déclarée sans valeur et sans défaut ; `asac vars diff` liste les variables manquantes et inutilisées. `asac validate` refuse une référence `var.<nom>` dont la variable est absente de `variables` (`ASAC014`).
- **F4. Dépendances.** Une étape démarre quand toutes les étapes de `dependsOn` sont terminées. Un cycle est une erreur.
- **F5. Preuves chaînées.** Une étape démarre quand toutes ses `requiresEvidence` existent. Elle déclare ses `producesEvidence`.
- **F6. Plan.** `asac plan` affiche l'ordre des étapes, les gates et une estimation de tokens. C'est une lecture seule.
- **F7. Initialisation.** `asac init [chemin]` crée `asac.yaml` et l'arborescence `.asac/` (`policies`, `hooks`, `knowledge`, `instructions`). Il détecte la pile du projet. `--template` choisit le modèle (`minimal` par défaut, ou `feature`), `--name` le nom du workspace, `--force` remplace les fichiers existants.

### 5.2 Exécution d'un run

- **F8. Lancement.** `asac apply -p <pipeline>` crée le run, son worktree et sa branche. `--run-id` fixe l'identifiant. `--watch` garde la commande au premier plan et continue après chaque décision.
- **F9. Lancement en une commande.** `asac run [étape]` crée un run et l'exécute, avec les mêmes codes de sortie qu'`asac apply`. Avec un nom d'étape, seule cette étape s'exécute, après contrôle de ses dépendances et de ses preuves requises.
- **F10. Worktree par run.** Chaque run travaille dans `.asac-state/worktrees/<run>`, sur la branche `asac/<run>`, créée depuis `HEAD`. Le dépôt doit être un dépôt git propre, avec au moins un commit.
- **F11. Commit par étape.** À la fin de chaque étape, ASAC commite le travail dans le worktree et enregistre le sha (`step.committed`). Les fichiers de cache et d'état sont exclus du commit.
- **F12. Reprise.** `asac apply --resume <run>` reprend un run à l'étape où il s'est arrêté.
- **F13. Arrêt définitif.** `asac kill <run>` arrête un run (`run.killed`). Le moteur vérifie l'arrêt avant chaque étape.
- **F14. Nettoyage.** `asac clean <run>` retire le worktree (`workspace.removed`) et conserve la branche pour la revue.
- **F15. Relance sur incident.** `retries` (0 à 5) relance une étape dont l'outil ou le runner a échoué. Chaque relance est auditée (`step.retry`).
- **F16. Codes de sortie.** 0 terminé, 1 erreur, 2 en attente (gate ou travail manuel), 3 bloqué (politique, budget, hook, rôle, arrêt).

### 5.3 Conduite manuelle ou automatique

L'étape déclare son mode (`mode: assist` par défaut). Le run choisit la conduite.

- **F17. Conduite manuelle.** En l'absence d'`autorun`, ASAC écrit le brief et les skills dans le worktree, applique les hooks et indique où travailler. La personne travaille avec son outil, aidée de l'agent si elle le veut, puis rend l'étape avec `asac submit <run>`.
- **F18. Rendu contrôlé.** À `asac submit`, les contrôles de l'étape s'exécutent. La preuve est enregistrée quand ils réussissent ; en cas d'échec, l'étape revient à la personne avec la raison. Le rendu est audité (`step.submitted`) avec son auteur.
- **F19. Conduite automatique.** Avec `autorun` (`ASAC_AUTORUN=1` ou `autorun: true`), ASAC lance l'outil dans le worktree avec le brief dans le prompt (`tool.launched`), attend sa fin dans la limite de `autorun_timeout` (900 secondes par défaut), puis applique les contrôles et ouvre la gate.
- **F20. Même gouvernance.** Le pipeline, les gates, les preuves et les règles sont identiques dans les deux conduites. Le passage de l'une à l'autre se fait par la variable `autorun`.

### 5.4 Boucle jusqu'à validation

- **F21. Boucle.** `loop: { until: [hooks], max_iterations: N }` sur une étape. Après chaque tour, ASAC exécute les contrôles de `until`. Quand l'un échoue, l'agent est relancé avec la sortie du contrôle. Chaque tour est audité (`step.iteration`).
- **F22. Plafond.** `max_iterations` est obligatoire, de 1 à 50. Au plafond, l'étape passe en échec avec la raison du dernier contrôle.
- **F23. Relance après rejet.** Sous `autorun`, un rejet motivé relance l'agent avec le motif dans son brief, puis l'étape revient à la même gate. Plafond : `max_iterations` de la boucle, ou 2 relances.

### 5.5 Contrôles

- **F24. Hooks globaux.** `hooks.pre_tool` s'exécute sur chaque étape, avant que l'agent travaille. `hooks.post_step` s'exécute sur chaque étape, après le travail.
- **F25. Hooks par étape.** `steps.<id>.hooks.pre_tool` et `.post_step` ajoutent des hooks déclarés dans `hooks.definitions`. Les hooks globaux passent en premier ; un hook présent aux deux endroits s'exécute une fois.
- **F26. Effet d'un hook.** `on_fail: block` (défaut) arrête l'étape ; `on_fail: warn` enregistre l'échec et continue. Chaque résultat est audité avec son moment (`pre_tool` ou `post_step`) : `hook.passed` pour une réussite, `hook.failed` pour un échec.
- **F27. Contexte du hook.** Le hook est lu depuis le dépôt principal et s'exécute sur le worktree du run, qu'il reçoit dans `ASAC_WORKTREE`.
- **F28. Politiques Rego.** Une étape (`policies`) ou une gate `quality` cite des fichiers `.rego`. OPA les évalue. Une règle `block` arrête l'étape avec ses raisons ; une règle `escalate` ouvre une gate d'escalade, qu'une personne décide. Une erreur d'évaluation bloque.

### 5.6 Protection des règles

- **F29. Contrôle d'intégrité.** Autour du lancement de l'outil par ASAC, le moteur calcule l'empreinte de `asac.yaml`, `asac.vars.yaml` et `.asac/` dans le dépôt principal avant et après. Une différence bloque l'étape et écrit `integrity.violated` avec les chemins. Une étape intacte écrit `integrity.verified`.
- **F30. Bac à sable local.** Avec `ASAC_SANDBOX=1`, l'outil s'exécute sous `srt`. L'écriture est limitée au worktree et au dossier temporaire de l'outil. La lecture des secrets (`~/.ssh`, clés, `.env` hors worktree) est refusée. Le réseau est limité à la passerelle du modèle et aux domaines listés dans `sandbox_domains`.
- **F31. Refus audités.** Chaque refus du bac à sable est écrit dans l'audit (`sandbox.denied`) avec le fichier ou l'hôte visé, jusqu'à 20 par étape.

### 5.7 Consignes et autonomie

- **F32. Instructions.** Les fichiers de `instructions` sont projetés dans le fichier de consignes de l'outil (`CLAUDE.md` pour Claude Code). Un agent qui liste ses instructions reçoit celles-là ; l'agent qui en est dépourvu reçoit toutes celles du projet.
- **F33. Skills montés.** Le skill de l'agent est écrit dans le format natif de l'outil (`.claude/skills/<skill>/SKILL.md`), dans le worktree.
- **F34. Autonomie.** `autonomy: readonly` lance Claude Code en mode `plan`, le mode de l'outil réservé à la lecture et à la proposition ; en conduite manuelle, le brief demande à la personne de garder les fichiers intacts. `autonomy: autonomous` exige au moins une instruction déclarée.

### 5.8 Budgets

- **F35. Tokens par run** (`budgets.per_run.tokens`).
- **F36. Coût par run** (`budgets.per_run.cost_usd`). Quand une étape rend un coût inconnu, le budget bloque le run.
- **F37. Durée par run** (`budgets.per_run.wall_clock`), vérifiée avant chaque étape.
- **F38. Itérations par étape** (`budgets.per_step.iterations`).
- **F39. Coût réel.** Le coût, les tokens et le nombre de tours viennent de la sortie JSON de `claude -p` et sont enregistrés (`spend.recorded`). Derrière une passerelle, ce coût est l'estimation de l'outil.

Tout dépassement bloque le run (`step.blocked`) avec la valeur atteinte et le plafond.

### 5.9 Gates et preuves

- **F40. Gate humaine.** `gate: { type: human, role, timeout }`. Le run attend la décision d'une personne du rôle indiqué.
- **F41. Gate qualité.** `gate: { type: quality, role, policy }`. La politique Rego rend le verdict ; le rôle désigne la personne responsable.
- **F42. Rôle obligatoire.** Une gate `human` ou `quality` déclare un rôle (`ASAC020`).
- **F43. Décision.** `asac approve <gate> --by <nom> --role <rôle>` approuve, puis reprend le run. `--reject --comment "<motif>"` rejette, avec un motif obligatoire. `--no-resume` enregistre la décision seule. La décision est enregistrée avec le rôle, l'auteur et le sha du commit. Un rôle insuffisant bloque la commande avec le code de sortie 3.
- **F44. Réouverture.** `asac apply --resume <run> --reopen` rouvre une gate rejetée.
- **F45. Expiration.** Une gate dont le `timeout` est dépassé passe à l'état expiré (`gate.expired`).
- **F46. Preuve par l'approbation.** L'approbation produit les preuves de l'étape (`evidence.produced`), au nom de l'étape et liées à son commit.
- **F47. Vérification.** `asac evidence verify` contrôle les preuves d'un run ; `asac evidence show` les affiche.
- **F48. Preuve importée.** `asac evidence bootstrap` enregistre une preuve produite en dehors d'ASAC, comme une revue externe (`evidence.bootstrapped`). Elle est marquée comme importée.

### 5.10 Observation

- **F49. Statut.** `asac status` liste les runs, ou les étapes d'un run.
- **F50. Décisions en attente.** `asac gates` liste les gates, celles en attente en premier.
- **F51. Journal d'un run.** `asac logs <run>` affiche l'audit du run dans l'ordre.
- **F52. Audit.** `asac audit` affiche le journal, en texte ou en CSV. Les événements `sandbox.denied` et `integrity.violated` sont affichés avec leur détail.
- **F53. Livrables.** La sortie complète de l'outil est stockée comme livrable, avec son empreinte sha256 (`artifact.stored`).
- **F54. Notifications.** Retenues pour la v1 (décision du 2026-11-24). `ASAC_NOTIFY` envoie `gate.opened`, `step.blocked`, `step.escalated` et `step.failed` vers un webhook signé, Slack, Teams ou e-mail. Un envoi qui échoue est audité (`notify.failed`) et le run continue. La vérification par envoi réel est la fonctionnalité F67.
- **F55. Propositions d'amélioration.** `asac learn <run>` écrit dans `.asac/proposals/<run>.md` la liste des échecs, blocages et escalades du run (`proposal.written`). La personne la relit et modifie le manifeste elle-même.

### 5.11 Diagnostic

- **F56. Prérequis.** `asac doctor` vérifie git, opa, node (22.12 ou plus), srt, claude, et l'état du dépôt (dépôt git, arbre propre, un commit au moins). Chaque échec indique la commande de correction.

## 6. Fonctionnalités à livrer

Chaque fonctionnalité donne : l'objectif, les fichiers à lire, les critères d'acceptation. Une fonctionnalité est livrée quand tous ses critères sont vérifiés, que le contrôle global du § 8 est vert et que la documentation du § 9 reflète le comportement.

### Lot A. Parcours du développeur

#### F64. Commandes `init`, `run`, `vars`, `learn` visibles

- **Objectif.** Ces quatre commandes figurent dans `asac --help` avec les autres commandes de la v1.
- **Fichiers.** `src/asac/cli/__init__.py` (déclarations `app`, `vars_app`, `init`, `run`, `learn`), `tests/test_help_scope.py`.
- **Critères.**
  1. `asac --help` liste `init`, `run`, `vars` et `learn`, en plus des commandes du § 10.
  2. Le texte d'aide de l'application énumère les commandes de la v1.
  3. L'aide de `run` décrit le comportement réel : créer un run et l'exécuter, ou exécuter une seule étape.
  4. `portal`, `daemon` et `project` restent accessibles par leur nom et absents de `asac --help`.
  5. `tests/test_help_scope.py` reflète cette liste.

#### F65. Variables avant le premier fichier de valeurs

- **Objectif.** `asac vars check` et `asac vars diff` fonctionnent dans un projet qui vient d'être créé.
- **Fichiers.** `src/asac/cli/__init__.py` (`_var_report`, `vars_check`, `vars_diff`), `tests/test_validate.py`.
- **Critères.**
  1. En l'absence de `asac.vars.yaml`, `asac vars check` liste chaque variable déclarée sans défaut (`missing: <nom>`) et sort avec le code 1.
  2. Dans le même cas, `asac vars diff` liste les mêmes variables et sort avec le code 1.
  3. Le message « not found » disparaît.
  4. Avec un `asac.vars.yaml` complet, les deux commandes sortent avec le code 0.

#### F66. Gabarit `feature` exécutable

- **Objectif.** `asac init --template feature` crée un projet qui valide, dont chaque fichier référencé existe, et qui atteint sa première gate.
- **Fichiers.** `src/asac/cli/__init__.py` (`init`, `TEMPLATES`, `detect_stack`), nouveau dossier `src/asac/templates/feature/`, `tests/test_golden.py`, `tests/test_validate.py`, nouveau `tests/test_init_run.py`.
- **Contenu du gabarit.**
  - `asac.yaml` : une variable `tool`, un fournisseur `llm`, les capacités `specification_engineering` et `implementation`, les preuves `spec_reviewed` et `tests_green`, deux skills locaux, deux agents, une instruction, trois hooks (`no-secrets` en `pre_tool` global, `spec-present` sur l'étape `requirements`, `tests-green` sur l'étape `development`), le pipeline `feature` avec deux gates `human` de rôle `product_owner`.
  - `.asac/skills/spec.md`, `.asac/skills/impl.md`, `.asac/instructions/style.md`.
  - `.asac/hooks/no-secrets.sh`, `spec-present.sh`, `tests-green.sh`, exécutables. `tests-green.sh` lance `python3 -m unittest discover`.
  - `asac.vars.yaml.example` avec `tool: claude-code`.
  - Le nom du workspace remplace le marqueur `__NAME__`.
- **Critères.**
  1. `asac init --template feature` dans un dossier vide crée tous les fichiers ci-dessus.
  2. `asac validate` rend `0 error(s), 0 warning(s)`.
  3. `.gitignore` est créé ou complété avec `asac.vars.yaml` et `.asac-state/`, une seule fois chacun, en préservant les lignes existantes.
  4. Les fichiers déjà présents sont conservés tant que `--force` est absent ; `--force` les remplace.
  5. Les scripts sont lus depuis le paquet installé : le wheel contient `asac/templates/feature/` et `asac init` fonctionne depuis un environnement vierge où seul le wheel est installé.
  6. Sur une pile autre que Python, `init` indique qu'il faut adapter `.asac/hooks/tests-green.sh`.
  7. Le parcours `init`, `asac vars check` (code 1), copie de l'exemple vers `asac.vars.yaml`, `asac vars check` (code 0), `git commit`, `asac apply -p feature --harness claude-code` atteint l'attente d'un travail manuel (code 2) ; après un `SPEC.md` contenant « Acceptance criteria », `asac submit` ouvre `gate_<run>_requirements`.
  8. `--template minimal` crée un manifeste vide valide, seul fichier créé.

#### F63. Validation du parcours délégué

- **Objectif.** `asac validate` signale à l'écriture du manifeste qu'une étape `delegate` demande un runner.
- **Fichiers.** `src/asac/validate/checks.py` (contrôle de `mode`, code `ASAC013` existant), `tests/test_validate.py`.
- **Critères.**
  1. Une étape `mode: delegate` sans `execution.runner` produit une erreur `ASAC028`, avec le chemin `pipelines.<p>.steps.<s>.execution`.
  2. Une étape `mode: delegate` avec `execution.runner` valide.
  3. `execution.fallback: assist` reste accepté ; son effet est décrit par F57, critère 7.
  4. `ASAC028` est ajouté à la plage de codes citée par F1.

#### F68. Documentation alignée

- **Objectif.** Chaque document décrit le comportement des commandes livrées.
- **Fichiers.** `README.md` (ligne de statut), `docs/reference/cli.md`, `docs/getting-started/quickstart.md`, `tests/functional/01-new-project/README.md`, `CHANGELOG.md`.
- **Critères.**
  1. `docs/reference/cli.md` décrit `init` (options `--template`, `--name`, `--force`), `run`, `vars check`, `vars diff`, `learn` (observations, rien d'appliqué) et chaque commande du § 10.
  2. L'option `--mode observe` de `init` disparaît de la documentation.
  3. Le quickstart déroule `init`, `vars check`, `validate` et `apply` avec les options qui existent.
  4. `tests/functional/01-new-project/README.md` donne les sorties attendues du gabarit `feature`.
  5. `CHANGELOG.md` liste les fonctionnalités de ce lot sous « Unreleased ».
  6. `.venv/bin/zensical build --strict` réussit.

### Lot B. Notifications

#### F67. Notifications vérifiées par envoi réel

- **Objectif.** Chaque cible de F54 reçoit un vrai message, lu par un processus distinct.
- **Fichiers.** `src/asac/adapters/notify.py`, `tests/test_notifications.py` (existant, avec enregistreur), nouveau `tests/test_notify_live.py`.
- **Critères.**
  1. Un récepteur HTTP et un récepteur SMTP tournent dans des processus séparés du test, sur des ports locaux libres, et écrivent chaque requête reçue dans un fichier.
  2. Cible `webhook+` : le message reçu contient `kind: gate.opened`, l'identifiant du run, l'identifiant de la gate et le rôle ; l'en-tête `X-ASAC-Signature` vaut `sha256=` suivi du HMAC-SHA256 du corps avec `ASAC_WEBHOOK_SECRET`.
  3. Cible `slack+` : le corps JSON porte la clé `text` avec le titre de la notification.
  4. Cible `teams+` : le corps JSON porte une carte `AdaptiveCard` avec le titre.
  5. Cible `smtp://` : le serveur reçoit un message avec les en-têtes `From`, `To` et `Subject` attendus. Le chemin STARTTLS reste couvert par un test unitaire.
  6. Une cible injoignable listée avant une cible joignable : le run atteint sa gate, la cible joignable reçoit son message, l'audit contient `notify.failed`.
  7. Le message d'erreur d'un envoi raté nomme le type d'échec (par exemple `delivery failed: ConnectError`) et omet l'URL et les identifiants de la cible.
  8. Le fichier de test porte les marqueurs `integration` et `enable_socket` et s'exécute avec `ASAC_NOTIFY_LIVE=1`.
  9. `ASAC_WEBHOOK_SECRET` et `notify_targets` (références `${vault...}`) figurent au § 11.

### Lot C. Parcours délégué

Le runner Docker existe dans `src/asac/adapters/runner_local.py` avec l'image générique `python:3.12-slim`, le réseau `none`, un système de fichiers en lecture seule et un projet monté en lecture seule. Le lot le porte jusqu'à un agent réel. Le moteur appelle le runner depuis `src/asac/engine/apply.py` (`_place`, `_exec_in_runner`).

#### F58. Image de l'agent

- **Fichiers.** Nouveau dossier `docker/agent/` (Dockerfile), `src/asac/adapters/runner_local.py` (`DEFAULT_IMAGE`, `runner_from_vars`), `src/asac/doctor.py`.
- **Critères.**
  1. Le Dockerfile construit une image qui contient `claude`, `git` et `python3`, et dont l'étiquette porte la version d'ASAC.
  2. `docker run --rm <image> claude --version` affiche une version.
  3. `runner_image` par défaut désigne cette image.
  4. `asac doctor` signale l'image présente ou absente, avec la commande de construction.

#### F59. Montages

- **Fichiers.** `src/asac/adapters/runner_local.py` (`DockerRunner.command`), `tests/test_runner_docker_real.py`.
- **Critères.**
  1. Le conteneur reçoit le worktree du run seul, monté en écriture.
  2. Le dépôt principal (`asac.yaml`, `.asac/`, scripts de hooks) et `.asac-state/` restent hors du conteneur.
  3. Le conteneur conserve l'utilisateur sans privilèges, `--cap-drop ALL`, `no-new-privileges` et les limites de ressources en vigueur.
  4. Le travail de l'agent écrit dans le conteneur se retrouve dans le worktree de l'hôte.

#### F61. Identifiants

- **Fichiers.** `src/asac/adapters/runner_local.py` (`env`, `_redact`, `runner_env`).
- **Critères.**
  1. Les variables nommées dans `runner_env` sont transmises au conteneur par leur nom, la valeur étant lue dans l'environnement du processus ASAC.
  2. La valeur d'une variable transmise est remplacée par un masque dans les sorties de runner, l'audit (`runner.output`), les livrables et les messages d'erreur.
  3. Un test écrit une clé de test dans l'environnement, lance un agent factice qui l'affiche, et constate le masque dans l'audit et le livrable.

#### F60. Réseau du conteneur

- **Fichiers.** `src/asac/adapters/runner_local.py` (`network`, `runner_network`), `src/asac/doctor.py`, `src/asac/engine/apply.py` (événement `runner.started`).
- **Critères.**
  1. Le réseau par défaut est `none`.
  2. `runner_network` désigne un réseau Docker préparé par l'opérateur, dont la sortie vers la passerelle du modèle est réglée hors d'ASAC.
  3. L'événement `runner.started` consigne le réseau utilisé.
  4. `asac doctor` signale un réseau nommé introuvable.
  5. La documentation indique que le filtrage par domaine et l'audit des refus réseau relèvent d'une version ultérieure (§ 16).

#### F57. Parcours délégué

- **Fichiers.** `src/asac/engine/apply.py` (`_place`, `_exec_in_runner`, `_run_harness`, `_finish_step`), `src/asac/adapters/claude_code.py` (branche `delegate`), `src/asac/adapters/runner_local.py`.
- **Critères.**
  1. Un run dont une étape déclare `mode: delegate` et `execution: { runner: docker }` exécute `claude -p` dans le conteneur de F58 et laisse le travail de l'agent dans le worktree.
  2. Le coût, les tokens et les tours lus dans la sortie JSON sont enregistrés (`spend.recorded`) et comptés dans les budgets.
  3. `step.loop` s'applique : un contrôle de `until` en échec relance l'agent dans le conteneur avec la sortie du contrôle ; chaque tour est audité (`step.iteration`).
  4. Un rejet motivé relance l'agent sous les plafonds de F23.
  5. Le contrôle d'intégrité de F29 entoure l'exécution dans le conteneur (`integrity.verified` ou `integrity.violated`).
  6. Le commit de l'étape et la gate sur son sha suivent F11 et F40.
  7. `execution.fallback: assist` rend l'étape à une personne quand le runner est indisponible (`runner.unavailable`).
  8. Les événements `runner.started`, `runner.output` (avec empreinte sha256) et `runner.stopped` apparaissent dans l'audit, et la sortie complète est un livrable.

#### F62. Worker

- **Fichiers.** `src/asac/ports/jobs.py`, `src/asac/adapters/jobs_sqlite.py`, `src/asac/adapters/jobs_postgres.py`, `src/asac/cli/__init__.py` (nouvelle commande `worker`, option `--enqueue` de `apply`), `src/asac/engine/runtime.py`, nouveau `src/asac/engine/worker.py`.
- **Critères.**
  1. `asac apply -p <pipeline> --enqueue` place un job de type `run` dans la file (SQLite dans `.asac-state/`) avec le pipeline, l'identifiant du run et le harness, puis rend la main avec le numéro du job.
  2. `asac worker` prend les jobs dans l'ordre, un à la fois, crée le run, l'exécute, puis marque le job terminé quand le moteur rend un résultat stable (terminé, en attente de gate, bloqué).
  3. Un résultat d'erreur du moteur marque le job en échec avec sa raison et le replace dans la file jusqu'à 5 tentatives (`fail`, `max_attempts`).
  4. Un bail de job expiré rend le job à la file (`claim` reprend un job `running` dont le bail est échu).
  5. `asac worker --once` traite les jobs présents et s'arrête.
  6. Le worker affiche une ligne par job : numéro, run, résultat.
  7. Le worker utilise le runner et le harness de la configuration, comme `asac apply`.
  8. `asac worker` rejoint la liste du § 10 et de `asac --help`.

#### F69. Vérification du parcours délégué

- **Fichiers.** Nouveau `tests/test_delegate_hostile.py`, `tests/test_runner_docker_real.py`, `tests/test_real_claude.py`.
- **Critères.**
  1. Un agent factice hostile, lancé par le runner Docker, tente quatre actions : modifier un hook, modifier `asac.yaml`, lire `~/.ssh`, appeler un hôte externe. Chaque tentative échoue, et le disque de l'hôte le confirme (fichiers intacts).
  2. Le contrôle d'intégrité et les hooks jugent le travail du worktree, y compris quand l'agent a écrit dans sa propre copie de `asac.yaml`.
  3. Un test avec le vrai `claude` dans le conteneur produit une spécification dans le worktree et un coût réel dans l'audit ; il s'exécute avec `ASAC_REAL_CLAUDE=1`.
  4. Les deux fichiers de test s'ignorent proprement quand Docker ou l'image est absent.

## 7. Ordre d'exécution

| Étape | Fonctionnalités | Dépendance |
|---|---|---|
| 1 | F64, F65, F63 | — |
| 2 | F66 | F64, F65 |
| 3 | F68 | F64, F65, F66 |
| 4 | F67 | — |
| 5 | F58, F59, F61 | — |
| 6 | F60 | F59 |
| 7 | F57 | F58, F59, F60, F61, F63 |
| 8 | F62 | F57 |
| 9 | F69 | F57 |

Les étapes 1 à 4 et 5 à 9 forment deux suites indépendantes.

## 8. Règles de travail du thread d'exécution

- **Branche.** `v1-scope`. Un commit par fonctionnalité, message en anglais, dont la première ligne cite la fonctionnalité (`F66: ...`).
- **Contrôle global.** Avant chaque commit, depuis le dossier `asac/` :
  1. `.venv/bin/ruff check .`
  2. `.venv/bin/ruff format --check .`
  3. `.venv/bin/mypy --strict src`
  4. `.venv/bin/python -m pytest -q -n auto -p no:cacheprovider`

  Les tests se lancent par `python -m pytest` du venv du dépôt, qui importe le code de ce dépôt.
- **Sockets.** Les tests ouvrent des sockets uniquement avec le marqueur `enable_socket`, comme `tests/conformance/test_state_store.py`.
- **Périmètre.** Une demande hors de ce fichier va dans le § 16 et reste à l'état de proposition jusqu'à une entrée du § 17.
- **Écarts.** Quand le code contredit un critère, le code suit le critère. Quand un critère se révèle impossible, le thread s'arrête sur cette fonctionnalité, consigne la raison dans son compte rendu et passe à la suivante de l'ordre.
- **Vérité d'abord.** Une fonctionnalité passe en « supportée » quand ses critères sont vérifiés contre le vrai système ; seul un scénario réel suffit, un test avec double reste un test unitaire (`SCOPE_V1.md`, § 6, règle 4).
- **Rédaction des documents.** Les textes décrivent ce que fait ASAC ; le style du fichier présent sert de modèle.

## 9. Documentation à tenir à jour

Pour chaque fonctionnalité livrée : la ligne correspondante de `docs/reference/cli.md` ou du guide concerné, `CHANGELOG.md` (« Unreleased »), le § 12 de ce fichier quand un nouveau scénario apparaît. `README.md` reprend la liste des commandes de la v1.

## 10. Commandes

Les commandes de `asac --help` :

| Commande | Rôle |
|---|---|
| `asac init` | Créer `asac.yaml` et l'arborescence `.asac/` (F7, F66) |
| `asac doctor` | Vérifier les prérequis (F56) |
| `asac validate` | Contrôler le manifeste (F1) |
| `asac vars check`, `asac vars diff` | Contrôler les variables (F3, F65) |
| `asac plan` | Afficher l'ordre, les gates et l'estimation (F6) |
| `asac apply` | Lancer ou reprendre un run ; `--enqueue` le met en file (F8, F12, F62) |
| `asac run` | Créer un run et l'exécuter, ou exécuter une seule étape (F9) |
| `asac submit` | Rendre une étape faite à la main (F18) |
| `asac gates` | Lister les décisions (F50) |
| `asac approve` | Approuver ou rejeter (F43) |
| `asac status` | Suivre les runs (F49) |
| `asac logs` | Lire l'audit d'un run (F51) |
| `asac audit` | Lire et exporter l'audit (F52) |
| `asac evidence` | Afficher, vérifier ou importer des preuves (F47, F48) |
| `asac learn` | Écrire une proposition d'amélioration (F55) |
| `asac kill` | Arrêter un run (F13) |
| `asac clean` | Retirer le worktree (F14) |
| `asac worker` | Exécuter les runs de la file (F62) |
| `asac version` | Afficher la version |

Les commandes `portal`, `daemon` et `project` appartiennent au portail (§ 16).

## 11. Réglages d'exécution

| Réglage | Variable d'environnement | Effet |
|---|---|---|
| `autorun` | `ASAC_AUTORUN` | Conduite automatique du run |
| `autorun_timeout` | `ASAC_AUTORUN_TIMEOUT` | Durée maximale d'un lancement de l'outil, en secondes (900) |
| `sandbox` | `ASAC_SANDBOX` | Bac à sable `srt` pour la conduite automatique |
| `sandbox_domains` | `ASAC_SANDBOX_DOMAINS` | Domaines autorisés en plus de la passerelle du modèle |
| `retries` | `ASAC_RETRIES` | Relances sur incident, de 0 à 5 |
| `runner_kind`, `runner_image`, `runner_network`, `runner_env` | `ASAC_RUNNER` | Runner du parcours délégué (F57 à F61) |
| `notify_targets` | `ASAC_NOTIFY` | Cibles des notifications ; `notify_targets` liste des références `${vault...}` |
| — | `ASAC_WEBHOOK_SECRET` | Clé de signature HMAC des webhooks |
| — | `ASAC_STATE_DIR` | Emplacement de l'état |
| — | `ASAC_NOTIFY_LIVE` | Active `tests/test_notify_live.py` |
| — | `ASAC_REAL_CLAUDE` | Active les tests avec le vrai `claude` |

Le réglage `parallel` (étapes indépendantes simultanées) existe dans le dépôt. La v1 fixe l'exécution à une étape à la fois.

## 12. Vérification de chaque fonctionnalité

Une fonctionnalité est supportée quand un scénario exécuté contre le vrai système la couvre. Le tableau nomme le scénario de référence ; le thread d'exécution l'étend selon les critères du § 6.

| Fonctionnalités | Scénario de référence |
|---|---|
| F1 à F6, F8, F10 à F16 | `tests/functional/01-new-project`, `tests/functional/02-feature` |
| F7, F9, F3, F55, F64, F65, F66 | `tests/test_init_run.py`, `tests/functional/01-new-project` |
| F17 à F20 | `tests/functional/02-feature`, `tests/test_submit.py` |
| F21 à F23 | `tests/test_loop.py`, `tests/test_rejection_retry.py` |
| F24 à F28 | `tests/functional/02-feature`, `tests/functional/03-hotfix` |
| F29 à F31 | `tests/test_integrity.py`, `tests/test_adversarial.py` |
| F32 à F34 | `tests/functional/04-onboarding` |
| F35 à F39 | `tests/test_claude_cost.py`, `tests/functional/02-feature` |
| F40 à F48 | `tests/functional/02-feature`, `tests/test_run_e2e.py` |
| F49 à F53 | `tests/functional/02-feature` |
| F54, F67 | `tests/test_notifications.py`, `tests/test_notify_live.py` |
| F56 | `tests/test_doctor.py` |
| F57 à F63, F69 | `tests/test_runner_docker_real.py`, `tests/test_delegate_hostile.py`, `tests/test_real_claude.py` |

## 13. Règles

### 13.1 Preuve

- **R1.** Une preuve est immuable une fois produite.
- **R2.** Une preuve est liée au sha du commit de son étape.
- **R3.** Une étape démarre quand toutes ses preuves requises existent.
- **R4.** Une étape produit sa preuve après la réussite de tous ses contrôles : à l'approbation quand elle porte une gate, à la fin de l'étape quand elle se termine seule.
- **R5.** Le résultat d'un run est sa branche `asac/<run>`. La fusion est faite par une personne.

### 13.2 Décision

- **R6.** Une gate est décidée par une personne du rôle déclaré.
- **R7.** Toute décision est enregistrée avec le rôle, l'auteur et le sha approuvé.
- **R8.** Tout rejet porte un motif écrit.
- **R9.** L'identité de l'approbateur est celle déclarée sur la ligne de commande (`--by`, `--role`).

### 13.3 Protection des règles

- **R10.** Les hooks, les politiques, `asac.yaml` et `.asac/` sont lus depuis le dépôt principal.
- **R11.** Quand ASAC lance l'outil (conduite automatique), toute modification de `asac.yaml`, `asac.vars.yaml` ou `.asac/` pendant l'étape la bloque. En conduite manuelle, la personne travaille avec ses propres droits : les hooks de l'étape (F18) contrôlent le résultat.
- **R12.** Sous bac à sable, l'agent écrit uniquement dans le worktree et le dossier temporaire de l'outil.
- **R13.** Le commit de l'étape est fait par ASAC, hors de la zone d'écriture de l'agent.
- **R14.** Dans un runner, l'agent reçoit le worktree seul ; le dépôt principal et l'état restent hors du conteneur.

### 13.4 Exécution

- **R15.** Un run démarre avec son worktree, ou il échoue.
- **R16.** Toute boucle a un plafond, de 1 à 50.
- **R17.** Toute relance après rejet a un plafond.
- **R18.** Un run arrêté par `asac kill` reste arrêté.
- **R19.** Une étape `mode: delegate` déclare un runner.

### 13.5 Coût

- **R20.** Le coût enregistré est celui que rend l'outil.
- **R21.** Un budget de coût exige que chaque étape rende son coût.
- **R22.** Le budget est vérifié après chaque étape et chaque tour de boucle.

### 13.6 Audit

- **R23.** L'audit est en ajout seul.
- **R24.** Chaque événement porte un type, une date, un auteur et un détail ; ceux d'une étape portent son identifiant.
- **R25.** Un hook est audité à chaque exécution : `hook.passed` ou `hook.failed`. L'intégrité est auditée à chaque lancement de l'outil par ASAC : `integrity.verified` ou `integrity.violated`.
- **R26.** Chaque sortie de l'outil est enregistrée avec son empreinte sha256.
- **R27.** Les secrets restent dans l'environnement du processus ; l'audit, les livrables et les journaux en portent le masque.

## 14. Événements d'audit

Chaque événement est écrit par le moteur (`asac apply`, `asac approve`, `asac submit`, `asac worker`) ou par la commande indiquée.

| Famille | Événements |
|---|---|
| Run | `run.created`, `run.completed`, `run.killed` (`asac kill`) |
| Espace de travail | `workspace.created`, `workspace.removed` (`asac clean`), `workspace.failed`, `commit.failed` |
| Étape | `step.started`, `step.completed`, `step.failed`, `step.blocked`, `step.escalated`, `step.handoff`, `step.submitted`, `step.retry`, `step.iteration`, `step.committed` |
| Gate | `gate.opened`, `gate.reopened`, `gate.expired`, `rejection.handled`, `attempt.after_rejection` |
| Preuve et livrable | `evidence.produced`, `evidence.bootstrapped` (`asac evidence bootstrap`), `artifact.stored`, `artifact.refused` |
| Contrôle | `hook.passed`, `hook.failed`, `integrity.verified`, `integrity.violated`, `sandbox.denied` |
| Exécution | `tool.launched`, `spend.recorded`, `runner.started`, `runner.output`, `runner.stopped`, `runner.unavailable` |
| Apprentissage | `proposal.written` (`asac learn`) |
| Notification | `notify.failed` |

Le portail et le daemon écrivent `gate.denied`, `run.triggered`, `tools.exposed` et les événements d'administration et d'édition de pipeline. Ils appartiennent à la suite de la v1.

## 15. Conditions d'usage de la v1

| Sujet | Condition |
|---|---|
| Outil de l'agent | Claude Code |
| Système | macOS pour le bac à sable `srt` ; Docker pour le parcours délégué |
| État | SQLite local |
| Identité | Déclarée en ligne de commande |
| Coût | Estimation fournie par l'outil |
| Réseau du parcours délégué | Réseau `none` par défaut ; réseau préparé par l'opérateur pour joindre la passerelle du modèle |
| Résultat | Branche `asac/<run>`, fusionnée par une personne |
| Ordre des étapes | Une étape à la fois |
| Notifications | Webhook signé, Slack, Teams, SMTP |
| Gabarit `feature` | Projet Python |

## 16. Suite de la v1

Création de la MR en fin de run, départ d'un run depuis un ticket, identité authentifiée par le portail, étapes en parallèle, autorun par étape, second harness, filtrage réseau par domaine et audit des refus réseau sous Docker, gabarits d'autres piles, registre de skills et de hooks signés, pattern `critic`, routage multi-modèles, orchestration multi-agents, portail et daemon. Les références `${vault...}` accompagnent les intégrations (forges, trackers, wikis, serveurs MCP). Détail : `docs/project/roadmap.md`.

## 17. Registre des modifications

Ce document est gelé. Un changement s'écrit ici avant d'être appliqué : date, changement, raison, décideur.

| Date | Changement | Raison | Décidé par |
|---|---|---|---|
| 2026-11-24 | Gel de la version 1.0 du document. Quatre commandes (`init`, `run`, `vars`, `learn`) rejoignent `asac --help`. Les notifications (F54) restent dans la v1. Le gabarit `feature` devient un projet Python exécutable. `asac learn` reste une liste d'observations. | Consigne du porteur du 2026-11-24 : un autre thread lit ce fichier et livre les fonctionnalités. | Porteur du projet |
