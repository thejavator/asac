# Suivi des fonctionnalités v1

Un fichier par fonctionnalité de `asac-specs-v1.md` (§ 6), écrit quand elle est traitée. La
spec fait foi pour les critères ; ces fichiers disent **ce qui a été fait, avec quelle preuve, et
ce qui reste**.

## Règle de statut

| Statut | Sens |
|---|---|
| **Vérifiée** | Chaque critère a un test qui passe, et le test a été vu échouer sur une version fausse du code (mutation). Contrôle global vert. |
| **Partielle** | Certains critères sont vérifiés, d'autres non. Le fichier liste lesquels. |
| **Bloquée** | Un critère ne peut pas être tenu. Le fichier dit pourquoi (§ 8 de la spec : écart consigné). |
| **À faire** | Rien de livré. |

Un test avec un double (faux runner, faux harnais) reste un **test unitaire** : il ne fait pas
passer une fonctionnalité en « vérifiée » seul (spec § 8, « Vérité d'abord »).

## Tableau

Mis à jour à chaque commit de fonctionnalité.

| Fonctionnalité | Statut | Commit | Fichier |
|---|---|---|---|
| F63 | Vérifiée | `ae972dd` | [F63](F63.md) |
| F64 | Vérifiée | `804c8af` | [F64](F64.md) |
| F65 | Vérifiée | `804c8af` | [F65](F65.md) |
| F66 | Vérifiée | `804c8af` | [F66](F66.md) |
| F67 | Vérifiée | `a896951` | [F67](F67.md) |
| F68 | Vérifiée (lots A et B) | `0caaeae` | [F68](F68.md) |
| F58 | Vérifiée | `52f0fee` | [F58](F58.md) |
| F59 | Vérifiée | `52f0fee` | [F59](F59.md) |
| F60 | Vérifiée | voir `git log` | [F60](F60.md) |
| F61 | Vérifiée | voir `git log` | [F61](F61.md) |
| F57 | Vérifiée | voir `git log` | [F57](F57.md) |
| F62 | Vérifiée | voir `git log` | [F62](F62.md) |
| F69 | Vérifiée | voir `git log` | [F69](F69.md) |

## Demandes de modification de la spec

La spec est gelée : une modification s'écrit au § 17 avant d'être appliquée. Ce tableau liste ce que
le travail a fait apparaître. Une ligne passe au § 17 quand le porteur la décide.

| Date | Fonctionnalité | Écart | État |
|---|---|---|---|
| 2026-11-24 | F63 | F1 cite `ASAC001` à `ASAC027` : le code émet `ASAC028` | Prévu par F63, critère 4 |
