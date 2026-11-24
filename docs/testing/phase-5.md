# Vérifications phase 5 — stockage local et Amazon S3

Date : 23 novembre 2026. Cette recette couvre le socle logiciel et la qualification réelle
de l'adaptateur Amazon S3 dans la région `eu-north-1`.

| Vérification | Résultat |
|---|---|
| Tests documentaires backend | **8 tests réussis** |
| Suite backend complète | **127 tests réussis**, 2 avertissements de dépendances |
| Tests Lambda PV | **10 tests réussis** : doublon, intégrité, reprise et validation d'événement |
| Artefact Lambda Linux | import réel de psycopg 3.3.9 et Boto3 1.44.9 en conteneur réussi |
| Tests frontend | **19 tests réussis** après ajout du scénario multipart |
| Build TypeScript/Vite | Réussi |
| Ruff et contrôle de format | Réussis |
| Migration `0004_private_documents` | Appliquée localement |
| `alembic check` | Aucun changement de schéma manquant |
| Stack Docker | PostgreSQL, API et web sains ; migration et initialisation du volume terminées avec code 0 |
| Smoke test via `127.0.0.1:3000` | Dépôt 201, téléchargement 200, contenu identique, suppression 204 |
| Authentification Boto3 | Compte attendu et profil temporaire `electionhub-demo` validés |
| Configuration du bucket | Région correcte, SSE-S3, versioning, blocage public complet, `BucketOwnerEnforced` et refus du transport non TLS |
| Smoke test S3 via l'API | Dépôt 201, lecture 200, SHA-256 identique, suppression 204 |
| Nettoyage du test S3 | Delete marker et version temporaire ciblés puis purgés ; aucune donnée existante supprimée |

Les tests couvrent dépôt, empreinte, métadonnées non sensibles, téléchargement privé,
suppression, permissions, immutabilité après soumission, conservation par révision, taille, type MIME, signature de
contenu, assainissement du nom et rejet des traversées de chemin. Le test frontend vérifie
l'envoi `multipart/form-data` et la version optimiste du PV.

Le smoke test Docker crée un PDF synthétique en mémoire, le dépose avec la session de
l'agent de démonstration, le relit derrière le proxy, compare les octets puis le supprime.
Le volume reste privé et inscriptible uniquement après l'initialisation de ses permissions
pour l'utilisateur non privilégié de l'API.

L'adaptateur S3 est maintenant qualifié contre le compte AWS de démonstration. La dépendance
`botocore[crt]` permet à Boto3 de consommer les identifiants temporaires créés par
`aws login`. Lambda PV est préparée et testée hors AWS, avec un plan non appliqué ; sa qualification
réelle dépend encore de RDS. Lambda OTP, SNS, les incidents et les tests de reprise déployés restent
à faire. Les avertissements proviennent de dépendances de test ; aucun test n'échoue.
