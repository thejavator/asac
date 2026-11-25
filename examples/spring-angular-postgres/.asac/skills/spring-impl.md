# Implémentation backend (Java 21, Spring Boot 3, Maven)

Implémentez le contrat d'API de `SPEC.md` dans `backend/`.

- Architecture en couches : `controller` → `service` → `repository` (Spring Data JPA).
- Un test JUnit 5 par critère d'acceptation, plus un test d'intégration avec Testcontainers
  (PostgreSQL) pour chaque repository.
- Validez les entrées avec Bean Validation ; ne renvoyez jamais d'entité JPA directement : un DTO.
- Mettez à jour `backend/src/main/resources/openapi.yaml` pour qu'il décrive exactement les routes.

Ne modifiez pas les migrations Flyway ni le dossier `frontend/`. Arrêtez-vous quand `mvn test` passe.
