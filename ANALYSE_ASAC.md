# Analyse du projet ASAC & Architecture cible du Portail Entreprise

> **Date d'analyse** : 19 novembre 2026  
> **Périmètre analysé** : implémentation de référence ASAC (spec v0.4) dans `src/asac/`, `tests/`, `examples/`, `docs/` et `schemas/`.

---

## Table des matières

1. [Audit technique du développement actuel](#1-audit-technique-du-développement-actuel)
   - [1.1 Vue d'ensemble et qualité statique](#11-vue-densemble-et-qualité-statique)
   - [1.2 Architecture et composants réalisés](#12-architecture-et-composants-réalisés)
   - [1.3 Points forts notables](#13-points-forts-notables)
   - [1.4 Décalage documentation ↔ implémentation](#14-décalage-documentation--implémentation)
   - [1.5 Bugs, incohérences et limites techniques](#15-bugs-incohérences-et-limites-techniques)
2. [Analyse du portail actuel et propositions Entreprise](#2-analyse-du-portail-actuel-et-propositions-entreprise)
   - [2.1 État actuel et limites à l'échelle entreprise](#21-état-actuel-et-limites-à-léchelle-entreprise)
   - [2.2 Nouvelles fonctionnalités par persona (BA, PO, Dev, Managers)](#22-nouvelles-fonctionnalités-par-persona-ba-po-dev-managers)
   - [2.3 Socle technique transverse entreprise](#23-socle-technique-transverse-entreprise)
3. [Décision SPA vs SSR et architecture cible du portail](#3-décision-spa-vs-ssr-et-architecture-cible-du-portail)
   - [3.1 Pourquoi basculer vers une SPA en mode BFF](#31-pourquoi-basculer-vers-une-spa-en-mode-bff)
   - [3.2 Comparatif des options architecturales](#32-comparatif-des-options-architecturales)
   - [3.3 Architecture cible : SPA + FastAPI BFF](#33-architecture-cible--spa--fastapi-bff)
   - [3.4 Modèle de sécurité BFF et RBAC scopé](#34-modèle-de-sécurité-bff-et-rbac-scopé)
   - [3.5 Contrat API `/api/v1/`](#35-contrat-api-apiv1)
   - [3.6 Arborescence cible et stack Frontend](#36-arborescence-cible-et-stack-frontend)
   - [3.7 Plan de migration incrémental](#37-plan-de-migration-incrémental)

---

## 1. Audit technique du développement actuel

### 1.1 Vue d'ensemble et qualité statique

**ASAC (Agentic SDLC as Code)** est l’implémentation de référence en Python 3.12+ de la spécification v0.4 (gelée) visant à déclarer et exécuter un cycle de vie logiciel piloté par agents IA sous gouvernance explicite (3 couches : `asac.yaml`, `asac.vars.yaml`, `.asac/policies/*.rego`).

- **Volumétrie** :
  - ~3 700 lignes applicatives dans `src/asac/` (39 fichiers Python, 4 templates Jinja2, 1 feuille CSS).
  - ~1 500 lignes de tests dans `tests/` (16 fichiers + 20 golden files + suites de conformité).
  - 1 projet exemple complet 3 couches (`examples/payments-service/`), 1 JSON Schema exporté (`schemas/asac-manifest-0.4.schema.json`) et une documentation complète (`docs/`).
- **Contrôles qualité exécutés (sans modification)** :
  - `ruff check src tests` : **0 erreur**.
  - `mypy --strict src` (plugin `pydantic.mypy`) : **0 erreur** sur 39 fichiers.
  - `pytest` (offline via `--disable-socket --allow-unix-socket`) : **134 passés, 5 ignorés (`skipped`), 4 en échec** (liés à l'absence du binaire `opa` dans le `PATH` et à l'exception `OpaUnavailable` non interceptée — voir section 1.5).

### 1.2 Architecture et composants réalisés

Le projet repose sur une **architecture hexagonale (Ports & Adapters)** propre et modulaire :

| Couche / Module | Fichiers clés | Rôle et état d'avancement |
|---|---|---|
| **Modèle & Chargement** | `src/asac/model/manifest.py`, `src/asac/model/vars.py`, `src/asac/loader/load.py`, `src/asac/schema.py` | Modèles Pydantic v2 stricts (`extra="forbid"`), rejet explicite des clés v0.5 (`ASAC000`), export JSON Schema. |
| **Validation statique** | `src/asac/validate/checks.py` | 20 règles (`ASAC001`–`ASAC020`) : références agents/skills/capabilities/providers, cycles DAG, disponibilité amont des `requiresEvidence`, compatibilité `delegate`/headless, confinement des chemins locaux, digests `#sha256:` sur les hooks distants. |
| **Moteur & Gouvernance** | `src/asac/engine/plan.py`, `src/asac/engine/apply.py`, `src/asac/engine/governance.py`, `src/asac/engine/runtime.py` | Planification topologique par vagues (`waves`), exécution stateless/reprise (`--resume`, `--reopen`), gestion des gates (rôles, expiration, rejet motivé), budgets (tokens/coût/itérations), autonomie, escalade, kill-switch, politiques OPA + `no_regression`. |
| **Hooks locaux** | `src/asac/hooks.py` | Exécution de scripts `run:` déclarés dans le manifeste, chemin confiné au dépôt, environnement nettoyé (`PATH`, `LANG`, `LC_ALL`, `TMPDIR`), timeout 60s. |
| **Ports** | `src/asac/ports/{harness,policy,registry,runner,state}.py` | 5 `Protocol` découplés avec suites de conformité dans `tests/conformance/`. |
| **Adaptateurs** | `src/asac/adapters/state_sqlite.py`, `claude_code.py`, `fake_harness.py`, `stub_harness.py`, `opa_policy.py`, `runner_local.py` | SQLite en mode WAL avec triggers SQL append-only (`evidence`, `audit`), harness `claude-code` (mode `assist` uniquement : génère `.claude/skills/<skill>/SKILL.md`, bloc géré dans `CLAUDE.md` et brief), stubs (`copilot`, `cursor`, `bob`), `OpaPolicyEngine` (CLI `opa eval`), `FakeRunner` + `DockerRunner` durci. |
| **CLI** | `src/asac/cli/__init__.py` | 17 commandes Typer : `version`, `init`, `validate`, `vars check/diff`, `plan`, `apply`, `run`, `status`, `gates`, `approve`, `evidence show/verify/bootstrap`, `logs [--json]`, `audit`, `kill`, `learn`, `portal`, `daemon`. |
| **Portail Web** | `src/asac/portal/{app,oidc,sessions}.py`, `templates/`, `static/portal.css` | FastAPI + Jinja2 : OIDC Authorization Code + PKCE S256 (`joserfc`), personas dev bloqués hors `ASAC_ENV=dev`, sessions SQLite serveur, CSRF, CSP stricte, rate limiting, dashboard, approbation de gates, audit paginé et export CSV. |
| **Daemon Webhook** | `src/asac/daemon/{app,triggers}.py` | Récepteur `POST /webhooks/jira` authentifié par HMAC-SHA256 (`X-Hub-Signature-256`), filtrage sur `issuetype`/`labels`, création de run idempotente (`run_<pipeline>_<issue_key>`). |

### 1.3 Points forts notables

1. **Séparation des responsabilités rigoureuse** : la logique métier (`engine/`) ne dépend que des `Protocol` (`ports/`), rendant les tests rapides, déterministes (`ASAC_FIXED_TIME`, `FakeHarness`, `FakeIdP`, `sandbox_project`) et totalement offline.
2. **Intégrité garantie au niveau base de données** : `src/asac/adapters/state_sqlite.py` (lignes 64–71) impose l'immutabilité via triggers SQLite (`BEFORE UPDATE` / `BEFORE DELETE` -> `RAISE(ABORT)`) sur `evidence` et `audit`.
3. **Hygiène sécurité solide** :
   - OIDC + PKCE S256, `state`/`nonce` à usage unique, régénération de l'ID de session au login (anti-fixation), double vérification des rôles (UI + moteur), audit des tentatives refusées (`gate.denied`).
   - En-têtes HTTP défensifs (`CSP`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Cache-Control: no-store`, `HSTS`).
   - Confinement des chemins (`is_relative_to(root)`) et filtrage strict de l'environnement dans `src/asac/hooks.py`.
   - Commande Docker durcie (`--network none`, `--read-only`, `--user 65534:65534`, `--cap-drop ALL`, `no-new-privileges`, `--pids-limit 128`) dans `src/asac/adapters/runner_local.py`.

### 1.4 Décalage documentation ↔ implémentation

- **Documentation en retard sur le code** : `README.md` (ligne 7) et `docs/reference/cli.md` (ligne 4) indiquent que le portail, le runner et le daemon ne sont « pas encore implémentés », alors que `src/asac/portal/`, `src/asac/daemon/` et `src/asac/adapters/runner_local.py` sont développés et testés.
- **Ce qui reste réellement non implémenté (ou à l'état de stub)** :
  - **Registry** : port défini (`src/asac/ports/registry.py`), aucun adaptateur ; pas de commandes `registry search`, `skill publish`, `provider install` ; hooks `ref:` refusés et skills distants en warning `ASAC017`.
  - **Mode `delegate` réel & MCP** : aucun harness n'exécute réellement un agent LLM ni ne câble des serveurs MCP ; `copilot`, `cursor` et `bob` sont des stubs (`src/asac/adapters/stub_harness.py`).

### 1.5 Bugs, incohérences et limites techniques

#### Critiques / Bloquants

1. **Exception `OpaUnavailable` non gérée dans le moteur et la CLI (cause des 4 tests en échec)**
   - Dans `src/asac/engine/apply.py` (lignes 219–222), `check_policies()` appelle `OpaPolicyEngine.evaluate()` sans `try/except`. En l'absence du binaire `opa` sur `PATH`, l'exception remonte sans transition propre : la CLI crashe (`tests/test_run_e2e.py:55,187`, `tests/test_daemon.py:116`) et le portail laisse le run coincé à `running` (`tests/test_portal.py:105`).
   - Seuls `test_governance.py` et `conformance/test_policy_engine.py` vérifient `shutil.which("opa")` ; les autres tests présupposent sa présence.
2. **Escalade (`ESCALATE`) impossible à reprendre (`NotFound`)**
   - Dans `src/asac/engine/apply.py` (lignes 276–283), `_govern()` passe l'étape et le run à `gate_waiting` **sans créer de `GateRecord`**. Au prochain `asac apply --resume`, `_resolve_gate()` (lignes 358–360) appelle `ctx.store.get_gate(gid)` et lève `NotFound`.
3. **Incompatibilité `autonomy: readonly` ↔ `ClaudeCodeHarness`**
   - `permission_for()` (`src/asac/engine/governance.py:71-75`) renvoie `"readonly"`, mais `ClaudeCodeHarness.permissions()` (`src/asac/adapters/claude_code.py:70-75`) n'accepte que `("assist", "delegate")` et lève `HarnessError`.

#### Fonctionnels / Câblage incomplet

4. **Politiques custom dans `step.policies` non évaluées à l'exécution** : `checks.py` vérifie l'existence de `.asac/policies/<pol>.rego`, mais `governance.py` (lignes 106–112) ne traite que `no_regression` et ignore les autres politiques de `step.policies` (seul `step.gate.policy` est passé à OPA).
5. **Hooks `pre_tool` jamais invoqués** : `apply.py` n'exécute que `post_step` (les hooks `pre_tool` comme `secret-scan` ne sont jamais déclenchés).
6. **Outils MCP (`agent.tools`) non transmis au harness** : `apply.py` n'appelle jamais `harness.tools(agent.tools)`.
7. **`DockerRunner` non branché et non couplé au harness** : ni la CLI ni le daemon ne passent de `Runner` à `make_context()`, et `DockerRunner.start()` exécute `sleep 3600` pendant que le harness tourne encore dans le processus hôte.
8. **Champs modélisés mais non appliqués** : `budgets.per_run.wall_clock`, `pipeline.timeout`, `pipeline.specLevel`, `agent.instructions` et `agent.knowledge` sont validés dans le schéma mais non exploités au runtime (`ClaudeCodeHarness` embarque toutes les `manifest.instructions` globales sans filtrage par agent ; `checks.py` ne valide pas la syntaxe des durées ni les références `agent.knowledge`/`capability.evidence`).
9. **Divergence de `asac run`** : `docs/reference/cli.md` et `execute(..., only=...)` prévoient `asac run <step>`, mais `src/asac/cli/__init__.py` (lignes 391–399) n'accepte pas d'argument `<step>`.

#### Robustesse, Concurrence, Sécurité & Packaging

10. **Cycle de vie SQLite sur les serveurs HTTP (`portal` & `daemon`)** :
    - `store_for()` ouvre une nouvelle connexion `sqlite3.connect()` par requête sans jamais appeler `.close()` (fuite de descripteurs).
    - `SessionStore` (`src/asac/portal/sessions.py:16`) partage une unique connexion SQLite (`check_same_thread=False`) entre threads FastAPI sans verrou (`threading.Lock`).
    - `session_db` (`src/asac/portal/app.py:61`) utilise `root / ".asac-state"` en dur et ignore `ASAC_STATE_DIR`.
11. **Déterminisme et hygiène** :
    - `asac logs --json` (`src/asac/cli/__init__.py:564`) utilise `hash(run_id)` (salé par processus Python) pour `trace_id` au lieu d'un hash déterministe (`sha256`).
    - `asac learn <run_id>` (`src/asac/cli/__init__.py:683`) utilise `run_id` directement dans le nom de fichier sans `safe_name()`.
    - `OidcClient._jwks()` (`src/asac/portal/oidc.py:80-84`) met en cache les JWKS sans rafraîchissement lors d'une rotation de clé IdP.
    - `RateLimiter` (`src/asac/portal/sessions.py:48-63`) est en mémoire sans éviction et repose sur `request.client.host` (problématique derrière reverse proxy sans `X-Forwarded-For` de confiance).
12. **Dépendances `pyproject.toml`** : `joserfc` est importé directement dans `oidc.py` sans être déclaré (tiré transitivement via `authlib`), tandis que `authlib`, `itsdangerous` et `rich` sont déclarés sans import direct dans `src/asac/`.

---

## 2. Analyse du portail actuel et propositions Entreprise

### 2.1 État actuel et limites à l'échelle entreprise

Le portail actuel (`src/asac/portal/app.py`) est une application FastAPI + Jinja2 **zéro JavaScript** (CSP `default-src 'none'; style-src 'self'`), conçue pour un unique projet et un SQLite local :

| Route | Contenu actuel |
|---|---|
| `/login`, `/callback`, `/logout` | OIDC + PKCE S256 (ou 3 personas dev sous `ASAC_ENV=dev`), sessions SQLite 8h, CSRF, rate limiting. |
| `/` | 4 KPIs globaux, file « Needs your decision » filtrée par rôles, liste des runs avec rail linéaire (`topo_order`). |
| `/gates`, `POST /gates/{id}/decision` | Gates `pending` (rôle, IDs d'evidence, `timeout_at`), Approve/Reject (commentaire obligatoire au rejet), reprise synchrone `_resume()`, historique. |
| `/audit`, `/audit.csv` | Journal immuable paginé (50/page), export CSV réservé aux rôles `auditor`/`manager`. |

> **Note** : `src/asac/portal/static/portal.css` (lignes 116–129) définit déjà des classes inutilisées (`.filters`, `.graph`, `.gnode`, `.source`, `.project-list`), préfigurant des vues de filtrage, de graphe DAG, d'inspection source et multi-projets.

**Principales limites pour un usage entreprise :**
1. Mono-projet / mono-équipe (un seul `asac.yaml` par instance).
2. Décision « à l'aveugle » sur `/gates` : aucun lien ni aperçu des livrables réels (spec, MR/diff, rapport couverture/SAST, verdict OPA, brief handoff).
3. Aucune vue détail d'un run (DAG réel, preuves horodatées, coût/tokens, sorties hooks, cause précise d'échec/blocage).
4. Aucune action opérationnelle depuis l'UI (`plan`/`apply`, `resume`, `reopen`, `evidence bootstrap`, `kill`, revue `asac learn`).
5. Pas de recherche/filtres, pas de notifications (Slack/Teams/Email), pas de délégation en cas d'absence, pas de temps réel.
6. Aucune métrique FinOps, DORA ou maturité L0–L4.

### 2.2 Nouvelles fonctionnalités par persona (BA, PO, Dev, Managers)

Toutes les propositions respectent la philosophie ASAC : **`asac.yaml`, `asac.vars.yaml` et `.rego` restent la source de vérité**, le portail expose, orchestre et gouverne sans jamais contourner le moteur.

#### A. Business Analysts (BA)
1. **Atelier de spécification & suivi du `specLevel` (1 → 3)** : progression de maturité (`story` -> `spec versionnée` -> `spec exécutable`), prévisualisation Markdown/diff face au ticket Jira source, checklist `acceptance_criteria` et preuves associées (`hills_defined`, `prfaq_approved`, `spec_reviewed`).
2. **Gestion de la Knowledge Base & fraîcheur (`knowledge` / OKF)** : inventaire des sources de connaissances (`trust_tier`, `owner`, `stale_after`) avec alertes proactives avant péremption.
3. **Boucle d'itération sur handoff / escalade** : consultation du brief agent dans le portail, ajout de clarifications métier et soumission de l'evidence (`spec_reviewed`) sans CLI.
4. **Traçabilité Exigence → Code → Preuve** : vue reliant chaque ticket Jira (`PAY-123`) à sa spec, ses MR et ses preuves de vérification.

#### B. Product Owners (PO)
1. **Inbox « Decision Room » enrichie** : synthèse exécutive, liens directs vers spec/MR/preview, état des preuves amont, détail du verdict OPA, compte à rebours SLA (`timeout_at`), et distinction visuelle entre preuve **agent**, **humaine** et **bootstrapped**.
2. **Délégation, suppléance & multi-signataires (4-eyes / quorum)** : délégation temporaire auditée d'un rôle en cas d'absence, approbation à quorum (`>= 2` signataires) et **séparation des tâches (SoD)** empêchant l'auteur d'approuver sa propre release.
3. **Pilotage du backlog « Agent-Ready »** : stories Jira filtrées (`asac-enabled`), prévisualisation `asac plan` (étapes, gates, estimation tokens/coût) et déclenchement de pipeline depuis le portail.
4. **Release Readiness & Outcome Review** : vue « Release Train » des runs prêts pour la prod et espace de revue post-déploiement (`outcome_reviewed`).

#### C. Équipes Dev (Développeurs, Tech Leads, QA, DevOps/SRE)
1. **Vue détail d'un Run : Graphe DAG interactif & Inspection d'étape** : graphe `dependsOn`/`waves` avec panneau latéral par étape :
   - Agent, skill + version/digest (`#sha256:...`), harness, mode (`assist`/`delegate`), autonomie.
   - Sorties des hooks (`pre_tool`/`post_step` : `secret-scan`, `deps-verify`).
   - Évaluation OPA complète (input JSON, règles déclenchées, raisons).
   - Brief de handoff copiable/téléchargeable et action « Enregistrer preuve / Reprendre ».
2. **Console opérationnelle & observabilité temps réel** : actions RBAC (`resume`, `reopen`, `retry`, `kill` avec motif obligatoire), suivi en direct par **SSE** et **waterfall des spans OTel** (`logs --json`).
3. **Catalogue interne & Qualité/Sécurité** : explorateur du manifeste résolu, instructions (`.asac/instructions/`), politiques `.rego` + statut `asac validate`/`opa test` ; vue dédiée aux gates `quality` (couverture, SAST, `no_regression`, `deps_verified`).
4. **Workflow `asac learn` intégré** : onglet `Proposals` listant les propositions issues des échecs/blocages/rejets récurrents, avec triage et ouverture de MR/PR vers le dépôt (jamais d'application automatique).

#### D. Managers (Engineering Managers, Delivery, FinOps, CISO / Auditeurs)
1. **Vue Portefeuille Multi-Projets & Multi-Équipes** : agrégation cross-dépôts par Org / Tribu / Équipe (`asac.team`, `asac.workspace`), filtres par statut, pipeline, environnement et `data_residency`.
2. **Tableau de bord FinOps & Budgets IA** : consommation tokens et coût USD par équipe, projet, pipeline, capability, modèle et harness ; taux d'utilisation des plafonds (`budgets.per_run`, `per_step`), coût moyen par feature, détection des boucles d'itérations coûteuses.
3. **Métriques Delivery & DORA « Agent-Augmented »** : décomposition du lead time (**temps machine** vs **temps d'attente humain sur gates/handoffs**), First-Pass Yield, taux de rejet par gate, taux d'escalade et taux de fallback `delegate -> assist`.
4. **Matrice de Maturité L0–L4** : heatmap **Équipe × Capability** (`docs/guides/maturity.md`) et aide à la promotion de niveau fondée sur l'historique réel des preuves.
5. **Conformité & Pack Réglementaire (SOC2, ISO 27001, DORA, EU AI Act)** : audit explorer multi-critères, exports CSV/JSONL/PDF signés, streaming SIEM/OTel, inventaire supply-chain des skills/digests et détection de dérive (`drift`) sur la doctrine `autonomous`.

### 2.3 Socle technique transverse entreprise

| Domaine | État actuel | Cible Entreprise |
|---|---|---|
| **Persistance** | `SqliteStateStore` local + `portal-sessions.db` | `PostgresStateStore` multi-tenant + sessions/rate-limit sur Redis/PostgreSQL (HA multi-réplicas). |
| **RBAC / Identité** | Claim OIDC plat global sur un projet | RBAC scopé (`org` / `team` / `workspace`), synchro groupes Entra ID/Okta/Keycloak, SoD, délégations. |
| **Notifications & ChatOps** | Aucune | Connecteurs Slack / Microsoft Teams / Email sur `gate.opened`, `step.escalated`, alertes SLA/budget. |
| **Intégrations** | Webhook entrant Jira uniquement | Webhooks GitLab/GitHub/Linear/ServiceNow + commentaires sortants sur tickets Jira et MR. |
| **Exécution** | `_resume()` synchrone dans la requête HTTP | File asynchrone (worker dédié) + retours immédiats + diffusion SSE. |
| **API** | HTML uniquement + `/audit.csv` | API REST `/api/v1/` versionnée (OpenAPI) réutilisable par Backstage/IDP, CLI distant et BI. |

---

## 3. Décision SPA vs SSR et architecture cible du portail

### 3.1 Pourquoi basculer vers une SPA en mode BFF

Pour un outil mono-projet local, Jinja2 + zéro JS est idéal. Pour un **portail Entreprise (Dev + BA + PO + Managers)**, le SSR pur atteint vite ses limites sur 4 usages clés :
1. Graphe DAG interactif (zoom/pan + panneau d'inspection d'étape).
2. Dashboards FinOps, DORA et heatmap L0–L4 avec filtres croisés.
3. Decision Room riche (revue spec/diff/preuves côte à côte).
4. Suivi temps réel (SSE) des runs, logs et gates sans rechargement.

La base Jinja2 actuelle ne représentant que ~320 lignes Python et 4 templates simples, **le coût de bascule est minimal aujourd'hui** et évite une réécriture coûteuse après avoir ajouté de nombreux écrans.

**4 règles d'or à respecter lors de la bascule :**
1. **Conserver le pattern BFF (Backend For Frontend)** : OIDC/PKCE et les sessions restent 100 % côté FastAPI (`HttpOnly` cookie), aucun token OIDC dans `localStorage`.
2. **Conserver une CSP stricte** : `default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'` (zéro `unsafe-inline` / `unsafe-eval`).
3. **Ne pas alourdir `asac-cli`** : séparer le frontend (`portal-ui/`) et le packager dans le service/image `asac-portal`.
4. **API-First** : concevoir `/api/v1/` proprement en amont pour servir à la fois la SPA, Backstage/IDP et les intégrations CI.

### 3.2 Comparatif des options architecturales

| Critère | Option A : SSR Jinja2 + HTMX / SSE | Option B : SPA (React/TS) + BFF séparé | Option C (Recommandée) : API-first + SPA servie par FastAPI BFF |
|---|---|---|---|
| **Complexité stack / CI** | Très faible (100 % Python) | Moyenne (Python + Node + CORS) | Moyenne (1 seul déploiement prod, zéro CORS) |
| **UX DAG / Dashboards / Diffs** | Limitée | Excellente | Excellente |
| **Sécurité OIDC / Sessions** | Native | Bonne si BFF strict | **Intacte** (same-origin, cookie `HttpOnly`, CSRF header) |
| **Réutilisabilité API** | Faible | Forte | **Forte** (OpenAPI -> types TS + intégrations IDP) |

### 3.3 Architecture cible : SPA + FastAPI BFF

```text
                        ┌──────────────────────────────────────────────┐
                        │               Navigateur (SPA)               │
                        │  React + TypeScript + Vite (assets statiques)│
                        │  • Cookie HttpOnly (session opaque)          │
                        │  • Header X-CSRF-Token sur mutations         │
                        │  • EventSource (SSE) pour le temps réel      │
                        └───────────────┬──────────────────────────────┘
                                        │ HTTPS (même origine, zéro CORS)
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     FastAPI BFF & API (asac-portal)                          │
│  • /auth/*          : OIDC + PKCE S256 (oidc.py), sessions serveur           │
│  • /api/v1/*        : API REST JSON (OpenAPI généré -> types TS auto)        │
│  • /api/v1/stream   : SSE (avancement runs, gates ouvertes, alertes)         │
│  • /* (fallback)    : Sert dist/index.html (build Vite) en production        │
└──────┬──────────────────────┬───────────────────────┬────────────────────────┘
       │                      │                       │
       ▼                      ▼                       ▼
┌─────────────┐      ┌──────────────────┐    ┌────────────────────────┐
│ StateStore  │      │  Session / Rate  │    │  Worker asynchrone     │
│ • SQLite    │      │  • SQLite (dev)  │    │  • execute / resume    │
│   (local)   │      │  • Redis / PG    │    │  • DockerRunner / K8s  │
│ • Postgres  │      │    (entreprise)  │    │  • Notifications       │
│   (ent.)    │      └──────────────────┘    │    (Slack/Teams/Jira)  │
└─────────────┘                              └────────────────────────┘
```

### 3.4 Modèle de sécurité BFF et RBAC scopé

- **Session & CSRF** : `GET /api/v1/me` renvoie `csrf_token` (stocké en mémoire JS uniquement). Toutes les mutations (`POST`/`PUT`/`PATCH`/`DELETE`) vérifient `X-CSRF-Token`. Les tokens machine-à-machine (PAT / OIDC service account pour CI/Backstage) utilisent `Authorization: Bearer ...` sans cookie.
- **Rotation JWKS** : rafraîchissement automatique du `KeySet` dans `OidcClient` si un `kid` inconnu apparaît.
- **RBAC scopé** : attribution des rôles par niveau (`org:<id>`, `team:<id>`, `workspace:<id>`) + délégations temporaires auditées :

```json
{
  "sub": "alice-sub",
  "name": "Alice Martin",
  "email": "alice@corp.example",
  "bindings": [
    { "scope": "org:acme", "roles": ["auditor"] },
    { "scope": "team:payments", "roles": ["product_owner"] },
    { "scope": "workspace:payments-service", "roles": ["developer"] }
  ],
  "delegations": [
    {
      "from": "bob-sub",
      "scope": "workspace:billing-api",
      "role": "product_owner",
      "expires_at": "2026-12-01T18:00:00Z"
    }
  ]
}
```

| Rôle | Permissions principales sur son scope |
|---|---|
| `developer` | Consulter runs/DAG/logs/hooks/OPA/manifeste, lancer `plan`/`apply`, `resume`, `reopen`, bootstrapper une evidence `assist`, trier les proposals `learn`. |
| `ba` | Suivre `specLevel`, gérer la fraîcheur `knowledge`, répondre aux handoffs/escalades `requirements`, soumettre `spec_reviewed`. |
| `product_owner` | Décider les gates `product_owner`, déclencher des runs depuis le backlog, gérer ses délégations, suivre Release Readiness. |
| `qa_engineer` | Décider les gates `quality`, inspecter couverture/SAST/`no_regression`, rejeter/rouvrir. |
| `engineering_manager` | Vue portefeuille équipe/tribu, dashboards FinOps/DORA/Maturité L0–L4, `kill`-switch, export audit. |
| `auditor` | Lecture seule transverse sur l'org, audit trail complet, exports signés CSV/JSONL, rapports conformité. |
| `platform_admin` | Gestion des workspaces, connecteurs (Jira, GitLab, Slack/Teams) et politiques d'organisation. |

**Contrôles imposés côté moteur (`engine/`), jamais uniquement dans l'UI** : séparation des tâches (SoD), quorum multi-signataires et journalisation systématique (`gate.denied`, `role.delegated`, `audit.exported`, `run.killed`, `gate.reopened`).

### 3.5 Contrat API `/api/v1/`

- **Erreurs** : RFC 7807 (`application/problem+json`).
- **Pagination** : `?cursor=...&limit=50` -> `{ "items": [...], "next_cursor": "...", "total": 142 }`.
- **Idempotence** : header `Idempotency-Key` sur `POST /runs` et `POST /gates/{id}/decision`.

#### Identité & Session
| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/auth/login` | Redirection OIDC + PKCE (ou persona en `ASAC_ENV=dev`) |
| `GET` | `/auth/callback` | Échange du code, validation ID token, pose du cookie session |
| `POST` | `/auth/logout` | Destruction session serveur et cookie |
| `GET` | `/api/v1/me` | Identité, rôles scopés, délégations actives, `csrf_token` |

#### Workspaces, Manifeste, Knowledge & Politiques
| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/workspaces` | Liste des projets/équipes accessibles + résumé santé |
| `GET` | `/api/v1/workspaces/{ws}/manifest` | Manifeste résolu (hors secrets) + diagnostic `asac validate` |
| `GET` | `/api/v1/workspaces/{ws}/knowledge` | Sources `knowledge`, `trust_tier`, statut `stale_after` |
| `GET` | `/api/v1/workspaces/{ws}/policies` | Fichiers `.rego` et dernier statut `opa test` |
| `GET` | `/api/v1/workspaces/{ws}/proposals` | Propositions `asac learn` (`open`/`accepted`/`dismissed`, lien PR) |

#### Runs, DAG & Temps réel
| Méthode | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/workspaces/{ws}/plan` | Dry-run : vagues DAG, gates, estimation tokens/coût (`over_budget`) |
| `GET` | `/api/v1/workspaces/{ws}/runs` | Liste filtrable (`status`, `pipeline`, `actor`, `q`, `from`, `to`) |
| `POST` | `/api/v1/workspaces/{ws}/runs` | Démarrage asynchrone d'un run |
| `GET` | `/api/v1/runs/{run_id}` | Synthèse (statut, pipeline, `specLevel`, spend vs budget, preuves, gates) |
| `GET` | `/api/v1/runs/{run_id}/graph` | DAG (`nodes` par vague + métadonnées, `edges` `dependsOn`/`requiresEvidence`) |
| `GET` | `/api/v1/runs/{run_id}/steps/{step_id}` | Inspection détaillée (brief, hooks, verdict OPA, itérations) |
| `GET` | `/api/v1/runs/{run_id}/traces` | Spans OTel déterministes (vue waterfall) |
| `GET` | `/api/v1/runs/{run_id}/stream` | Flux **SSE** temps réel |
| `POST` | `/api/v1/runs/{run_id}/resume` | Reprise asynchrone (`{ "reopen": false }`) |
| `POST` | `/api/v1/runs/{run_id}/kill` | Kill-switch (`{ "reason": "..." }`) + arrêt du runner |

#### Gates, Décisions & Preuves
| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/gates` | File cross-workspaces filtrable (`status`, `mine`, `role`, `workspace`, `expiring_soon`) |
| `GET` | `/api/v1/gates/{gate_id}` | Dossier Decision Room (preuves, liens artefacts, verdict OPA, SLA, historique, SoD/quorum) |
| `POST` | `/api/v1/gates/{gate_id}/decision` | `{ "decision": "approve" \| "reject", "comment": "..." }` |
| `GET` | `/api/v1/runs/{run_id}/evidence` | Preuves immuables (agent/humain/bootstrapped) + vérification |
| `POST` | `/api/v1/runs/{run_id}/evidence/bootstrap` | Enregistrement d'une preuve externe / mode `assist` |
| `GET`/`POST`/`DELETE` | `/api/v1/delegations` | Gestion des délégations temporaires de rôle |

#### Métriques Entreprise & Audit
| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/metrics/overview` | KPIs agrégés sur scope (`org`/`team`/`workspace`) et période |
| `GET` | `/api/v1/metrics/finops` | Tokens & coût USD par équipe/projet/capability/modèle/harness + alertes budget |
| `GET` | `/api/v1/metrics/dora` | Lead time (agent vs attente humaine), First-Pass Yield, taux rejet/escalade/fallback |
| `GET` | `/api/v1/metrics/maturity` | Matrice Équipe × Capability (`L0`–`L4`) et critères de promotion |
| `GET` | `/api/v1/audit` | Recherche multi-critères dans le journal append-only |
| `GET` | `/api/v1/audit/export` | Export `csv` ou `jsonl` (`auditor` / `engineering_manager`), audité |

### 3.6 Arborescence cible et stack Frontend

```text
asac/
├── src/asac/
│   ├── engine/               # Source de vérité métier
│   ├── ports/                # + filtrage/pagination/multi-workspace
│   ├── adapters/
│   │   ├── state_sqlite.py   # Local / dev
│   │   └── state_postgres.py # Multi-tenant entreprise (Lot 2)
│   └── portal/
│       ├── app.py            # Montage BFF (/auth, /api/v1, static dist/)
│       ├── oidc.py           # + refresh JWKS automatique
│       ├── rbac.py           # Rôles scopés, SoD, délégations
│       ├── sessions.py       # Interface SessionStore (SQLite / Redis)
│       ├── worker.py         # File asynchrone execute/resume + bus SSE
│       └── api/              # Routeurs FastAPI par domaine
│           ├── me.py
│           ├── workspaces.py
│           ├── runs.py
│           ├── gates.py
│           ├── evidence.py
│           ├── metrics.py
│           └── audit.py
│
└── portal-ui/                # SPA indépendante (Node/Vite/TypeScript)
    ├── package.json
    ├── vite.config.ts        # Proxy /api et /auth vers FastAPI en dev
    └── src/
        ├── app/              # Router, AuthProvider (GET /api/v1/me), QueryClient
        ├── api/              # Client fetch (CSRF auto) + types générés OpenAPI
        ├── design-system/    # Tokens repris de portal.css (couleurs, pills, badges)
        ├── layouts/          # Shell avec navigation par rôle + sélecteur workspace
        └── features/
            ├── inbox/        # PO / QA / BA : Decision Room + SLA + délégations
            ├── runs/         # Dev : Liste filtrée + Graphe DAG + Waterfall OTel + SSE
            ├── specs/        # BA : Suivi specLevel (1->3), fraîcheur Knowledge
            ├── catalog/      # Dev : Explorateur asac.yaml, policies Rego, proposals learn
            ├── analytics/    # Managers : FinOps, DORA, Matrice L0–L4
            └── audit/        # Auditeurs : Explorer multi-critères + exports CSV/JSONL
```

**Stack Frontend recommandée** :
- **React + TypeScript strict + Vite** (build statique compatible CSP stricte, zéro lib OIDC côté client).
- **TanStack Query** (cache API, invalidation sur événements SSE) + **TanStack Table** (tableaux/audit performants).
- **React Flow** (ou Cytoscape) pour le graphe DAG interactif.
- **Apache ECharts** (ou Recharts) pour les graphiques FinOps, DORA et heatmap L0–L4.
- **`openapi-typescript`** pour générer automatiquement les types TS depuis le schéma OpenAPI FastAPI.

### 3.7 Plan de migration incrémental

1. **Étape 0 — Stabilisation moteur & BFF (Python existant)**
   - Gérer proprement `OpaUnavailable`, créer un `GateRecord` sur `ESCALATE`, supporter `readonly` dans `ClaudeCodeHarness`, évaluer les `.rego` de `step.policies`.
   - Fermer les connexions `SqliteStateStore` par requête, sécuriser `SessionStore` contre la concurrence, respecter `ASAC_STATE_DIR`, rendre `trace_id` déterministe (`sha256`), ajouter `joserfc` dans `pyproject.toml`, et exécuter `_resume` via un worker asynchrone.
   - Mettre à jour `README.md` et `docs/reference/cli.md`.
2. **Étape 1 — API-First (`/api/v1/*`)**
   - Exposer les endpoints JSON du Lot 1 (`me`, `workspaces`, `runs`, `graph`, `gates`, `decision`, `evidence`, `audit`) avec les garanties OIDC/CSRF/RBAC existantes et générer les types TypeScript OpenAPI.
3. **Étape 2 — Socle SPA (Parité + Lot 1 Opérationnel Dev/BA/PO)**
   - Créer `portal-ui/` avec les 4 vues cœur : **Inbox Décisions**, **Runs + DAG + Inspection d'étape**, **Specs & Knowledge**, **Audit filtré**, servis depuis FastAPI BFF.
4. **Étape 3 — Entreprise Multi-équipes, FinOps & Conformité (Lots 2 & 3)**
   - Ajouter `PostgresStateStore` + `RedisSessionStore`, RBAC scopé, notifications Slack/Teams/Jira sortant, dashboards **FinOps / DORA / Maturité L0–L4**, puis SoD, quorum et exports conformité signés / SIEM.
