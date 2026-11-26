# Portail entreprise ASAC : plan de contrôle, données et vérification

**Statut : proposition de conception, 2026-11-26.** Rien de ce document n'est implémenté. Il ne modifie ni `asac-specs-v1.md`, ni `SCOPE_V1.md`, dont le périmètre gelé reste en vigueur. Les décisions du § 16 demandent l'avis du porteur.

## 1. Problème

Une entreprise veut répondre à trois questions sur l'ensemble de ses projets : **quelles règles s'appliquent ? quelles preuves existent ? que coûte l'usage des agents ?**

Trois contraintes structurent la réponse.

1. **Le portail ne joint jamais un poste.** Les postes sont derrière NAT, pare-feu ou VPN, et ils s'éteignent. Toute communication part du CLI, en HTTPS sortant. Un laptop et un runner CI parlent la même API.
2. **Le poste du développeur contrôle sa machine.** Il peut modifier un hook, une base SQLite, un cache, ou le CLI lui-même. Tout ce qu'il affirme reste **déclaratif**.
3. **Une preuve opposable vient d'une machine que l'entreprise contrôle**, qui rejoue les contrôles sur un code précis avec des règles qu'il ne peut pas modifier.

Le document sépare donc deux plans. Le **plan de contrôle** distribue les règles, collecte les événements et porte les décisions. La **vérification** établit ce qui est vrai. Ils se complètent : le plan de contrôle montre, la vérification prouve.

## 2. Architecture

```text
                       PORTAIL ENTREPRISE (plan de contrôle)
  ┌────────────────────────────────────────────────────────────────────────┐
  │ OIDC / RBAC                                                           │
  │ P1  Gouvernance : bundles de règles signés (org → capacité → projet)   │
  │ P2  Ingestion : événements idempotents, métriques, FinOps, dérive      │
  │ P3  Decision Room : approbations par rôle, reçus signés                │
  │ Postgres (événements, décisions, bundles) · lecteur de forge (diffs)   │
  └──────▲─────────────────────────────▲───────────────────────────▲───────┘
         │ pull bundle (HTTPS,         │ push événements           │ poll/SSE
         │ ETag, signé)                │ (outbox, HTTPS)           │ décisions
  ┌──────┴────────────────┐   ┌────────┴──────────────┐   ┌────────┴──────────────┐
  │ Poste dev A           │   │ Poste dev B           │   │ Vérificateur CI       │
  │ asac CLI              │   │ asac CLI              │   │ asac verify           │
  │ SQLite (outbox)       │   │ SQLite (outbox)       │   │ conteneur isolé       │
  │ mode assist / autorun │   │ mode assist / autorun │   │ clé de signature (KMS)│
  └───────────────────────┘   └───────────────────────┘   └───────────────────────┘
                 │                          │                         ▲
                 └──────── git push ────────┴─────────────────────────┘
                              forge (branche protégée, statut asac/verified)
```

Le **vérificateur CI** est le seul composant qui signe. Les postes ne signent rien, et ils ne parlent pas à Postgres.

## 3. Principes

- **P1. Connexion sortante uniquement.** Le CLI initie toutes les communications. Le portail ne joint jamais un poste.
- **P2. Le local d'abord.** Le CLI écrit toujours dans son SQLite local, même hors ligne. La synchronisation vide une file (outbox) à la reconnexion.
- **P3. Le code ne sort pas de la forge.** Le portail lit les diffs et les fichiers **dans la forge**, à partir d'un sha. Le poste n'envoie que des métadonnées.
- **P4. Ce qui juge ne vient pas de ce qui est jugé.** Les règles viennent d'un bundle signé ou de la branche protégée, jamais de la branche du développeur.
- **P5. Une approbation vaut pour un sha.** Un nouveau sha n'a ni verdict ni approbation.
- **P6. Le verdict vient d'un processus observé de l'extérieur**, jamais d'un fichier écrit par le code jugé.
- **P7. Échec fermé.** Serveur absent, reçu absent ou invalide, bundle expiré : la fusion reste bloquée.
- **P8. Déclaré et vérifié ne se mélangent jamais.** Le portail affiche séparément les faits établis par le vérificateur et les affirmations du poste.

## 4. Frontières de confiance

| Élément | Qui le contrôle | Statut dans le portail |
|---|---|---|
| Code poussé (sha) | Personne : immuable | Vérifié |
| Diff et fichiers | La forge, lus par le portail | Vérifié |
| Règles appliquées (bundle et manifeste) | Le bundle signé, puis la branche protégée | Vérifié par le vérificateur |
| Exécution des contrôles (hooks, Rego) | Le vérificateur, dans un conteneur | Vérifié |
| Identité de l'approbateur | Le fournisseur OIDC | Vérifié |
| Identité du pousseur | La forge | Vérifié |
| Verrou de fusion | La protection de branche | Vérifié |
| Coût, tours, journal de l'agent | Le poste | Déclaré |
| Bac à sable actif, version du CLI, bundle appliqué sur le poste | Le poste | Déclaré |
| Événements locaux non vérifiés | Le poste | Déclaré |

## 5. Ce qui existe déjà

Chaque ligne a été relue dans le code de `sldc-agentic-orca/asac`.

| Brique | Où | Usage |
|---|---|---|
| Hooks lus depuis une racine, exécutés dans un autre dossier | `src/asac/hooks.py` : `run_hook` (paramètres `root`, `workdir`) | Rejeu du vérificateur |
| Environnement des hooks réduit à `PATH`, `LANG`, `LC_ALL`, `TMPDIR` | `src/asac/hooks.py` : `_PASS_ENV` | Aucun secret n'atteint un hook |
| Un commit par étape, message `asac: <étape> (run <id>)`, auteur `ASAC <asac@localhost>` | `src/asac/engine/workspace.py` : `commit_step` | Découpe le travail par étape |
| Sha approuvé par une gate | `GateRecord.subject` (`src/asac/ports/state.py`) | Lien décision ↔ code |
| Sha de base du run | événement `workspace.created` | Point de départ du rejeu |
| Audit et preuves en ajout seul | `state_sqlite.py` : triggers `*_no_update`, `*_no_delete` | Protège contre l'agent et l'accident |
| Protection Postgres | `state_postgres.py` : `asac_append_only`, sur `audit` et `evidence` seulement | La table `gates` reste modifiable (§ 9.3) |
| État central, un schéma par projet | `src/asac/adapters/__init__.py` : `open_state` (`ASAC_STATE_URL`) | Base du portail |
| Webhooks GitHub (HMAC) et GitLab (jeton) | `src/asac/daemon/app.py` | Déclencheurs |
| Port `Registry` (résolution, recherche, publication) | `src/asac/ports/registry.py` | Sans adaptateur aujourd'hui |
| Mode `delegate` et worker | lot C de la v1, `asac-specs-v1.md` § 6 | Vérification déléguée |

**Écarts constatés.**

1. **Identifiants non uniques entre postes.** `asac apply` nomme un run `run_<pipeline>_<n>` avec un compteur local (`src/asac/cli/__init__.py`, environ ligne 342). Deux postes produisent donc le même identifiant. L'audit s'appuie sur `seq`, un compteur local. Seul `asac worker` utilise un UUID (ligne 417).
2. **`asac evidence verify` ne rejoue rien.** Il contrôle que les preuves requises existent en base.
3. **Le port `Forge` n'a aucune opération de statut de commit.**
4. **La table `evidence` n'a pas de colonne sha.** Le lien passe par la gate.
5. **La politique Rego d'exemple lit des champs que le harness ne fournit pas.** `_policy_input` (`src/asac/engine/apply.py`) ne transmet que ce que rend l'adaptateur. Le harness Claude Code ne rend que `autorun`, `cost_usd`, `tokens` et `cost_unknown`. Les champs `findings_count`, `coverage`, `sast_high_count`, `human_approved` n'existent que dans les données de test.

## 6. Plan de contrôle

### 6.1 Identifiants et événements

Chaque événement envoyé au portail porte :

| Champ | Forme | Rôle |
|---|---|---|
| `event_id` | UUIDv7 | Idempotence : un doublon est ignoré |
| `project_id` | identifiant stable du projet (voir ci-dessous) | Regroupement |
| `run_id` | UUIDv7, généré au `apply` | Identité globale du run |
| `sequence` | entier par run, à partir de 1 | Ordre dans le run, détection des trous |
| `actor` | identité **authentifiée** de l'émetteur | Voir 6.6 |
| `source` | `workstation` ou `ci` | Niveau de confiance |
| `payload` | le fait, sans code | Contenu |
| `at` | horodatage émetteur | Information seulement |

**`project_id`.** L'identifiant ne vient pas du nom de dossier. Il est déclaré une fois dans `asac.yaml`, dans un champ `workspace` stable (`payments-service`), et il est **unique par organisation** : le portail refuse deux projets qui revendiquent le même identifiant, et rejette la synchronisation d'un poste qui ne correspond pas au projet enregistré. Un projet dont le dépôt change d'URL garde son identifiant.

**Les identifiants de run passent à UUIDv7.** C'est une modification du CLI : le format `run_<pipeline>_<n>` reste lisible en local, mais il n'est plus la clé globale. Un `display_id` court est conservé pour l'affichage.

### 6.2 Outbox locale

- Chaque événement est écrit dans la table d'audit locale **et** dans une file `outbox` (même transaction).
- La synchronisation envoie les lots dans l'ordre de `sequence`, en `POST` idempotent sur `event_id`.
- Une confirmation par lot marque la file comme vidée. Une coupure n'a aucun effet : au retour, les événements non confirmés sont renvoyés.
- L'outbox n'est jamais modifiée après écriture. Une fois confirmée, elle peut être purgée, mais seulement après l'export d'une trace (§ 9).

### 6.3 Décisions de gate

- Une gate ouverte crée une demande dans le portail, avec le sha, les contrôles déclarés et le coût.
- Le PO, le QA ou le responsable sécurité décide dans le navigateur, avec OIDC.
- Le CLI reçoit la décision de deux façons : **SSE ou poll sortant** pendant `asac apply --watch`, ou **au prochain `asac apply --resume`**, qui télécharge la décision signée.
- Un rejet porte son motif. La relance de l'agent utilise ce motif, comme aujourd'hui en autorun (F23).

### 6.4 Le diff reste dans la forge

Le portail affiche le diff **qu'il lit lui-même dans la forge**, à partir du sha de la gate. Le poste n'envoie jamais de diff. Il faut donc que la branche soit **poussée avant l'ouverture de la gate** ; un sha non poussé ne peut pas être approuvé. Cette contrainte est acceptable : une approbation sur un code que personne ne peut voir n'a pas de sens.

Les champs qui peuvent quand même être copiés depuis le poste (résumés, verdicts) sont des **métadonnées** : nombre de fichiers, chemins, verdicts par contrôle. Le contenu des logs bruts n'est jamais envoyé.

### 6.5 Confidentialité configurable

Trois niveaux, fixés par l'organisation dans le bundle :

| Niveau | Envoyé au portail | Usage |
|---|---|---|
| `metadata` | événements, sha, coûts, verdicts, noms de fichiers | Par défaut |
| `summary` | + sortie des contrôles tronquée et masquée | Équipes qui acceptent les extraits |
| `full` | + logs bruts | Rarement justifié ; à réserver aux environnements internes |

Le code source n'entre dans aucun niveau : il reste dans la forge (§ 6.4).

### 6.6 Authentification de l'émetteur

Deux sources, deux niveaux de confiance, affichés séparément :

- **Poste** : jeton obtenu par OIDC (flux « device »), propre à l'utilisateur, de courte durée. Les événements sont marqués `source: workstation`, donc **déclarés**.
- **CI** : identité de charge de travail de la plateforme de CI (jeton OIDC du job). Les événements sont marqués `source: ci`. Ils ne sont **vérifiés** que si le job est celui du vérificateur protégé (§ 7).

Un événement venu d'un poste n'a jamais le même statut qu'un événement venu de la CI, dans aucun tableau de bord.

### 6.7 Résilience

- Hors ligne : le CLI travaille, la file grossit, rien n'est perdu.
- Portail indisponible : même effet, avec un message affiché à l'utilisateur.
- Reçu expiré ou révoqué : la fusion reste bloquée ; le poste peut continuer à travailler.

## 7. Vérification

### 7.1 Le vérificateur

`asac verify` est lancé par la CI de la forge, sur une définition de tâche **venant du côté protégé** (§ 7.4).

**Entrées** : le dépôt, la pointe de la branche protégée, la branche ou le sha à vérifier, et la trace déclarée si elle est présente.

**Algorithme.**

1. Récupérer la branche et résoudre les sha. Refuser si le sha de base du run n'est pas un ancêtre de la branche.
2. Extraire la pointe de la branche protégée dans `rules/`, en lecture seule. Charger et valider le manifeste depuis ce dossier, puis appliquer le **bundle** (§ 8.4). Un manifeste ou un bundle invalide arrête la vérification.
3. Calculer la liste des étapes **d'après le manifeste**, et non d'après la trace. Chercher pour chaque étape le commit `asac: <étape> (run <id>)`. Une étape sans commit fait échouer la vérification.
4. Pour chaque étape, dans l'ordre de `dependsOn` :
   1. extraire le commit parent (étape précédente ou base) dans un conteneur ;
   2. exécuter les hooks `pre_tool` ;
   3. dans **le même dossier**, extraire le commit de l'étape ;
   4. exécuter les hooks `post_step` ;
   5. évaluer les politiques dont l'entrée se calcule côté serveur (§ 15) ;
   6. vérifier que le diff ne touche ni `asac.yaml`, ni `asac.vars.yaml`, ni `.asac/`.
5. Comparer les verdicts aux résultats déclarés dans la trace. Un écart est enregistré (`verify.mismatch`).
6. Signer le reçu, écrire les événements, poser le statut.

**Le même dossier entre `pre_tool` et `post_step`.** `step-scope.sh` de l'exemple `real-tools` écrit une empreinte dans `.asac-state/` en `pre_tool`, puis la compare en `post_step`. Le rejeu doit donc garder un seul dossier pour les deux phases.

**Codes de sortie** : 0 tout est vérifié, 3 un contrôle a échoué, 1 erreur interne.

### 7.2 Isolation du code jugé

Les hooks lancent les tests du projet, donc du code écrit par le développeur. Ce code est **non fiable** et s'exécute sur une machine de l'entreprise.

- Il tourne dans un **conteneur**, jamais comme processus fils du vérificateur. Sous Linux, un processus fils du même utilisateur peut lire l'environnement de son parent, où se trouve la clé de signature.
- Aucun secret ne doit y entrer. Réseau coupé, sauf besoin déclaré. Conteneur éphémère, avec limites de temps et de mémoire.
- `rules/` est monté en lecture seule. Le dossier du sha est monté en écriture, car les tests écrivent des fichiers.
- Le verdict est le **code de sortie observé de l'extérieur**. Aucun fichier écrit par le code du dépôt n'entre dans le verdict.
- Le runner Docker de la v1 est un point de départ. Ses montages sont à vérifier avant réutilisation.

### 7.3 Ce que vérifie le reçu

Le reçu (§ 8) prouve la chaîne suivante, pour un sha donné :

1. les contrôles ont été rejoués par le vérificateur, avec les règles de la branche protégée et le bundle indiqué ;
2. les résultats sont ceux-là ;
3. une personne habilitée, identifiée par OIDC, a approuvé ce sha pour ce rôle ;
4. cette personne n'est pas la personne qui a poussé le sha.

### 7.4 Définition de la tâche de vérification

La tâche qui lance `asac verify` ne doit pas être lue dans la branche du développeur, sinon celui-ci peut la modifier pour la sauter. Elle vient :

- **GitHub** : d'un workflow réutilisable dans un dépôt protégé, imposé par une règle d'organisation ;
- **GitLab** : d'une politique d'exécution de pipelines, ou d'un pipeline de conformité.

Ces deux mécanismes viennent de ma connaissance des forges, **non vérifiée dans cette session**. À confirmer avant d'engager le palier (§ 16, question 6).

## 8. Gouvernance distribuée : bundles

### 8.1 Le bundle

Un **bundle de gouvernance** est un fichier signé, publié par l'organisation, qui contient les règles communes à tous les projets. Il ne décrit ni les étapes ni les skills d'un projet.

Il contient uniquement :
- des **politiques Rego** obligatoires ;
- des **hooks** obligatoires ;
- des **plafonds** de budget ;
- des **exigences par capacité** : pour une capacité donnée, un hook, un mode et une gate minimale ;
- une liste de **domaines réseau interdits** ;
- une **version**, un horodatage d'expiration, la référence de la clé de signature.

### 8.2 Le problème du nommage

Une règle comme « la gate de l'étape `release` doit avoir un rôle `security` » ne peut pas être imposée : l'entreprise ne connaît pas le nom de l'étape dans chaque projet. Les exigences visent donc les **capacités** et les **types de preuves**, qui sont des noms partagés (ou que l'organisation normalise) :

- « toute étape de capacité `release` a une gate `human` de rôle `security` et tourne en `mode: delegate` » ;
- « toute étape qui produit la preuve `tests_green` exécute le hook `deps-verify` » ;
- « `budgets.per_run.cost_usd` ≤ 20 ».

Le projet ne peut pas réaliser ces exigences en changeant le nom d'une étape, car l'exigence se lit sur la capacité. Un projet qui n'utilise pas la capacité `release` n'est pas concerné ; cette limite doit être écrite dans le bundle.

### 8.3 Fusion stricte

Le moteur travaille sur `effective = merge_strict(bundle, manifeste_du_projet)`.

| Primitive | Règle de fusion |
|---|---|
| Hooks obligatoires | Union. Un projet ne peut pas retirer un hook du bundle |
| Politiques Rego obligatoires | Union. Un projet ne peut pas les désactiver |
| Gates | Le bundle fixe un plancher (type, rôle) par capacité ; le projet peut le renforcer, pas l'affaiblir |
| Mode | Le bundle peut imposer `delegate` sur une capacité |
| Budgets | Minimum des deux |
| Domaines réseau autorisés | Intersection ; les domaines interdits gagnent toujours |
| Skills | Le projet ajoute les siens. Le bundle peut en imposer, par digest |

Une incohérence (le projet exige moins que le bundle) **arrête la validation**, avec une erreur qui nomme l'exigence violée. Elle ne produit pas d'avertissement.

### 8.4 Distribution et vérification

- **Publication** : l'organisation signe le bundle (clé publique connue des postes et du vérificateur).
- **Sur le poste** : le CLI le télécharge en HTTPS sortant, avec `ETag`, le vérifie et le garde en cache **hors du worktree**. Le cache est couvert par le contrôle d'intégrité (F29), et doit l'être étendu à ce cache.
- **Hors ligne** : le bundle reste utilisable jusqu'à son expiration. Au-delà, l'organisation choisit `fail-closed` (le CLI refuse les runs) ou `warn` (il les marque comme hors conformité).
- **Sur le vérificateur** : le bundle appliqué est celui que le vérificateur télécharge lui-même. Son sha est écrit dans le reçu.

**Limite importante** : le bundle appliqué sur le poste peut être contourné par le développeur (cache édité, CLI modifié). Le poste ne sert donc qu'à **donner un retour rapide**. La conformité réelle se décide sur le vérificateur. Le poste déclare `bundle_sha256` ; le vérificateur le recalcule. Un écart est signalé comme dérive.

### 8.5 Skills et registre

Le manifeste d'exemple référence des skills par `registry.asac.dev/<équipe>/<nom>@<version>`. Le port `Registry` existe, sans adaptateur. Un skill référencé est résolu, puis vérifié par son **digest sha256**. Le contenu d'un skill n'est jamais accepté sans ce digest. La publication et la signature des skills relèvent d'un palier ultérieur.

## 9. Traces, chaînage et ancrage

### 9.1 Ce que SQLite garantit

Les triggers interdisent `UPDATE` et `DELETE` sur `audit` et `evidence`. Cela protège contre l'agent et contre l'accident. Le propriétaire du fichier peut supprimer les triggers, éditer la base ou la recréer. Aucun stockage local ne résout ce point.

### 9.2 Le modèle git, et sa limite

Un historique chaîné par hash détecte la modification d'une entrée ancienne. Mais le propriétaire d'un historique local peut le réécrire et **recalculer toute la chaîne**. Git fonctionne entre plusieurs personnes parce qu'un **remote protégé refuse la réécriture**, et le hash ne sert pas de confiance en soi. Le chaînage ne vaut donc que si **la tête de chaîne est ancrée là où le développeur n'écrit pas**.

### 9.3 Trois couches

| Couche | Où | Contenu | Garantie |
|---|---|---|---|
| Travail | Poste, SQLite | audit + `prev_hash` + `entry_hash` | Rapide, hors ligne. Détecte une altération accidentelle |
| Transport | Ref `asac/trace/<run>` poussée par le développeur | export chaîné | Le serveur voit ce que le poste affirme, et compare |
| Preuve | Serveur : Postgres (ajout seul) + reçu signé | verdicts, règles utilisées, décisions OIDC | Opposable |

**Chaînage.** `entry_hash = sha256(prev_hash ‖ forme canonique de (at, run_id, step_id, actor, action, detail))`. La première entrée d'un run a un `prev_hash` nul. La trace exportée contient toutes les entrées et le hash de tête.

**Ancrage.** Le serveur recopie la tête de chaîne reçue dans le reçu signé. Toute réécriture ultérieure de l'historique local ne correspond plus au hash signé.

**Ce qui n'est pas protégé.** Une réécriture faite **avant** le premier envoi est possible. Elle n'affecte pas le verdict, qui repose sur le code.

**Le contenu transmis** peut contenir du code ou des secrets : la sortie de l'agent est tronquée à 8 000 caractères dans l'audit, mais les chemins de fichiers restent. Le niveau de confidentialité (§ 6.5) s'applique.

## 10. Reçus et gates

### 10.1 Le reçu

Le reçu est signé par le vérificateur. Il prouve l'approbation **et** les contrôles pour un sha :

```json
{
  "project_id": "payments-service",
  "run_id": "0196f3a2-…",
  "step": "release",
  "commit_sha": "…",
  "checks": { "verified_by": "asac-verifier@ci", "rules_sha": "…", "bundle_sha256": "…",
              "controls": [{ "hook": "deps-verify", "exit": 0 }] },
  "decision": { "gate": "gate_release", "role": "security", "approver": "…", "decided_at": "…" },
  "trace_head": "…",
  "signature": { "alg": "…", "keyid": "…", "sig": "…" }
}
```

**Format.** Le reçu devrait suivre l'énoncé **in-toto v1** (`_type`, `subject`, `predicateType`, `predicate`), dont j'ai vérifié les champs sur la page de spécification. Deux points restent à confirmer : la clé du digest d'un commit git (la page cite `sha1` dans son exemple, sans lister les noms reconnus) et l'enveloppe de signature (DSSE, d'après ma connaissance, non vérifiée).

### 10.2 Vérification à la fusion

La protection de branche exige le statut `asac/verified` sur le sha, et ce statut n'est posé que si le reçu est valide. La vérification se fait **dans la CI**, avec la clé publique de l'organisation.

### 10.3 Gates centrales

- Une décision est enregistrée **dans l'audit central**, avec l'identité OIDC, le rôle et le sha. La ligne de la table `gates` ne fait pas foi : en Postgres, seules `audit` et `evidence` sont protégées, et `decide_gate` modifie la ligne. La source de vérité est l'événement d'audit, repris dans le reçu.
- **Séparation des tâches.** Les commits d'étape sont signés `ASAC <asac@localhost>`, ils n'identifient donc pas le développeur. On compare l'approbateur à la **personne qui a poussé le sha**, identifiée par la forge. Un approbateur identique au pousseur est refusé.
- **Correspondance d'identité.** Une table administrée relie l'identité OIDC à l'identité de la forge, ou une règle sur l'adresse e-mail (§ 16, question 5).

## 11. Situations

### 11.1 Parcours

| # | Situation | Comportement |
|---|---|---|
| S1 | Conduite manuelle (`assist`) | Push, vérification, gate centrale, fusion |
| S2 | Conduite automatique (`autorun`) | Idem. La trace porte en plus le coût et le journal de l'agent, déclarés |
| S3 | Parcours délégué (`mode: delegate`) | L'agent tourne sur le runner géré par l'entreprise. La vérification est intégrée au run |
| S4 | Code écrit sans ASAC, poussé tel quel | Le vérificateur crée un run de vérification seule. Les contrôles et les gates s'appliquent |
| S5 | Rejet à la gate | Le développeur reprend le travail (nouvel appel à l'agent, voulu) et pousse un nouveau sha. L'ancienne vérification ne vaut plus |
| S6 | Bundle mis à jour pendant un run | Le run garde le bundle de son `run.created`. Le vérificateur applique le bundle courant : s'il diffère, la vérification échoue et le développeur rebase |
| S7 | Poste hors ligne | Le travail continue. La file grossit, et la synchronisation reprend au retour |
| S8 | Portail ou vérificateur indisponible | Le statut reste en attente, la fusion est bloquée |
| S9 | Test instable | Le résultat du vérificateur fait foi, avec une relance plafonnée. L'instabilité est visible |
| S10 | Plusieurs développeurs sur une branche | Le raisonnement se fait par sha, chaque push est vérifié |
| S11 | Contrôle coûteux (appelle un modèle) | Marqué « vérificateur seulement » ou « déclaré » pour ne pas être payé deux fois (§ 16, question 3) |
| S12 | Contrôle qui exige des secrets ou des services | Exécuté sur le vérificateur uniquement |
| S13 | Push sans trace | Le verdict porte sur le code. L'absence de trace est affichée |
| S14 | Trace dont la chaîne est cassée | Le verdict repose sur le code, avec `verify.trace_invalid` |
| S15 | Force-push après vérification | Nouveau sha, nouvelle vérification ; l'ancien statut est sans effet |
| S16 | La branche modifie les règles | Les contrôles sont rejoués avec les règles de la branche protégée. La fusion exige l'approbation des propriétaires de code |
| S17 | Deux projets revendiquent le même `project_id` | Le portail refuse le second enregistrement |

### 11.2 Tentatives de falsification

| # | Tentative | Défense | Risque résiduel |
|---|---|---|---|
| T1 | Modifier un hook pour qu'il réussisse | Le vérificateur lit les hooks sur la branche protégée (P4) | Aucun pour le hook lui-même |
| T2 | Modifier `asac.yaml` ou retirer une gate | Idem. Changement de règles = MR protégée, propriétaires de code | Collusion de deux personnes |
| T3 | Éditer le SQLite local ou la file | Le portail ignore les événements non vérifiés ; ils sont affichés comme déclarés | Aucun |
| T4 | Mentir sur `--by` | Les approbations comptent dans le portail (OIDC) | Aucun |
| T5 | Pousser un autre commit que celui approuvé | Verdict et approbation liés au sha (P5) | Aucun |
| T6 | Fusionner sans passer par ASAC | Statut requis, posé seulement par une source vérifiée | Administrateur de la forge |
| T7 | Rejouer une ancienne approbation | Même défense que T5 | Aucun |
| T8 | Poster un faux statut `asac/verified` | Statut exigé d'une source précise (§ 7.4) | Forge qui ne lie pas le statut à une source |
| T9 | Modifier la définition de la tâche de vérification | Elle vient du côté protégé | Forge sans mécanisme équivalent |
| T10 | Voler la clé de signature depuis le code jugé | Le code tourne dans un conteneur sans secret (§ 7.2) | Évasion de conteneur |
| T11 | Faire écrire un faux verdict par le code jugé | Le verdict est un code de sortie observé de l'extérieur (P6) | Aucun |
| T12 | Réécrire la trace locale et recalculer la chaîne | La tête signée ne correspond plus (§ 9.3) | Réécriture avant le premier envoi |
| T13 | Écrire dans la base centrale | Les postes n'ont aucun identifiant de base ; le portail écrit avec un rôle d'insertion seule | Administrateur de la base |
| T14 | Approuver son propre travail | Pousseur (forge) comparé à l'approbateur (OIDC) | Correspondance d'identité mal tenue |
| T15 | Déclarer un faux coût | Affiché comme déclaré ; recoupable avec les journaux de la passerelle | Coût non recoupé |
| T16 | Désactiver le bac à sable localement | Sans effet sur la preuve, qui vient du vérificateur | Aucun |
| T17 | Se faire passer pour la CI en envoyant des événements avec `source: ci` | Le jeton de charge de travail est vérifié par le portail ; un jeton de poste ne peut pas porter `source: ci` | Compromission de la plateforme de CI |
| T18 | Modifier le cache du bundle sur le poste | Le poste ne sert qu'au retour rapide ; le vérificateur applique son propre bundle et écrit son sha dans le reçu | Aucun pour la conformité ; le poste reste contournable |
| T19 | Faire passer un projet pour un autre (même `project_id`) | Unicité par organisation, refus du second enregistrement (S17) | Enregistrement initial fait par un administrateur |

### 11.3 Limites résiduelles

1. **Affaiblir les tests.** Supprimer un test ou assouplir une assertion fait passer les contrôles. ASAC rend le geste visible et coûteux : non-régression sur le nombre de tests et la couverture par rapport à la branche protégée, chemins protégés (modifier `tests/` demande un rôle QA), mise en évidence dans la Decision Room. Le dernier rempart reste l'approbateur.
2. **Un verdict vaut ce que valent les tests du projet.**
3. **Un administrateur de la forge ou de la base** peut contourner le système. Le webhook de fusion détecte une fusion sans statut et l'écrit dans l'audit, sans l'empêcher.
4. **Le coût et le journal de l'agent** restent déclarés tant qu'ils ne sont pas recoupés avec la passerelle du modèle.
5. **Le poste reste contournable.** Ce qui est vrai pour la conformité, c'est le vérificateur.

## 12. Ce que cela change pour la v1

Rien dans le périmètre gelé. La v1 reste un outil local, avec des preuves déclaratives, ce que `asac-specs-v1.md` § 15 énonce déjà. Le plan de contrôle et la vérification sont des paliers ultérieurs.

Deux changements de la v1 sont toutefois nécessaires avant tout palier, et ils n'ajoutent aucune fonctionnalité visible :
- les identifiants de run passent à UUIDv7, avec un `display_id` pour l'affichage ;
- le cache du bundle, s'il existe, entre dans le contrôle d'intégrité.

## 13. Plan de réalisation

Chaque palier apporte une valeur à lui seul. L'ordre est celui retenu après la discussion du 2026-11-26 : **gouvernance descendante, puis visibilité, puis Decision Room**. Mais le plan de contrôle seul ne prouve rien : le vérificateur (P1 de la vérification) doit exister avant que les décisions aient un sens.

| Palier | Contenu | Critère d'acceptation | Valeur |
|---|---|---|---|
| **V1** | `asac verify` : rejeu des contrôles sur un sha, règles lues sur la branche protégée, verdict par étape, codes 0, 1 et 3. Réutilise `run_hooks` (`root`, `workdir`) | Une branche hostile (hook modifié, `asac.yaml` modifié, étape sans commit) échoue. Une branche saine réussit. Le hook à état `step-scope` donne le même verdict qu'en local | Preuve vérifiée, sans serveur dédié |
| **P1** (réduit) | Bundle : politiques Rego obligatoires, hooks obligatoires, plafonds de budget, exigences par capacité. Signature, cache, fusion stricte, erreur de validation en cas de conflit | Un projet qui affaiblit une exigence est refusé à la validation. Le vérificateur applique le bundle et écrit son sha dans le reçu | Référentiel commun, appliqué au bon endroit |
| **V2** | Tâche de vérification GitHub et GitLab, définie côté protégé, conteneur isolé | Une branche qui modifie sa propre tâche ne contourne pas la vérification | Merge conditionné |
| **V3** | Statut de commit dans le port `Forge` ; protection de branche liée à une source | Un faux statut posté par un autre utilisateur ne débloque pas la fusion | Verrou de fusion |
| **P2** | Outbox, identifiants UUIDv7, `project_id` unique, événements idempotents, authentification de l'émetteur, lecture des diffs dans la forge | Un portable hors ligne qui se reconnecte ne perd ni ne duplique d'événement. Un doublon est ignoré | Visibilité et FinOps fiables |
| **V4** | Chaînage de l'audit, export de trace, ref `asac/trace/<run>`, détection `verify.mismatch` | Une trace réécrite est détectée à partir du hash de tête ancré | Détection de falsification |
| **P3** | Decision Room OIDC, décisions par SSE ou poll, reçus signés vérifiés à la fusion | Un approbateur identique au pousseur est refusé. Un reçu falsifié ne débloque pas la fusion | Gouvernance et conformité |
| **V5** | Attestations signées, rôle d'insertion seule en Postgres | Une attestation vérifie avec la clé publique de l'organisation | Opposabilité |

Ce document remplace la version précédente de la vérification centrale ; les paliers V y sont détaillés aux §§ 7 à 10.

## 14. Hors de ce document

- Publication et signature des skills (registre) : palier ultérieur. Le port existe, sans adaptateur.
- Forges autres que GitHub et GitLab.
- Journal de transparence public pour l'ancrage externe.

## 15. Décisions de conception

Les réponses ci-dessous sont proposées. Elles ne sont pas tranchées.

1. **Politiques Rego : d'où vient leur entrée.** `_policy_input` (`src/asac/engine/apply.py`) ne transmet que ce que rend l'adaptateur. Claude Code ne rend que `autorun`, `cost_usd`, `tokens` et `cost_unknown`. Les champs que lit la politique d'exemple ne sont produits nulle part. Une politique de gate ne reçoit donc rien d'utile aujourd'hui. Choix : définir une **entrée serveur** pour les politiques (couverture mesurée par un hook, résultats d'un analyseur), ou limiter le rejeu aux hooks. Recommandation : limiter aux hooks en V1, puis définir l'entrée serveur en V2.
2. **Règles à la pointe de la branche protégée, ou à la base du run.** Recommandation : à la pointe, avec échec et rebase (S6). Une règle changée est une règle que le développeur doit connaître.
3. **Contrôles coûteux.** Clé de manifeste `replay: server` ou `replay: declared`. Elle étend la couche 2 : c'est une extension documentée, comme `step.loop` l'a été. Recommandation : oui.
4. **Signature : clé gérée ou sans clé.** Une clé dans un KMS de l'entreprise, ou une signature liée à l'identité OIDC du job. Dépend de l'infrastructure.
5. **Correspondance d'identité** entre OIDC et forge : table administrée, ou règle sur l'adresse e-mail.
6. **Forges prioritaires.** GitHub et GitLab sont proposées. Pour chacune, trois capacités à vérifier : définition de tâche imposée côté protégé, statut exigé d'une source précise, restriction d'écriture par motif de référence.
7. **Rétention et ancrage externe** de la tête de chaîne.
8. **Niveau de confidentialité par défaut** (§ 6.5) et durée de conservation des traces.
9. **Identifiant de projet.** Champ `workspace` de `asac.yaml`, unique par organisation : confirmer qu'on le garde comme identifiant, et qui l'administre.
10. **Mode hors ligne du bundle.** `fail-closed` ou `warn` par défaut, et durée de validité du cache.

## 16. Extensions de code, par palier

| Besoin | Fichier | Palier |
|---|---|---|
| Commande de vérification | `src/asac/cli/__init__.py`, nouveau `src/asac/engine/verify.py` | V1 |
| Lecture des hooks sur une racine distincte | `src/asac/hooks.py` (déjà présent) | V1 |
| Bundle : format, signature, cache, fusion | nouveau `src/asac/governance/bundle.py` | P1 |
| Contrôle d'intégrité étendu au cache du bundle | `src/asac/engine/integrity.py` | P1 |
| Opération de statut de commit | `src/asac/ports/forge.py` et adaptateurs | V3 |
| Tâche de vérification | fichiers de modèles pour GitHub et GitLab, nouveau `docs/guides/verification-ci.md` | V2 |
| Identifiants UUIDv7 et `display_id` | `src/asac/cli/__init__.py`, `src/asac/engine/apply.py` | P2 |
| Outbox | `src/asac/adapters/state_sqlite.py`, nouveau `src/asac/sync/` | P2 |
| Lecture des diffs dans la forge | `src/asac/ports/forge.py` (lecture seule) | P2 |
| Chaînage de l'audit | `state_sqlite.py`, `state_postgres.py` | V4 |
| Reçus et attestations | nouveau `src/asac/attest/` | V5 |
| Portail : décisions, séparation des tâches | `src/asac/portal/api.py`, `decision.py` | P3 |
| Nouveaux événements | `asac-specs-v1.md` § 14, à la prochaine version | V1 et suivants |

Les événements proposés : `verify.started`, `verify.step`, `verify.mismatch`, `verify.trace_invalid`, `bundle.applied`, `attestation.written`.
