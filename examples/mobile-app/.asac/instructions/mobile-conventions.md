# Conventions mobile

- Aucune chaîne en dur dans un widget : tout passe par `AppLocalizations`.
- Pas de `print` : le journal passe par `package:logging`.
- Un écran fonctionne hors ligne ou dit clairement pourquoi il ne le peut pas.
- Cibles tactiles : 44 pt (iOS) / 48 dp (Android) au minimum.
