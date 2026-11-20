# Liste globale des tâches ASAC

Mise à jour : 2026-11-20. Ordre des priorités : celui accepté dans la décision de positionnement (parcours de bout en bout, sécurité des agents, harnais headless, portail, FinOps et Postgres). Chaque tâche livrée doit passer `ruff`, `mypy`, `pytest -n auto` et `zensical build --strict`.

Légende : [ ] à faire, [~] en cours, [x] fait.

## État de départ (fait)

- [x] CLI local : `validate`, `plan`, `apply`, gates, preuves, audit, `kill`, `learn`.
- [x] Moteur séquentiel avec budgets, autonomie, escalade, hooks `run:`, reprise.
- [x] Harness Claude Code (assist et delegate), runner Docker (testé avec des fakes).
- [x] Portail v2 : SPA, API `/api/v1`, OIDC, Decision Room, audit, administration, multi-projets.
- [x] Éditeur de pipeline et 6 forges (git, GitHub, GitLab, Gitea/Forgejo, Bitbucket, Azure DevOps).
- [x] Tracker, wiki, livrables et coûts.
- [x] Écran de connexion qui sert de page d'accueil.

## 1. Fiabiliser le parcours de bout en bout

- [ ] Tester le runner Docker et `claude -p` pour de vrai (machine avec Docker et Claude Code).
- [x] Corriger les textes périmés « portail, runner non implémentés » : `README.md:7`, `docs/index.md:14`, `docs/visuals/*.html` (4 pages), `docs/project/roadmap.md`, `versioning.md`. Nouveau texte : le CLI, le portail, le runner Docker et le harness Claude Code fonctionnent ; les autres harnesses et le registre ne sont pas implémentés.
- [x] Reprise et relance automatiques après échec (retry avec plafond, journal).
- [ ] Démo de 15 minutes : installer, voir un agent contraint par une règle, preuve consultable.

## 2. Sécurité des agents et MCP (décision : étapes 1 à 4, Claude Code seul, sans passerelle)

- [x] **MCP 1. Schéma.** Bloc `mcp: {command | url, args, env}` optionnel sur le provider, avec références `${vault...}` pour les secrets. Extension de la couche 2 (v0.4 reste gelé). Schéma JSON, validateur (nouveau code d'erreur), documentation.
- [x] **MCP 2. Génération de config.** Claude Code : écrire `.mcp.json` limité aux serveurs de l'agent de l'étape. Secrets passés par variables d'environnement résolues à l'exécution, jamais écrits dans le fichier.
- [x] **MCP 3. Filtrage.** `--allowedTools mcp__<serveur>__*` sur `claude -p`, pour qu'un agent n'appelle que ses serveurs.
- [x] **MCP 4. Audit.** Entrée `tools.exposed` par étape. Test de redaction : aucun secret dans le fichier, les logs, l'audit.
- [x] Tests avec un faux serveur MCP ; documentation (`harness.md`, `cli.md`, retrait de « MCP wiring not implemented »).
- [ ] Plus tard : passerelle MCP (liste d'autorisation, injection de secrets, journal des appels).
- [ ] Preuves de sécurité : `deps_verified`, `no_regression`, hooks `pre_tool`.
- [ ] Proxys de confiance pour `X-Forwarded-For` (limitation de débit).

## 3. Harnesses headless supplémentaires

- [x] Exécution `delegate` pour Codex et Cursor (tests avec fakes). Bob et Copilot restent assist seulement (pas de commande headless), documenté.
- [x] Runner Kubernetes (pod par étape, testé sans cluster). [ ] Runner GitLab.
- [x] Sémantique de `specLevel` (avertissements ASAC026).

## 4. Orchestration

- [x] Exécution parallèle des étapes indépendantes (`parallel`, 1 à 8).
- [ ] Routage multi-modèles (`routing`, design à décider, backlog v0.5).
- [ ] Pattern `critic` (« QA ≠ dev » comme pattern déclaré, backlog v0.5).
- [x] File de jobs Postgres (`SKIP LOCKED`), conformité et test de concurrence. [ ] Workers qui consomment la file.

## 5. Portail et multi-équipes

- [x] Projets en base (SQLite, `portal-admin.db`) : création, modification, archivage, organisation ; fichier `projects.yaml` et option `--projects` supprimés ; mappages de rôles dans le portail seulement.
- [ ] Registre de projets Postgres (même suite de conformité).
- [x] Commande `asac project add|list|archive` pour amorcer le premier projet sans passer par l'interface.

### Fonctionnalités à ajouter (proposées le 2026-11-20)

Fait : page Erreurs par projet (événements en erreur ; webhooks rejetés du daemon pas encore dans l'audit), Decision Room unifiée (tous les scopes, filtre « ce que je peux signer »), lancement de run depuis l'interface après plan et estimation, vue en direct (rafraîchie toutes les 2 s) et bouton Stop, notifications (cibles par projet `notify_targets` via vault, compteur dans la navigation et le titre de l'onglet).

Ordre proposé (reste) : KPI de flux et de coût → connexions par projet + administration des webhooks.

- **Administration** : connexions par projet avec bouton Tester ; webhooks reçus, rejetés, rejeu ; membres au niveau organisation ; budgets et quotas ; politiques (Rego) ; configuration du runner ; sessions et déconnexion forcée ; jetons de service ; rétention et purge.
- **Agents** : catalogue par projet ; vue d'un run en direct avec Stop ; lancer un run depuis l'interface après plan et estimation de coût ; relance et reprise ; file de jobs et workers ; passages de relais assist et escalades ; santé des runners ; outils exposés.
- **KPI et statistiques** : délais d'attente des gates ; taux de succès, d'escalade et de reprise par agent et par harness ; delegate contre assist ; coût par run, projet, équipe et modèle avec budgets et alertes ; rejets de gate, violations de politique, preuves amorcées ; DORA ; adoption ; export CSV, API, OpenTelemetry.
- **Autres** : page Erreurs unifiée ; boîte « Mes décisions » ; notifications ; rapport de conformité de release ; revue des propositions `asac learn` ; historique et diff des pipelines ; recherche globale ; catalogue de skills ; i18n fr/en et contrôle d'accessibilité.
- [ ] Découverte des membres depuis la forge.
- [ ] Webhook de fusion : marquer un brouillon appliqué sans ouvrir le brouillon.
- [ ] Paramètres de forge par projet dans l'interface ; administration des webhooks ; membres au niveau organisation.
- [ ] Vérifier avec la persona `admin` les pages Access et Administration.
- [ ] Tests frontend (vitest) et parcours Playwright : connexion, décision de gate, éditeur, administration.
- [ ] Test navigateur du téléchargement de l'onglet Hooks.
- [ ] Tester les adaptateurs de forge contre de vrais serveurs (GitLab CE, Gitea en conteneur).
- [ ] `npm audit` : avis vitest (dev seulement).

## 6. Registre, données, FinOps

- [ ] Registre : adaptateur filesystem, puis OCI (cosign) ; hooks `ref:` ; `asac skill publish`, `registry search`, `provider install`.
- [ ] `ProjectRegistry` Postgres avec RLS ; `ArtifactStore` Postgres ou S3.
- [ ] Suites de conformité supplémentaires.
- [ ] FinOps, DORA, maturité.

## 7. Publication

- [ ] Vérifier avec IBM (contrat, propriété intellectuelle, noms Bob, wxO, ICA, textes TLT) avant toute annonce.
- [ ] Empaquetage PyPI (`asac` ou `asac-cli`), chart Helm.
- [ ] Garder hors périmètre tant qu'il n'y a pas d'utilisateur externe : SoD, quorum, SIEM, RBAC par portée.

## Backlog spec v0.5

`routing`, `critic`, `integration_green`, `e2e_green`, `canary_healthy`, `post_deploy_verified`, `monitor.signal`, index de connaissance sémantique, `scope.paths`, `arch_conform`, Golden Paths (détails : `docs/project/roadmap.md`).
