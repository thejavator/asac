# Implémentation frontend (Angular)

Implémentez l'écran décrit dans `SPEC.md` dans `frontend/`.

- Composants autonomes (standalone), signaux pour l'état local, `HttpClient` pour les appels.
- Le client d'API est généré depuis `backend/src/main/resources/openapi.yaml` : ne l'écrivez pas à
  la main, lancez `npm run generate:api`.
- Un test Jest par critère d'acceptation qui concerne l'écran.

Ne modifiez pas `backend/`. Arrêtez-vous quand `npm test` passe.
