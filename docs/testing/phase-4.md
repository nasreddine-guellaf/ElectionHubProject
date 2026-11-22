# Vérifications phase 4 — 22 novembre 2026

| Vérification | Résultat |
|---|---|
| `npm test` dans `frontend/` | **18 tests réussis** |
| `npm run build` | TypeScript valide, build Vite réussi |
| `npm audit` avec et sans dépendances de développement | **0 vulnérabilité connue** |
| `pytest -q` dans `backend/` | **98 tests réussis**, 1 avertissement Starlette, 65,63 s |
| Ruff sur `backend/` et `scripts/` | Réussite |
| `docker compose up -d --build --wait` | Web, API et PostgreSQL sains; migration terminée avec code 0 |
| HTTP via `http://127.0.0.1:3000` | SPA, route profonde, CSP, proxy API, trois rôles et logout réussis |
| `nginx -t` et vérification du répertoire web | Configuration valide, fichiers non inscriptibles |

Les tests frontend couvrent la redirection vers la connexion, une connexion refusée,
la navigation par rôle, l'absence de jeton dans les stockages navigateur, la création et
la saisie d'un PV, les équations de cohérence, la sauvegarde et la soumission, un conflit
409, la validation et le rejet motivé, la création de compte, OTP activé/désactivé, les
erreurs réseau, la reprise et la session expirée. Les corps d'appels réseau sont vérifiés.

Les tests backend ajoutent la gestion des bureaux par ADMIN, l'audit, les refus pour les
autres rôles, les validations d'entrée, la protection des bureaux utilisés et la
conservation de l'effectif figé d'un scrutin.

Un backend de recette isolé peut être lancé avec `scripts/serve_ui_test_api.py`. Il crée
un schéma PostgreSQL aléatoire, charge les données fictives, écoute uniquement sur
`127.0.0.1:8001`, puis supprime son propre schéma à l'arrêt.

La prévisualisation native n'a pas pu capturer d'images : le service de navigateur intégré
était indisponible, et la fenêtre Brave existante était utilisée par l'utilisateur. Elle
n'a pas été manipulée davantage. La disposition responsive a été vérifiée par les règles
CSS, le build et les tests DOM; une inspection visuelle manuelle desktop/mobile reste
recommandée avant la présentation académique.

Le seul avertissement Python provient de la dépréciation du client de test Starlette avec
`httpx`; aucun test n'échoue. Aucun test de charge, audit externe, déploiement Azure ou
stockage de fichiers n'est inclus.

**IMPLÉMENTÉ / TESTÉ :** application React locale unique et parcours opérationnels.
**PLANIFIÉ :** pièces S3, événements Lambda, SMS SNS et RDS en phase 5, puis GCP/Azure.
