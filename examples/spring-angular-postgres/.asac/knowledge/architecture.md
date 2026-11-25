# Architecture

Trois blocs : `backend/` (Spring Boot, expose `/api/**`), `frontend/` (Angular, appelle l'API) et
`backend/src/main/resources/db/migration/` (Flyway). Le contrat entre le front et le back est
`openapi.yaml` ; le client Angular en est généré.
