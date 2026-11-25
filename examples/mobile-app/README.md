# Exemple : application mobile (Flutter, iOS et Android)

Une application mobile avec un backend d'API existant. Ce que ce cas montre et que les autres ne
montrent pas : des **outils différents selon l'étape** (un IDE pour la conception, un outil sans
interface pour le code), des contrôles propres au mobile, et une **validation sur appareil réel**.

```bash
cd examples/mobile-app
asac validate                                    # 0 error(s), 0 warning(s)
asac plan -p feature                             # 5 étapes
cp asac.vars.yaml.example asac.vars.yaml
asac vars check
```

## Les pipelines

| Pipeline | Étapes | Ce qu'il montre |
|---|---|---|
| `feature` | `design` → `requirements` → `implementation` → `device_check` → `release` | Un outil non headless (IDE) sur la conception, `delegate` sur le code, une gate tenue par une personne **devant l'appareil**, une livraison aux magasins |
| `hotfix` | `fix` → `release` | Correctif d'une version publiée : pas de conception, pas d'appareil, un relecteur |

`asac validate` refuse un agent `delegate` dont l'outil n'est pas headless (`ASAC013`) : l'agent
`designer` (un IDE, `copilot`) reste en `assist`. C'est voulu.

## Les contrôles (hooks), testés sur un vrai projet Flutter

| Hook | Vérifie | Bloque ? |
|---|---|---|
| `no-secrets` (global) | pas de clé ni de mot de passe de signature dans le dépôt | oui |
| `design-present` | `DESIGN.md` couvre chargement, erreur, hors ligne, accessibilité, texte à 200 % | oui |
| `spec-present` | `SPEC.md` a des critères d'acceptation et dit un mot des permissions | oui |
| `flutter-analyze` | `flutter analyze --fatal-infos` | oui |
| `flutter-tests` | `flutter test` | oui |
| `a11y` | chaque `IconButton`/zone tactile a un libellé (`tooltip`, `Semantics`) | oui |
| `permissions` | aucune permission Android/iOS ajoutée sans être demandée dans `SPEC.md` | oui |
| `app-size` | taille du paquet Android sous le budget | **non** (`warn`) |
| `changelog` | `CHANGELOG.md` a une entrée pour la version de `pubspec.yaml` | oui |

La politique `mobile-budget.rego` juge le rapport de l'outil après chaque lancement de
`implementation` : un coût inconnu, ou un tour trop cher, bloque.

## Une preuve que ni un script ni un agent ne remplacent

`device_check` est une gate `human` tenue par le rôle `qa_engineer`. L'agent prépare une liste de
vérifications ; **une personne tient le téléphone** et approuve un commit précis. La v1 n'a pas de
gate automatique : c'est dit, et l'exemple n'en simule pas une.

## Ce que la v1 n'applique pas, et que cet exemple écrit quand même

`asac validate` le dit en avertissement (`ASAC027`) ; il ne le cache pas.

| Clé | Ce qui se passe en 0.1 |
|---|---|
| `knowledge` | Acceptée, jamais donnée à l'agent. |
| `pipelines.<p>.specLevel` | Vérifié par `validate` (`ASAC026`), jamais imposé par le moteur. |
| `pipelines.<p>.trigger` | Lu par le daemon, qui n'est pas supporté en 0.1 : `asac apply` l'ignore. |
| `gate: { type: automated }` | Acceptée par le modèle, ignorée par le moteur : cet exemple n'en écrit aucune. |
| `escalation: { raison: human }` | Aucun outil ne rapporte aujourd'hui de raison d'escalade : cet exemple n'en écrit pas. Une politique Rego qui rend `escalate` ouvre bien une gate d'escalade. |

## Ce que le réseau du conteneur ne fait pas

Les étapes `mode: delegate` tournent dans un conteneur sans réseau par défaut, ce qui coupe aussi le
modèle. Pour un vrai agent, vous nommez un réseau Docker (`runner_network`) que **vous** réglez
(pare-feu, proxy) pour joindre la passerelle du modèle. ASAC ne filtre pas par domaine et n'audite
pas les refus réseau sous Docker. Voir `docs/guides/delegate.md`.
