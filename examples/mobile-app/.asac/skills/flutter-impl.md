# Implémentation Flutter

Implémentez `DESIGN.md` et `SPEC.md` dans `lib/` et `test/`.

- État : Riverpod. Navigation : go_router. Pas d'accès réseau dans un widget : un repository.
- Un test de widget par état décrit dans `DESIGN.md`, un test d'intégration par critère d'acceptation.
- Chaque élément interactif a un `Semantics(label: …)` ou un `tooltip`.
- N'ajoutez aucune permission dans `AndroidManifest.xml` ni `Info.plist` : demandez-la dans `SPEC.md`.
- Vous avez le serveur MCP `dart` : utilisez son analyse plutôt que de deviner.

Arrêtez-vous quand `flutter analyze` et `flutter test` passent.
