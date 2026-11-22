# Vérifications phase 5 — tranche stockage local

Date : 22 novembre 2026. Cette recette couvre le socle logiciel de la phase 5, pas un
déploiement AWS réel.

| Vérification | Résultat |
|---|---|
| Tests documentaires backend | **8 tests réussis** |
| Suite backend complète | **107 tests réussis**, 2 avertissements de dépendances |
| Tests frontend | **19 tests réussis** après ajout du scénario multipart |
| Build TypeScript/Vite | Réussi |
| Ruff et contrôle de format | Réussis |
| Migration `0004_private_documents` | Appliquée localement |
| `alembic check` | Aucun changement de schéma manquant |
| Stack Docker | PostgreSQL, API et web sains ; migration et initialisation du volume terminées avec code 0 |
| Smoke test via `127.0.0.1:3000` | Dépôt 201, téléchargement 200, contenu identique, suppression 204 |

Les tests couvrent dépôt, empreinte, métadonnées non sensibles, téléchargement privé,
suppression, permissions, immutabilité après soumission, conservation par révision, taille, type MIME, signature de
contenu, assainissement du nom et rejet des traversées de chemin. Le test frontend vérifie
l'envoi `multipart/form-data` et la version optimiste du PV.

Le smoke test Docker crée un PDF synthétique en mémoire, le dépose avec la session de
l'agent de démonstration, le relit derrière le proxy, compare les octets puis le supprime.
Le volume reste privé et inscriptible uniquement après l'initialisation de ses permissions
pour l'utilisateur non privilégié de l'API.

Limite actuelle : l'adaptateur S3 est implémenté mais n'est pas qualifié contre un compte
AWS. Lambda PV, RDS, Lambda OTP, SNS, les incidents et les tests de reprise restent à faire.
Les avertissements observés proviennent de la dépréciation du client de test Starlette et
d'un attribut de schéma Pydantic sans effet pendant un test concurrent ; aucun test n'échoue.
