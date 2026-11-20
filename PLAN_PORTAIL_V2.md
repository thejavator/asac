# Plan : portail ASAC v2 (SPA, BFF, API, administration, forges)

Statut : **proposition à valider**. Aucun code n'est modifié tant que ce plan n'est pas approuvé.

## 1. Objectif

Un portail utilisé à l'échelle de l'entreprise (petite structure avec beaucoup de projets, ou grande organisation) pour :

1. Gérer les accès par rôle (organisation et projet).
2. Administrer ASAC complètement (projets, connexions, rôles, politiques, registres, harness, runners, notifications, audit).
3. Consulter le détail des runs : étapes, prompts et sorties des agents, livrables, preuves, hooks, coûts, logs, audit.
4. Suivre et traiter les erreurs (liste, relance, reprise, arrêt, webhooks rejetés).
5. Éditer le pipeline et sauvegarder via git (branche puis MR ou PR).
6. Configurer les URL et connexions par projet (forge, tracker, wiki).

## 2. Architecture

| Couche | Choix | Rôle |
|---|---|---|
| Front | React, TypeScript, Vite, TanStack Router et Query | Écrans, cache, navigation |
| Éditeur | React Flow (graphe), Monaco (YAML) | Édition visuelle et texte synchronisées |
| BFF | FastAPI (existant) | OIDC code + PKCE, session serveur, cookie `HttpOnly; Secure; SameSite=Lax`, CSRF, CSP |
| API | `/api/v1`, OpenAPI généré, client TS généré | Source unique de vérité, aussi pour la CI et Backstage |
| Services | Couche `services/` appelée par l'API et par le CLI | Pas de logique dans les routes |
| Workers | File de jobs en Postgres (`SKIP LOCKED`) | Reprises de run, sync forge, webhooks, notifications |
| Données | Postgres en production, SQLite en local et tests | Via ports, comme aujourd'hui |

Le SPA est servi en fichiers statiques par le même FastAPI : une origine, pas de CORS, un seul déploiement. Le BFF ne voit jamais de jeton d'accès dans le navigateur.

## 3. Ports et adaptateurs (nouveaux ou étendus)

| Port | Rôle | Adaptateurs prévus |
|---|---|---|
| `ProjectRegistry` (existant) | Liste des projets | `postgres` (cible), `file` et `single` (existants, dev) |
| `Forge` (nouveau) | Dépôts, fichiers, branches, commits, MR/PR, membres, webhooks | `git` générique, `gitlab`, `github`, puis `gitea`/`forgejo`, `bitbucket`, `azure_devops` |
| `Tracker` (nouveau) | Tickets, déclencheurs | `jira` (Cloud et Data Center), `gitlab_issues`, `github_issues`, `azure_boards` |
| `Wiki` (nouveau) | Documentation liée au projet | `confluence`, `gitlab_wiki`, `github_wiki` |
| `ArtifactStore` (nouveau) | Livrables des runs | `filesystem`, `s3` |
| `JobQueue` (nouveau) | Travail asynchrone | `postgres`, `sqlite` (dev) |
| `IdentityDirectory` (nouveau) | Groupes et rôles de l'IdP | `oidc_claims`, `scim` (plus tard) |
| `StateStore`, `Gate`, `Runner`, `Harness`, `PolicyEngine` (existants) | Inchangés | — |

Règle : le moteur, l'API et les services n'importent que les ports. Chaque port a une suite de conformité exécutée sur chaque adaptateur.

## 4. Modèle de données (Postgres, schéma unique)

Schéma unique avec `project_id` et Row-Level Security Postgres (remplace le schéma par projet, qui ne passe pas à l'échelle). En SQLite, la même séparation est faite par colonne, sans RLS.

| Table | Contenu |
|---|---|
| `organizations` | Une par installation (extensible) |
| `projects` | id, nom, connexion forge, chemin du dépôt, branche par défaut, commit du manifeste, statut de synchronisation, archivé |
| `project_connections` | projet, type (`forge`, `tracker`, `wiki`), adaptateur, URL, référence de secret `${vault...}`, état du dernier test |
| `project_members` | projet, utilisateur (sub OIDC), rôle projet, source (`manual`, `forge`, `idp_group`) |
| `org_members` | utilisateur, rôle d'organisation |
| `group_role_map` | groupe IdP → rôle (organisation ou projet), géré par l'admin |
| `runs` | (existant) + `project_id`, déclencheur, coût, commit du pipeline utilisé |
| `gates` | (existant) |
| `artifacts` | run, étape, nom, type, digest, emplacement dans `ArtifactStore` |
| `jobs` | file de travail : type, payload, état, tentatives, verrou |
| `webhook_events` | événements reçus, signature vérifiée ou non, état (accepté, rejeté, rejoué) |
| `pipeline_drafts` | brouillons de l'éditeur : projet, auteur, contenu, commit de base, branche, MR liée |
| `audit` | (existant) avec `project_id` et `actor_type` (humain, système, agent) |

Toute modification d'administration est écrite dans `audit`.

## 5. Rôles et permissions

**Organisation** : `admin` (tout administrer), `auditor` (lecture globale et export), `member` (créer des projets si autorisé).

**Projet** : `owner` (administration du projet et des connexions), `product_owner` (approuve les gates de décision métier), `qa` (approuve les gates de qualité), `developer` (lance et relance les runs, édite le pipeline), `reader` (consulte).

Règles :
- Une permission est vérifiée dans l'API, pas seulement dans l'écran. Un test par endpoint vérifie le refus pour chaque rôle insuffisant.
- Le moteur revérifie le rôle à chaque décision de gate (déjà le cas).
- Un utilisateur voit un projet s'il en est membre (source `forge` ou `manual`), ou si un de ses groupes IdP est mappé.
- Séparation des tâches (SoD) : l'auteur d'une modification de pipeline ne peut pas approuver sa propre MR de pipeline. Règle moteur, testée.
- Le compte de service d'une forge ou d'un tracker n'a jamais de rôle humain.

## 6. API `/api/v1` (extrait)

| Méthode et chemin | Rôle minimum |
|---|---|
| `GET /projects`, `POST /projects` | reader / org member |
| `GET /projects/{id}` | reader |
| `PUT /projects/{id}/connections/{type}` | owner |
| `POST /projects/{id}/connections/{type}/test` | owner |
| `GET /projects/{id}/runs`, `POST /projects/{id}/runs` | reader / developer |
| `GET /runs/{id}`, `GET /runs/{id}/artifacts`, `GET /runs/{id}/events` | reader |
| `POST /runs/{id}/resume`, `POST /runs/{id}/kill` | developer |
| `GET /gates`, `POST /gates/{id}/decision` | product_owner ou qa selon le gate |
| `GET /projects/{id}/pipeline` | reader |
| `POST /projects/{id}/pipeline/drafts` | developer |
| `POST /pipeline/drafts/{id}/validate` | developer |
| `POST /pipeline/drafts/{id}/submit` (branche + MR) | developer |
| `GET /admin/users`, `PUT /admin/group-roles` | admin |
| `GET /errors`, `POST /errors/{id}/retry` | developer (son projet) / admin |
| `GET /webhooks/events`, `POST /webhooks/events/{id}/replay` | admin |
| `GET /audit`, `GET /audit.csv` | auditor |
| `POST /webhooks/forge/{connection}` | signature de l'adaptateur (pas de session) |

Erreurs au format `application/problem+json` (RFC 9457). Pagination par curseur. Schéma OpenAPI publié et versionné.

## 7. Éditeur de pipeline et sauvegarde git

1. L'éditeur charge `asac.yaml` au commit de base (`read_file`).
2. Le graphe et le YAML sont synchronisés. Le YAML est validé en continu avec le JSON Schema exporté, puis avec le validateur complet (côté serveur, pour les règles croisées).
3. « Enregistrer » crée un brouillon (`pipeline_drafts`), sans rien écrire dans git.
4. « Proposer » : création d'une branche `asac/pipeline-<id>`, commit du fichier, ouverture d'une change request (`create_branch`, `commit_files`, `open_change_request`). Le message de commit contient l'auteur réel.
5. Conflit : si la branche par défaut a changé le fichier depuis le commit de base, la soumission est refusée avec le diff, et l'utilisateur doit rebaser son brouillon.
6. Push direct sur la branche par défaut : désactivé par défaut, activable par projet, et soumis à la politique OPA.
7. À la fusion de la change request (webhook), le portail marque le brouillon comme appliqué et rafraîchit le projet.

## 8. Gestion des erreurs

- Liste unifiée : échecs de run, politiques refusées (OPA), budgets dépassés, harness indisponible, runner en échec, connexion forge ou tracker en erreur, webhook rejeté, job en échec.
- Chaque erreur a une catégorie, un message lisible, la cause technique, et les actions permises selon le rôle (relancer, reprendre, arrêter, ignorer avec commentaire audité).
- Les tests de connexion donnent un diagnostic (jeton invalide, URL inaccessible, permission manquante).
- Alertes : une erreur répétée sur un projet crée une notification (canal configuré : e-mail, Teams, Slack, webhook).

## 9. Détail d'un run

Onglets : **Résumé** (statut, durée, coût, déclencheur, commit du pipeline), **Étapes** (graphe SVG déjà existant, puis graphe interactif), **Sorties** (prompt, réponse, sorties d'outils), **Livrables** (téléchargement via `ArtifactStore`), **Preuves** (evidence, vérification, type agent, humain ou bootstrapped), **Hooks** (résultat et sortie), **Audit**, **Journal** (logs et spans OpenTelemetry).

## 10. Sécurité

- OIDC code + PKCE S256, `state` et `nonce`, JWKS avec rafraîchissement.
- Sessions serveur, rotation à la connexion, expiration, déconnexion globale.
- CSRF sur toutes les mutations (jeton en en-tête pour l'API).
- CSP stricte : `script-src 'self'`, pas de script ni de style inline. Le SPA est construit sans inline.
- Secrets : uniquement des références `${vault...}`, jamais stockés ni journalisés. Test de redaction sur l'API, le journal et l'audit.
- Signature des webhooks forge et tracker (HMAC ou jeton selon l'adaptateur), vérifiée avant tout traitement. Déjà en place pour le webhook générique.
- Rate limiting sur la connexion, les décisions et les tests de connexion.
- `X-Forwarded-For` accepté seulement depuis les proxys de confiance (point ouvert du plan précédent, traité ici).

## 11. Tests

- Unitaires sur les services et les règles de rôles.
- Tests d'API : une matrice rôle × endpoint.
- Conformité par port, exécutée sur chaque adaptateur.
- Forge : GitLab CE et Gitea en conteneur (vrais serveurs) ; GitHub, Bitbucket et Azure DevOps contre des réponses enregistrées. Tests d'intégration optionnels avec de vrais comptes.
- Playwright sur les parcours critiques : connexion, décision de gate, éditeur et soumission, administration.
- Sécurité : test de CSRF, de CSP, d'accès refusé, de fuite de secret, de rejeu de webhook.

## 12. Ordre de réalisation

| Étape | Contenu | Sortie |
|---|---|---|
| **1. Socle** | Schéma Postgres, `JobQueue`, `/api/v1` avec OpenAPI, RBAC à deux niveaux, matrice de tests | Pages Jinja existantes toujours vertes |
| **2. Projets et connexions** | Registre en base, administration des projets, connexions avec test | Plus de YAML pour les projets |
| **3. SPA, lecture** | Liste des projets, détail d'un run, Decision Room, erreurs | Parcours de lecture complet |
| **4. Administration** | Utilisateurs, mapping groupes → rôles, webhooks, audit | Administration utilisable sans toucher à la base |
| **5. Port `Forge`** | Suite de conformité, adaptateur `git` générique, puis GitLab et GitHub | Découverte des projets et lecture de `asac.yaml` |
| **6. Éditeur** | Brouillons, validation, branche, MR, conflits, fusion | Pipeline modifiable et sauvegardé via git |
| **7. Ports `Tracker` et `Wiki`** (fait) | Jira, GitLab/GitHub issues, Confluence, wiki GitLab | Liens et déclencheurs |
| **8. Runner réel (point 7)** (fait : Docker + Claude Code) | `Runner` passé explicitement, exécution en conteneur | Les runs contiennent de vraies sorties |
| **9. Livrables et coûts** (fait) | `ArtifactStore`, coûts et tokens enregistrés | Onglets Livrables et Résumé complets |
| **10. Retrait de Jinja** (fait) | Suppression des pages SSR une fois la SPA complète | Une seule interface |
| **11. Forges restantes** (fait) | Gitea et Forgejo, Bitbucket, Azure DevOps | Couverture complète |

Les étapes 5 et 8 peuvent avancer en parallèle, car elles touchent des fichiers différents.

## 13. Hors périmètre de ce plan

Routage multi-agents, critique, indicateurs DORA et FinOps complets (à faire après l'étape 9), packaging Helm et PyPI (M6 existant), registre OCI (M6 existant).

## 14. Questions à trancher avant de commencer

1. **Base de données** : Postgres obligatoire en production, SQLite seulement en local et tests. Confirmé ?
2. **Déclaration des connexions** : les URL et les jetons sont saisis dans le portail (chiffrés par référence vault) ou seulement par l'administrateur de la plateforme ? Ma proposition : admin saisit, owner de projet peut modifier l'URL dans les limites de l'organisation.
3. **Synchronisation des membres** : on lit les membres de la forge à chaque connexion, ou on synchronise toutes les heures ? Ma proposition : à la connexion, avec cache de 15 minutes.
4. **Push direct** : autorisé par défaut ou désactivé ? Ma proposition : désactivé.
5. **Étape 8** : l'exécution réelle des agents (point 7) entre-t-elle dans ce plan ou reste-t-elle un chantier séparé ? Ma proposition : étape 8, mais en parallèle de la SPA.
