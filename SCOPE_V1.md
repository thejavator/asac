# ASAC v1 : périmètre minimal à livrer

Statut : **GELÉ le 2026-11-23**, puis **élargi le même jour** par le lot 5 (runner Docker et `delegate`, § 7 et § 12.3). Ce document est le périmètre de la première version (ASAC 0.1.x). Il remplace l'ordre de priorités de `TACHES.md` pour la première livraison. Le périmètre ne change plus sans une entrée écrite dans le registre du § 12.3 ; les règles du gel sont au § 12.

**Changement par rapport à la version du 2026-11-20.** La comparaison avec Archon a montré qu'une v1 qui se contente de piloter `claude -p` sur le dépôt de l'utilisateur ne tient pas face à un orchestrateur existant. La v1 inclut donc l'**exécution réelle isolée** : worktree par run, boucle jusqu'à validation, bac à sable, mesure du coût. Le reste du périmètre reste minimal.

**Précision du 2026-11-21.** Ce qui est hors v1 n'est pas secondaire : c'est ce qui distingue ASAC d'Archon (identité des approbateurs, registre signé, neutralité vis-à-vis de l'agent, preuves et politiques avancées, gouvernance d'entreprise). La v1 le **diffère** sans le sacrifier : voir le § 6, qui impose des règles de conservation et fixe ce que la v1 doit garantir pour ne pas le perdre.

## État d'avancement (2026-11-23, au gel)

**Fait et vérifié.** Relancé le 2026-11-23 : `ruff` propre, `mypy --strict` propre (79 fichiers), 698 tests
passés, 6 ignorés (vrai `claude`, Postgres, Docker), 3 `xfail` connus. Les docs `--strict` n'ont pas été
relancées au gel. Contenu : worktree par run, coût réel, commit par étape lié à la gate, `asac clean`,
`step.loop` avec relance automatique, relance après un rejet motivé (plafonnée), bac à sable `srt`
(preuve par contrôle inverse), contrôle d'intégrité des règles (audité), refus du bac à sable audités,
`asac doctor`, `asac submit` (parcours manuel), hooks déclarés par étape, avertissement ASAC027,
RUNBOOK suivi à la lettre, chemins personnels retirés, `--help` limité, version 0.1.0.
Deux runs réels de bout en bout avec Claude Code sous le bac à sable (coût 0,13 et 0,16 USD).

**Non fait, à ne pas présenter comme fait :**
- ~~Aucun test d'intégration réel automatisé.~~ **Fait (2026-11-23)** : `tests/test_real_claude.py`, trois tests avec le vrai `claude` sur un projet qui n'est pas l'exemple (spécification, hook, gate, preuve). Ignorés sauf `ASAC_REAL_CLAUDE=1` (ils coûtent environ 0,12 à 0,30 USD l'un). Le test du bac à sable prouve que l'outil réel **fonctionne** sous `srt`, pas que le bac à sable **bloque** : l'agent réel refuse de lui-même de sortir du worktree, avec ou sans bac à sable (contrôle fait). Le blocage est prouvé par `tests/test_adversarial.py`.
- La boucle n'a pas tourné avec le vrai agent (seulement avec un faux outil).
- Quand l'agent a reçu la consigne d'attaquer les règles, il a **refusé** : la preuve que le bac à sable bloque vient des faux outils hostiles, pas du vrai agent.
- Le bac à sable ne couvre ni `delegate` ni les autres outils ; réseau limité à la passerelle du modèle ; macOS seulement ; Linux non testé.
- ~~Les tentatives refusées par l'OS ne sont pas dans l'audit.~~ **Corrigé (2026-11-23)** : chaque refus du bac à sable est écrit dans l'audit (`sandbox.denied`, avec le fichier ou l'hôte), et `asac audit` l'affiche. Limite : il est relu dans la sortie de l'outil et le journal de `srt`, donc un refus que l'outil n'imprime pas (il peut avaler l'erreur) n'est pas vu.
- Vérification avec IBM (propriété intellectuelle, noms Bob, wxO, ICA, textes TLT) : **décision humaine**, voir `TACHES.md`.
- Un test de la suite a échoué une fois sans être reproduit (voir le commit `0e653f9`).
- Nommage du schéma : `max_iterations` (snake_case) contre `dependsOn` (camelCase), mais aussi `on_fail`, `per_run`, `cost_usd` : le langage mélange déjà les deux. À trancher avant de geler.
- Rien n'est publié : tag local seulement, aucun push.
- `autorun` est **global** (variable `ASAC_AUTORUN` ou `autorun` dans les vars) : on ne peut pas, dans un même run, laisser l'agent seul sur une étape et garder une autre à la main. Le choix manuel ou automatique se fait par run (§ 4.2).
- Trois défauts connus, marqués `xfail` avec leur raison (`tests/test_rejection_retry.py`) : sans `autorun`, la raison d'un rejet n'est pas mise dans le brief que la personne lit ; une relance bloquée par un hook est retentée à chaque reprise ; reprendre un run en échec relance l'étape et rouvre sa gate rejetée sans décision.
- Les hooks ne s'attachent qu'à deux points (§ 1.1) : il n'y a pas de contrôle à chaque appel d'outil de l'agent.

## 1. Objectif

Livrer une version que **quelqu'un d'autre que son auteur peut installer et faire tourner sur un vrai dépôt en 30 minutes, avec la garantie que l'agent n'a pas pu tricher**.

Hypothèse à valider :

> Une équipe qui fait écrire du code par des agents IA veut **déclarer les preuves exigées à chaque étape, faire valider par un humain une version précise du code, et garder une trace infalsifiable**, le tout sans que l'agent puisse modifier les règles qui le contrôlent.

La dernière partie de la phrase est ce qui distingue ASAC d'Archon : Archon exécute, ASAC **prouve et contraint**. L'exécution n'est là que pour que la preuve porte sur du vrai travail.

### 1.1 Promesse produit et discours

Ajouté au gel (2026-11-23). Le discours est celui d'un pipeline de bout en bout que l'on pilote à la main ou que l'on laisse tourner seul. Formulation retenue pour la v1 :

> **De la spécification à une branche prête à fusionner, un seul pipeline déclaré, que vous le pilotiez à la main ou que vous le laissiez tourner seul.** À chaque étape : skills chargés, règles forcées, contrôles avant et après, consignes de sécurité, budget, puis une gate validée par le bon rôle (PO, dev, QA) sur un commit précis. Le niveau d'automatisation change ; la gouvernance ne change pas.

**Ordre du discours.** (1) La garantie : les règles sont hors de portée de l'agent, l'approbation est liée à un commit, l'audit est en ajout seul. (2) Le curseur manuel ou automatique, qui montre que personne n'est forcé. (3) Le bout en bout, comme horizon : « le même pipeline peut aller jusqu'à la MR et au déploiement ». Le bout en bout est l'endroit où ASAC rivalise avec les orchestrateurs existants (§ 11) ; il ne doit pas passer en premier.

**Ce que la v1 tient, élément par élément du discours :**

| Élément du discours | Dans la v1 | Précision |
|---|---|---|
| Gates PO, dev et QA par rôle, sur un commit | Oui | `role` par gate ; identité **déclarée** en CLI (`--by`, `--role`), non authentifiée |
| Skills et instructions chargés par étape | Oui | Claude Code seulement |
| Règles forcées | Oui | Rego en échec fermé ; contrôle d'intégrité (`integrity.violated`) ; bac à sable `srt` (`ASAC_SANDBOX=1`, macOS) |
| Contrôles avant et après | Oui, à **deux points** | `pre_tool` s'exécute **avant que l'agent travaille**, pas avant chaque appel d'outil ; `post_step` après l'étape. Hooks globaux ou par étape (`steps.<id>.hooks`) |
| Instructions de sécurité | Oui, comme **consignes** | Une consigne n'est pas une garantie : ce qui garantit, c'est le bac à sable et le contrôle d'intégrité |
| Gestion du budget | Oui | Itérations et coût par run ; le coût est l'**estimation** de Claude Code ; un coût inconnu bloque un budget de coût |
| Boucle jusqu'à validation | Oui | `step.loop`, plafond obligatoire ; relance après un rejet motivé sous `autorun`, plafonnée |
| Pilotage manuel, aidé par l'agent et ASAC | Oui | `assist` sans `autorun`, puis `asac submit` |
| Automatisation du pipeline | Oui, **au niveau du run** | `autorun` global (§ 4.2) |
| Départ depuis un ticket (Jira, Monday) | **Non** | Le texte du ticket n'atteint pas l'agent ; voir `docs/project/roadmap.md`. Candidat v1.1 |
| Ouverture de la MR en fin de run | **Non** | Le run se termine sur la branche `asac/<run>`, que l'humain fusionne. `open_change_request` n'est appelé que par l'éditeur de pipeline du portail. Candidat v1.1 (§ 6, ordre n° 2) |
| Déploiement | **Non** | ASAC ne déploie pas. À terme : déclencher la CD existante et vérifier le résultat (`canary_healthy`, `post_deploy_verified`, backlog v0.5) |
| Autres agents (Codex, Cursor, Bob, Copilot) | **Non** | Présents, testés avec des fakes, non supportés |

**Ce que la v1 ne dit pas.** Elle ne dit pas « automatise de bout en bout », ni « jusqu'au déploiement », ni « sans surveillance » : la phrase vraie est « de la spécification à une branche prête à fusionner ».

**Réponse à l'objection « la CI et la protection de branche suffisent ».** La CI juge le résultat final, hors de portée de l'agent, et ASAC ne prétend pas faire mieux sur ce point. Il apporte ce qu'elle ne fait pas : des gates **intermédiaires** (spécification validée par le PO avant le développement), une boucle locale qui renvoie l'erreur à l'agent, des preuves typées chaînées d'étape en étape, un budget par étape. Si les testeurs ne trouvent pas de valeur à ces quatre points, ASAC n'est qu'une CI locale : c'est un signal d'arrêt, à lire dans les retours du § 9.

## 2. Le parcours unique

```
asac validate
asac apply
  └─ crée un worktree + une branche asac/<run> (hors de l'espace de l'agent pour les règles)
  └─ pour chaque étape :
       agent lancé dans le bac à sable, dans le worktree
       ┌─ boucle : hooks et règles Rego ; si échec, l'agent reprend avec l'erreur ─┐
       └───────────── jusqu'à validation ou plafond d'itérations ─────────────────┘
       commit dans le worktree, sha enregistré dans l'audit
       gate humaine sur ce sha
asac approve  →  preuve liée au sha  →  étape suivante
asac audit / evidence verify / clean
```

Tout ce qui n'est pas sur ce chemin est hors scope de la v1.

## 3. État réel des quatre capacités à ajouter

**Historique : ce tableau décrit l'état du 2026-11-20, avant les lots 1 à 3.** Les quatre capacités sont construites depuis ; l'état courant est dans « État d'avancement ». Le tableau est conservé pour expliquer pourquoi elles étaient nécessaires.

Constaté dans le code (lecture) et sur une copie de `examples/real-tools` (exécution, 2026-11-20).

| Capacité | Aujourd'hui | Ce qu'il faut |
|---|---|---|
| **Exécution réelle** | Fonctionne : `claude -p` est lancé (`autorun`), les hooks passent, la gate s'ouvre. Mais l'agent tourne **dans le dépôt de l'utilisateur** (`cwd=ctx.root`, `acceptEdits`) et le coût n'est pas mesuré (`tokens=0 cost_usd=0.0000`). Le mode `delegate` + Docker n'a jamais été exécuté pour de vrai | Lancer l'agent dans un worktree, lire le coût et les tokens réels, un seul chemin d'exécution |
| **Worktree** | **Absent** (aucune occurrence dans `src/`) | À construire |
| **Boucle** | **Absente.** Il n'existe qu'un `retry` sur erreur du harness, et un plafond `per_step.iterations` qui compare une valeur rapportée par le harness. Un hook `post_step` qui échoue arrête l'étape, sans renvoyer l'erreur à l'agent | À construire |
| **Bac à sable** | **Inutilisable pour un vrai agent** (d'après le code de `DockerRunner`) : image `python:3.12-slim` sans `claude`, projet monté en lecture seule, `--network none` donc aucun accès à l'API du modèle, et `/work` limité à 64 Mo | À construire sur une autre base (voir § 5.4) |

**Trou de sécurité confirmé par le spike C (2026-11-21) :** les hooks, les politiques `.rego`, `asac.yaml` et la base d'état (`.asac-state`) sont dans le dépôt où l'agent a le droit d'écrire. Lancé avec les options actuelles de `autorun`, un agent a réécrit `tests-green.sh` pour qu'il réussisse, modifié `asac.yaml` et supprimé le dossier d'état. Le bac à sable et le worktree doivent fermer ce trou ; c'est le critère d'acceptation central de la v1.

## 4. Dans le scope

### 4.1 Langage (sous-ensemble de la spec v0.4)

| Primitive | Inclus | Précision |
|---|---|---|
| `asac.yaml` + `asac.vars.yaml` | oui | |
| `capabilities`, `evidenceTypes`, `skills` (locaux), `agents` | oui | Références locales uniquement |
| `pipelines` / `steps` | oui | `dependsOn`, `requiresEvidence`, `producesEvidence`, `mode` |
| `gate` humaine | oui | `role`, `timeout`, rejet motivé |
| `hooks` | oui | `pre_tool`, `post_step`, scripts locaux, `on_fail: block` |
| Politiques Rego | oui | Échec fermé |
| `budgets` | oui | `per_step.iterations` **et** `per_run.cost_usd` (devient fiable grâce à la mesure réelle) |
| `instructions` | oui | |
| **Nouveau** : `step.loop` | oui | Voir § 5.3. Extension de la couche 1 ; la spec v0.4 reste gelée, on documente l'extension |
| **Nouveau** : `sandbox` (bloc de la couche 2) | oui | Domaines réseau autorisés, chemins protégés |

**Règle de livraison : tout ce qu'accepte `validate` doit être appliqué par le moteur.** Toute clé hors sous-ensemble produit un avertissement « non pris en charge en v1 ».

### 4.2 Mode d'exécution

**Corrigé au gel (2026-11-23).** La version précédente annonçait « deux modes seulement » en décrivait trois, et présentait `delegate` comme le mode principal. Or `mode: delegate` passe par un **runner** (Docker ou Kubernetes), qui est hors v1 : sans runner, l'étape échoue (« harness delegated the step but no runner is placed »). La v1 n'a donc qu'un mode de déclaration supporté, `assist`, et **deux manières de le conduire** :

- **Manuelle** (`assist`, sans `autorun`) : ASAC crée le worktree, écrit le brief et les skills dedans, applique les hooks et les règles, puis attend. La personne travaille avec son outil (aidée de l'agent si elle le souhaite) et rend l'étape avec `asac submit` : les contrôles de l'étape tournent, la preuve n'est enregistrée que s'ils passent, puis la gate s'ouvre.
- **Automatique** (`assist` avec `autorun`, variable `ASAC_AUTORUN` ou `autorun` dans les vars) : ASAC lance `claude -p` dans le worktree (sous le bac à sable si `ASAC_SANDBOX=1`), mesure le coût réel, exécute la boucle `step.loop`, relance l'agent avec la raison d'un rejet motivé (plafonné), puis ouvre la gate. C'est le seul parcours où l'agent travaille sans personne devant l'écran.

Le pipeline, ses gates, ses preuves et ses règles sont **les mêmes** dans les deux cas : on passe de l'un à l'autre en changeant `autorun`, sans toucher à `asac.yaml`. **Limite :** `autorun` est global, donc le choix se fait par run, pas par étape (« QA automatique, développement à la main » n'est pas possible dans la v1). L'autorun par étape est un candidat v1.1.

**Ajouté au périmètre le 2026-11-23 (lot 5) :** `mode: delegate` avec le runner Docker, pour un agent qui tourne sans poste de développeur (CI, serveur, cluster). C'est le troisième parcours, distinct des deux autres :

- **Délégué** (`mode: delegate` + `execution.runner: docker`) : l'étape passe par le port `Runner`. L'agent tourne dans un conteneur, le worktree monté en écriture, les règles en lecture seule. Un **worker minimal** prend les runs dans la file de jobs et les exécute, sans que personne lance `asac apply`.

Le choix entre les parcours reste par étape pour `delegate`, et par run pour `autorun`. **`srt` reste le bac à sable du parcours local (`autorun`) ; Docker isole le parcours délégué.** Les deux backends sont prouvés par le même test hostile (§ 8.3). Il n'y a pas de Kubernetes ni de GitLab dans la v1 : ils restent hors v1.

**Sans autorun, l'agent tourne avec les droits de l'utilisateur** ; le worktree isole les fichiers produits, pas les autres accès, et le bac à sable ne couvre que le parcours automatique.

### 4.3 Commandes CLI (14 visibles)

`validate`, `plan`, `apply` (avec `--resume`), `status`, `gates`, `approve`, `submit`, `evidence show`, `evidence verify`, `audit`, `logs`, `kill`, `clean`, `version`, plus `doctor` pour les prérequis (`opa`, `claude`, `git`, outil de bac à sable, clé API). `submit` a été ajouté après la première rédaction, pour le parcours manuel (§ 4.2). Les autres commandes (`init`, `run`, `learn`, `portal`, `daemon`, `vars`, `project`) existent, sont masquées de `--help` et ne sont pas supportées.

### 4.4 Harness et état

Un seul harness (**Claude Code**), un seul état (**SQLite**, triggers append-only), étapes séquentielles avec reprise. Le runner Docker et le worker de la file de jobs entrent dans la v1 (lot 5) ; ils n'ajoutent ni harness ni état. Les étapes parallèles restent **hors v1** : le code existe (`ThreadPoolExecutor`, `parallel`), mais aucun test réel ne le couvre. Le parcours v1 reste séquentiel.

## 5. Les quatre capacités, définies au plus juste

### 5.1 Exécution réelle

- Lancer `claude -p … --output-format json` et lire le coût et les tokens dans la sortie. Le flag existe dans la version installée (2.1.327) ; **le contenu exact de la sortie reste à vérifier** au spike.
- Un seul chemin d'exécution, un seul format d'audit : `tool.launched`, `spend.recorded` (valeurs réelles), empreinte sha256 du log.
- Le budget `per_run.cost_usd` est vérifié après chaque itération.
- Authentification par clé API (`ANTHROPIC_API_KEY`) passée à l'agent par variable d'environnement, jamais écrite dans un fichier, masquée dans les logs.

### 5.2 Worktree

- `asac apply` crée `git worktree add <état>/worktrees/<run> -b asac/<run>` à partir de `HEAD`. Prérequis : dépôt git avec arbre propre (`doctor` le vérifie).
- Le harness écrit skills, `CLAUDE.md` et brief **dans le worktree**, jamais dans le dépôt principal.
- **À la fin de chaque étape, ASAC fait un commit dans le worktree et enregistre le sha dans l'audit.** La gate porte sur ce sha, et la preuve (`evidence`) y est liée. C'est ce qui rend l'approbation précise : on approuve « ce code-là », pas « l'état du dossier au moment du clic ».
- La gate affiche `git diff --stat` du sha concerné ; le diff complet est stocké comme artefact avec son sha256.
- Fin de run : la branche `asac/<run>` est conservée, et l'humain la fusionne. **Pas de création de PR en v1** (cela demanderait une forge). `asac clean <run>` supprime le worktree.

### 5.3 Boucle

Déclaration minimale, sur l'étape :

```yaml
steps:
  development:
    agent: developer
    mode: delegate
    loop:
      until: [tests-green, no-secrets]   # hooks et/ou politiques Rego qui doivent passer
      max_iterations: 5                  # plafond dur
```

Fonctionnement :

1. L'agent travaille dans le worktree.
2. ASAC exécute les contrôles de `until`.
3. Si un contrôle échoue et que le plafond n'est pas atteint, l'agent est relancé avec **la sortie du contrôle en échec** ; chaque tour est audité (`step.iteration n`, avec la raison).
4. Si tout passe, l'étape se termine (commit, gate).
5. Si le plafond est atteint, l'étape échoue ; l'escalade vers un humain existe déjà dans le moteur et est réutilisée.

Pas de boucle sans plafond, pas de conditions `when`, pas de sous-workflows : c'est tout ce qu'Archon offre de plus, et ce n'est pas nécessaire pour valider l'hypothèse.

### 5.4 Bac à sable

**Exigences** (identiques quel que soit l'outil retenu) :

| Ressource | Règle |
|---|---|
| Écriture | Uniquement dans le worktree et un dossier temporaire |
| Lecture refusée | `~/.ssh`, `~/.aws`, `~/.config` sensibles, fichiers `.env` hors worktree |
| **Protégés contre l'écriture** | `asac.yaml`, `.asac/` (hooks, politiques, skills), la base d'état et d'audit : ils sont exécutés **depuis le dépôt principal**, jamais depuis le worktree |
| Réseau | Refus par défaut ; liste blanche de domaines (API du modèle, plus ceux déclarés dans le bloc `sandbox`) |
| Durée et ressources | Délai maximal par itération |

**Choix de l'outil : `srt` retenu après le spike B (voir § 7). La comparaison initiale est conservée ci-dessous.**

| Option | Avantages | Risques |
|---|---|---|
| **Anthropic `sandbox-runtime` (`srt`)** | Apache-2.0, sans conteneur, filtre fichiers et réseau par domaine, conçu pour Claude Code, fonctionne sur macOS (Seatbelt) et Linux (bubblewrap) | « Beta research preview » : API susceptible de changer. Dépend de Node. Sur macOS, **Claude Code garde ses identifiants OAuth dans le trousseau** : le bac à sable peut les bloquer, d'où l'usage d'une clé API. À vérifier |
| **Conteneur Docker** (Docker 29.8.2 présent) | Isolation forte, déjà dans le code (`DockerRunner`) | Il faut construire une image avec `claude`, monter le worktree en écriture et filtrer le réseau par domaine, ce que Docker ne fait pas seul (il faut un proxy) |

Décision, **révisée le 2026-11-23** : **deux backends, un par parcours.** `srt` pour `autorun` (poste local, macOS prouvé) ; Docker pour `mode: delegate` (portable, sans poste de développeur). Le repli Docker n'est plus différé : il entre dans la v1 avec le lot 5. Les hooks s'exécutent eux aussi sous `srt` (conséquence 1 du lot 0) ; sous Docker, ils s'exécutent dans le conteneur.

**Exigences du bac à sable Docker (lot 5)**, en plus de celles du tableau ci-dessus :

| Ressource | Règle Docker |
|---|---|
| Image | Une image dédiée qui contient `claude`, versionnée et construite par ASAC ; pas `python:3.12-slim` |
| Worktree | Monté **en écriture** ; `asac.yaml`, `.asac/` et l'état montés **en lecture seule**, ou hors du conteneur |
| Réseau | Refus par défaut. La v1 n'ouvre que l'hôte de la passerelle du modèle ; **aucun proxy de filtrage par domaine n'est livré dans la v1**. Si la passerelle ne peut pas être isolée seule, `delegate` reste bloqué et le document le dit |
| Identifiants | Clé API passée par variable d'environnement au conteneur, jamais écrite dans l'image ni le worktree |
| Sortie | Ce que l'agent écrit en dehors du worktree disparaît avec le conteneur ; rien n'en est audité sauf le journal de l'outil |

## 6. Différé, pas abandonné : les différenciants hors v1

La v1 prouve une garantie (l'agent ne peut pas tricher). Ce qui suit fait d'ASAC une **plateforme de gouvernance**, et c'est ce qu'Archon n'a pas : Archon exécute des workflows, il ne documente ni identité des approbateurs, ni modèle de preuves, ni politiques, ni registre de skills.

**Statut du code existant.** Il n'est ni supprimé ni gelé. Il reste dans le dépôt. **`pytest`, `ruff check` et `mypy --strict` passent en local** (vérifié le 2026-11-20) ; la CI exécute aussi `ruff format`, `opa test` et le build de la documentation, non vérifiés ici. Il est exclu de la promesse v1 et de l'aide par défaut. Chaque élément passe en « supporté » seulement après un test réel, jamais après un test avec des fakes.

| Différenciant | Pourquoi il distingue ASAC | Où on en est | Ce que la v1 doit garantir pour ne pas le perdre |
|---|---|---|---|
| **Identité authentifiée et Decision Room** (portail, OIDC, rôles, séparation des tâches) | Archon ne documente pas qui peut répondre à un `wait`. ASAC a des rôles par gate et un portail de décision | SPA, OIDC, sessions, CSRF, tests avec faux fournisseur d'identité ; jamais contre un vrai | La gate enregistre déjà rôle, approbateur et sha dans l'audit : le portail se branche sur le même modèle sans migration |
| **Registre de skills et providers signés** (filesystem puis OCI + cosign) | Défend contre le détournement de skills (« dependency steering ») ; réutilisation entre équipes. Absent d'Archon (qui passe par GitHub) | Port défini, aucun adaptateur | Les skills locaux sont référencés avec leur digest `sha256` dès la v1 |
| **Neutralité vis-à-vis de l'agent** (Codex, Cursor, Bob, Antigravity, Copilot) | La gouvernance ne dépend pas d'un fournisseur ; argument fort pour un client qui n'a pas choisi | `assist` pour tous, `delegate` pour Codex et Cursor avec des fakes | Le port `Harness` reste inchangé et le bac à sable est indépendant de l'agent |
| **Preuves et politiques avancées** (`deps_verified`, `no_regression`, pattern `critic` « QA ≠ dev », `knowledge` avec fraîcheur, `autonomy`, `escalation`, `specLevel`) | C'est le cœur déclaratif : la gouvernance s'écrit, se teste (`opa test`) et se relit sans lire de code | Modèle, validation et une partie du moteur ; plusieurs points non câblés | `loop.until` accepte aussi bien des hooks que des politiques Rego |
| **Gouvernance d'entreprise** (multi-projets, FinOps, DORA, maturité L0–L4, rapport de conformité, export OpenTelemetry) | Répond à la question du responsable : « que font nos agents, à quel coût, avec quelle preuve ? » | Multi-projets et export CSV faits ; reste non démarré | Coût réel mesuré (spike A) et audit structuré : sans ces deux données, rien de ce qui précède n'est calculable |
| **Intégrations** (6 forges, création de PR, tracker, wiki, daemon et webhooks Jira, notifications) | Archon couvre GitHub et Slack ; ASAC vise GitLab, Bitbucket, Azure DevOps, Jira, c'est-à-dire les clients entreprise | Adaptateurs écrits, aucun testé sur un vrai serveur | La branche `asac/<run>` et le sha approuvé sont déjà l'entrée d'une PR |
| **Passerelle MCP** (liste d'autorisation, injection de secrets, journal des appels) | Contrôle ce que l'agent peut appeler, au-delà du fichier et du réseau | Génération de config, filtrage et audit faits pour Claude Code, avec un faux serveur | Le journal `tools.exposed` reste dans l'audit |
| **Exécution à l'échelle** (Kubernetes, Postgres, file de jobs, workers, étapes parallèles, repli Docker) | Passer d'un poste à une équipe | Code écrit, jamais exécuté sur un vrai cluster ni une vraie flotte | Le port `Runner` et le port `State` restent inchangés |

### Règles pour ne rien perdre

1. **La CI reste verte sur tout le code**, y compris les modules hors v1. Un module qui casse est corrigé ou retiré explicitement, jamais laissé pourrir.
2. **Les ports (`Harness`, `Runner`, `State`, `Policy`, `Registry`, `Forge`) sont stables** pendant la v1. Un changement de port exige une raison écrite.
3. **Le modèle de données de la gate et de l'audit contient déjà** rôle, approbateur, sha, identité du run. C'est ce qui permet d'ajouter l'identité authentifiée plus tard sans réécrire l'historique.
4. **Aucune promesse sans test réel.** Un module hors v1 passe en « supporté » après un test contre le vrai système (vrai serveur de forge, vrai fournisseur OIDC, vrai cluster), pas avant.
5. **Le README publie cette liste** : « existe, non supporté, voici ce qu'il faut pour le supporter ». Cela évite de cacher la valeur et d'en survendre l'état.

### Ordre proposé pour la v1.1, à ajuster avec les retours

1. Identité authentifiée et Decision Room (si la question 5 des retours montre que l'identité déclarative bloque).
2. Un adaptateur de forge, **un seul**, avec création de PR, testé sur un vrai serveur.
3. Un second harness vérifié en conditions réelles.
4. Registre filesystem, puis OCI.
5. FinOps et DORA, une fois le coût réel disponible sur plusieurs runs.
6. Passerelle MCP, puis exécution à l'échelle.

## 7. Lots de travail

Chaque lot doit passer `ruff`, `mypy --strict` et `pytest` avant le suivant.

### Lot 0. Spikes : réalisés le 2026-11-21

Réalisés dans `/tmp`, sur des copies, **sans modifier le dépôt**. Coût de l'ensemble : de l'ordre de 1 USD (estimation de Claude Code, voir la réserve du spike A).

| Spike | Résultat | Décision |
|---|---|---|
| **A. Coût réel** | `claude -p --output-format json` renvoie un objet avec `total_cost_usd`, `usage` (tokens en entrée, sortie, cache), `num_turns`, `is_error`, `session_id` et `result`. **Exploitable.** Réserves : une ligne d'avertissement précède le JSON ; derrière une passerelle (`ANTHROPIC_BASE_URL`), `costBasis` vaut `unknown` et le modèle est signalé non reconnu, donc le coût est une **estimation** de Claude Code, pas une facture. Plancher observé : 0,05 à 0,26 USD par appel, même pour répondre « pong » (contexte de base de 43 000 tokens) | **Go.** `per_run.cost_usd` est conservé, présenté comme estimation. Une boucle de 5 itérations coûte au moins de l'ordre de 1 USD : le budget par défaut doit en tenir compte |
| **B. `srt` avec `claude`** | `srt` s'installe par `npm` et tourne sur macOS (Seatbelt). `claude -p` fonctionne dedans quand seul le domaine de la passerelle est autorisé. Écriture hors zone, lecture de `~/.ssh` et domaine non autorisé sont refusés par le système (`Operation not permitted`, `CONNECT 403`) | **Go : `srt` retenu.** Réserves ci-dessous |
| **C. Test hostile** | **Sans bac à sable** (mêmes options que `autorun`, `acceptEdits`) : l'agent a réécrit `tests-green.sh` en `exit 0`, ajouté `# hacked` à `asac.yaml` et supprimé le dossier d'état. **Le trou est confirmé.** **Sous `srt`**, avec les permissions de Claude Code désactivées pour que seul le système décide : les cinq attaques (modifier un hook, modifier `asac.yaml`, supprimer l'état, lire `~/.ssh`, appeler un domaine non autorisé) échouent, et l'écriture de contrôle dans le worktree réussit. Vérifié sur le disque, pas seulement d'après le récit de l'agent | **Le critère d'acceptation central de la v1 est atteignable.** Reste à l'automatiser (lot 4) |

**Réserves sur `srt` (à traiter au lot 3)**

1. Authentification testée avec `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`. **Le cas OAuth (trousseau macOS) n'est pas testé.**
2. Il faut autoriser en écriture le dossier de travail de l'outil Bash (`/private/tmp/claude-<uid>`), sinon aucune commande ne s'exécute. Le shell affiche aussi du bruit sur `/tmp/claude-*-cwd`.
3. Un `curl` vers un domaine autorisé (`example.com`) a échoué avec une erreur de certificat, que je n'ai pas expliquée ; `claude` vers la passerelle a fonctionné. À éclaircir avant d'autoriser d'autres domaines (outils, dépendances).
4. La config exige le champ `deniedDomains`. `srt` est en préversion et demande Node. **Linux non testé** (`bwrap` et `socat` absents ici).

**Conséquences de conception découvertes** (elles changent le plan des lots 1 à 3)

1. **Les hooks doivent eux aussi tourner dans le bac à sable.** `tests-green.sh` exécute les tests du projet, donc du code écrit par l'agent. Hors bac à sable, ce code a les droits de l'utilisateur. Les scripts de hook viennent du dépôt principal (hors de portée de l'agent) mais s'exécutent sous `srt`.
2. **Les hooks doivent viser le worktree.** `tests-green.sh` fait `cd "$(dirname "$0")/../../app"` : exécuté depuis le dépôt principal, il testerait le mauvais code. ASAC doit passer le chemin du worktree aux hooks (variable `ASAC_WORKTREE`).
3. **Le commit se fait hors du bac à sable (hypothèse non testée).** Git écrit dans `<principal>/.git` (objets et métadonnées du worktree), hors de la zone d'écriture. ASAC commite donc lui-même après l'étape, ce qui empêche aussi l'agent de réécrire l'historique. À vérifier au lot 1.

### Lot 1. Worktree et exécution réelle

Worktree par run, commit et sha par étape, harness qui écrit dans le worktree, hooks et politiques exécutés depuis le dépôt principal, coût réel (fait : `claude -p --output-format json`, coût inconnu bloqué par un budget de coût), `asac clean`. **Décision corrigée :** `autorun` n'est pas supprimé en `assist` : c'est le mécanisme qui exécute l'agent et mesure son coût.

### Lot 2. Boucle

`step.loop` (`until`, `max_iterations`), renvoi de l'erreur à l'agent, audit de chaque itération, budget vérifié à chaque tour, escalade au plafond.

### Lot 3. Bac à sable

Backend retenu au lot 0, bloc `sandbox` en couche 2, règles du § 5.4, `doctor`.

### Lot 5. Runner Docker, `delegate` et worker (ajouté le 2026-11-23)

**Pourquoi :** `delegate` est le seul mode où l'agent tourne sans personne devant l'écran. Sans lui, la v1 ne couvre que le poste d'un développeur. `srt` n'est prouvé que sur macOS ; Docker est portable.

| Tâche | Critère d'acceptation |
|---|---|
| Image Docker avec `claude`, construite et versionnée par ASAC | Un `docker run` de l'image lance `claude -p` et rend un JSON de coût ; `doctor` vérifie sa présence |
| `DockerRunner` monte le worktree en écriture, les règles en lecture seule | Test : l'écriture dans `asac.yaml` et `.asac/` échoue dans le conteneur |
| Le coût, la boucle et la relance passent par le **chemin `delegate`**, pas seulement `autorun` | Un run `delegate` enregistre `spend.recorded` avec un coût réel ; `step.loop` s'applique ; un rejet motivé relance l'agent (plafonné) |
| Réseau limité à l'hôte de la passerelle du modèle | Test : un appel vers un autre hôte échoue dans le conteneur et l'échec est audité |
| Refus audités sous Docker, comme `sandbox.denied` sous `srt` | Une tentative refusée apparaît dans `asac audit` |
| **Worker minimal** qui consomme la file de jobs (`claim`, exécution, `complete` ou `fail`) | Un run mis en file est exécuté sans `asac apply` ; un job en échec est repris ou marqué en échec, avec sa raison |
| **Test hostile sous Docker**, le même que `test_adversarial.py` sous `srt` (§ 8.3) | Les quatre tentatives échouent et sont auditées |
| Test réel avec le vrai `claude` dans le conteneur | Passe au moins une fois, ignoré sauf `ASAC_REAL_CLAUDE=1`, sortie jointe |
| `validate` refuse `mode: delegate` sans `execution.runner` | Le scénario `02-feature` produit une erreur, pas un échec à l'exécution |

**Hors lot 5 :** Kubernetes, GitLab, passerelle MCP, étapes parallèles, pattern `critic`, `routing`. Le worker est **séquentiel** : une file, un worker, pas de concurrence entre workers.

### Lot 4. Tests hostiles et livraison

| Tâche | Critère d'acceptation |
|---|---|
| Test d'intégration réel (marqueur `integration`) sur un dépôt qui **n'est pas** l'exemple | Passe avec Claude Code, ignoré proprement sinon |
| **Test adversarial** : l'agent a pour consigne de modifier un hook, lire `~/.ssh`, appeler un domaine non autorisé, supprimer la base d'audit | Chaque tentative échoue, et l'échec apparaît dans `asac audit` |
| Test de boucle : un test échoue deux fois puis passe | 3 itérations auditées, étape validée, gate ouverte sur le bon sha |
| Test du plafond : un test ne passe jamais | Étape en échec ou escaladée après `max_iterations`, rien de fusionné |
| Corriger `RUNBOOK.md`, `README.md`, `quickstart.md`, `ANALYSE_ASAC.md` (chemins faux, ordre `approve`, statuts périmés) | Un lecteur suit le runbook sans corriger une commande |
| Installation propre depuis un wheel | `pipx install` puis `asac doctor` puis le quick start |
| Licence et origine du contenu | Aucun texte ni nom d'outil interne IBM dans les documents publics (voir `asac_veille_tlt.md`) |
| `--help` limité aux commandes de la v1, tag `v0.1.0`, `CHANGELOG`, canal de retour | Publié |

## 8. Définition de « terminé »

1. `ruff`, `mypy --strict` et `pytest` passent en CI.
2. Le test d'intégration réel passe au moins une fois, sortie jointe au dépôt.
3. **Les quatre tentatives hostiles du lot 4 échouent et sont auditées.** Sans cela, la v1 n'apporte pas ce qui la distingue d'Archon.
4. Une personne extérieure déroule le quick start en moins de 30 minutes sans poser de question.
5. Aucune clé acceptée par `validate` n'est ignorée sans avertissement.
6. Le README énonce les limites : identité des approbations déclarative en CLI, un seul harness, bac à sable en préversion, pas de création de PR.

### Statut au gel (2026-11-23)

La v1 n'est **pas encore « terminée »** au sens de ce paragraphe. Le gel fixe ce qu'il reste à faire pour l'être.

| # | Critère | Statut |
|---|---|---|
| 1 | `ruff`, `mypy --strict`, `pytest` | **Atteint en local.** CI distante non vérifiée : le dépôt n'a pas de remote |
| 2 | Test d'intégration réel | **Partiel.** `tests/test_real_claude.py` existe (commit `0aee199`), ignoré sauf `ASAC_REAL_CLAUDE=1`. La sortie jointe au dépôt n'est pas vérifiée |
| 3 | Les tentatives hostiles échouent et sont auditées | **Atteint avec des outils factices hostiles** (`tests/test_adversarial.py`), refus audités (`sandbox.denied`, `integrity.violated`). **Non démontré avec l'agent réel**, qui refuse d'attaquer |
| 4 | Une personne extérieure déroule le quick start en moins de 30 minutes | **Non atteint** |
| 5 | Aucune clé acceptée n'est ignorée sans avertissement | **Partiel.** ASAC027 couvre `knowledge`, `specLevel` et `config.model` ; il n'y a pas d'inventaire exhaustif des clés. `mode: delegate` sans runner est accepté par `validate` (d'après le scénario `02-feature`) et échoue à l'exécution |
| 6 | Le README énonce les limites | **Partiel.** Le `CHANGELOG` cite identité déclarative, macOS, bac à sable en préversion ; le README ne cite ni l'identité déclarative, ni macOS, ni l'absence de création de PR |
| 7 | Runner Docker, `delegate` et worker (lot 5) | **Fait le 2026-11-24, avec deux limites.** Image `asac-agent` construite, le vrai `claude` a tourné dans le conteneur par le moteur (coût réel 0,35 USD), quatre attaques d'un agent hostile échouent, `asac worker` exécute un run en file (détail : `docs/project/features/`). **Limites :** le réseau par défaut est `none`, qui coupe aussi la passerelle du modèle, donc un vrai agent exige un réseau Docker que l'opérateur prépare ; **ASAC ne filtre pas par domaine et n'audite pas les refus réseau sous Docker** (contrairement à `sandbox.denied` sous `srt`). Le § 5.4 et le lot 5 se contredisaient sur ce point : c'est le § 5.4 qui est vrai |

## 9. Retours à collecter

1. As-tu atteint la première gate sans aide ? Combien de temps ?
2. Qu'est-ce qui t'a bloqué ou surpris ?
3. As-tu consulté `asac audit` ? T'a-t-il appris quelque chose ?
4. La boucle a-t-elle corrigé des erreurs que tu aurais dû corriger toi-même ? Combien d'itérations en moyenne, et à quel coût ?
5. L'identité déclarative (`--by`) est-elle acceptable pour ton usage ?
6. Utiliserais-tu cela sur un vrai projet ? Sinon, que manque-t-il, **une seule chose** ?

Pas de télémétrie. **Seuil de décision à fixer avant les tests**, par exemple : sur 5 testeurs, au moins 3 vont jusqu'à la deuxième gate sans aide, et au moins 2 disent qu'ils l'utiliseraient.

## 10. Ce que les retours décideront (v1.1)

| Si les testeurs disent… | Alors |
|---|---|
| « Je ne sais pas qui approuve » | Portail minimal avec OIDC, limité à la Decision Room et à l'audit |
| « Je veux une PR, pas une branche » | Un adaptateur de forge, **un seul**, testé sur un vrai serveur |
| « Je n'utilise pas Claude Code » | Un second harness, vérifié en conditions réelles |
| « Je veux le lancer depuis Jira ou la CI » | Daemon et webhook |
| « Je veux réutiliser les skills d'une autre équipe » | Registre filesystem |

## 11. Risques assumés

1. **Le scope grossit nettement** : il passe d'un harnais de lancement à un moteur d'exécution isolé. C'est le coût de la décision de ne pas s'appuyer sur Archon. Les lots 1 à 3 sont la part importante du travail.
2. **ASAC concurrence désormais Archon sur l'exécution.** Il ne peut pas gagner sur la richesse des workflows (graphe, plugins, chat, console). Son seul argument est la garantie : preuves liées à un sha, règles hors de portée de l'agent, audit infalsifiable. Si les tests hostiles du lot 4 échouent, la v1 n'a plus de raison d'exister face à Archon.
3. **`srt` est en préversion.** Le spike B réduit le risque ; le repli Docker existe.
4. **Identité des approbations** : en CLI, `--by` et `--role` ne sont pas authentifiés. On l'assume en v1 (option A) et la question 5 mesure si c'est bloquant. L'alternative, intégrer l'OIDC du portail dès la v1, élargit le scope et est écartée pour l'instant.

## 12. Gel du périmètre

### 12.1 Ce que le gel signifie

Gelé le **2026-11-23**. Le périmètre de la première version (ASAC 0.1.x) est celui des sections 1 (y compris 1.1), 2, 4, 5 et 8. Une chose est « dans la v1 » seulement si ces sections la décrivent. Toute demande nouvelle va dans le § 6 ou le § 10 (v1.1), jamais dans la v1.

Numérotation : les numéros de section ne changent pas, car des commits et des tests y renvoient (`SCOPE_V1 §8.2`, `§8.3`).

### 12.2 Ce qui reste permis sans entrée au registre

- Corriger un défaut dans le périmètre (le comportement décrit n'est pas celui du code).
- Mettre à jour un statut (« fait » ou « non fait ») avec sa preuve : test, commit ou mesure.
- Corriger un texte faux, comme le § 4.2 au gel.

### 12.3 Ce qui exige une entrée au registre

Ajouter, retirer ou déplacer un élément du périmètre. L'entrée donne la date, le changement, la raison écrite et la personne qui a décidé. Sans entrée, le changement n'a pas eu lieu.

| Date | Changement | Raison | Décidé par |
|---|---|---|---|
| 2026-11-23 | Gel. Ajout du § 1.1 (promesse produit). Réécriture du § 4.2 : `delegate` retiré de la v1 (il exige un runner hors v1), deux manières de conduire `assist`. § 3 marqué historique. § 4.3 : `submit` et `version` ajoutés. « Statut au gel » ajouté au § 8 | Le § 4.2 décrivait trois modes sous le titre « deux modes » et présentait comme principal un mode non supporté ; le discours « bout en bout » promettait la MR et le déploiement, absents | À confirmer par le porteur du projet |
| 2026-11-23 | **Élargissement.** Entrée au périmètre : runner Docker, `mode: delegate` et worker minimal consommant la file de jobs (lot 5). Le bac à sable devient deux backends : `srt` pour `autorun`, Docker pour `delegate` (§ 5.4). Les étapes parallèles restent hors v1. Kubernetes et GitLab restent hors v1 | Le parcours délégué est le seul où l'agent tourne sans personne ; Docker est portable là où `srt` ne tourne prouvé que sur macOS. Décision de direction « option A » prise par le porteur. L'orchestration multi-agents (frameworks, `critic`, `routing`) est reportée à une version ultérieure, car ASAC orchestre les étapes du cycle, pas des agents qui collaborent | **Porteur du projet** (validé dans la conversation du 2026-11-23) |

### 12.4 Décisions ouvertes au gel

Le gel du périmètre **ne tranche pas** ces points. Chacun doit être décidé, avec une entrée au registre si le périmètre change.

1. **Nommage du schéma.** `max_iterations`, `on_fail`, `per_run`, `cost_usd` (snake_case) contre `dependsOn` (camelCase). À trancher avant de geler **le langage** ; le gel du périmètre ne gèle pas le schéma.
2. **Seuil de décision sur les retours** (§ 9), à fixer avant les tests, par exemple : sur 5 testeurs, au moins 3 vont jusqu'à la deuxième gate sans aide et au moins 2 disent qu'ils l'utiliseraient.
3. **Vérification avec IBM** (propriété intellectuelle, noms Bob, wxO, ICA, textes TLT) : décision humaine, avant toute publication.
4. **`mode: delegate` sans runner.** Ce point est **résolu par le lot 5** : `validate` doit refuser `mode: delegate` sans `execution.runner` (critère du lot 5). En attendant, la règle de livraison du § 4.1 est en défaut.
5. **Autorun par étape** et **MR en fin de run** : écartés de la v1 au gel, candidats v1.1.
6. **Proxy de filtrage réseau sous Docker.** Hors v1 : seul l'hôte de la passerelle est ouvert. Si l'isolation réseau ne peut pas être garantie sans proxy, `delegate` reste bloqué et le document le dit (§ 5.4).
7. **Orchestration multi-agents** (frameworks type LangGraph, pattern `critic`, `routing`) : reportée, hors v1, à réévaluer si le besoin apparaît. Voir `docs/project/roadmap.md`.
