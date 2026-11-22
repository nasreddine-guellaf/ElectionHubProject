# Authentification, permissions et validation — Phase 3

La clé de développement phase 2 est supprimée. Les routes métier acceptent exclusivement
`Authorization: Bearer <jeton>` obtenu via connexion. Les sessions durent une heure par
défaut (`SESSION_TTL_SECONDS`, entre 300 et 86400 secondes). Un jeton expiré ou révoqué
retourne 401 ; un rôle insuffisant retourne 403. Les réponses API ne doivent pas être mises en cache.

## Préparer les comptes fictifs

Depuis la racine, une fois PostgreSQL démarré et les dépendances locales installées :

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m app.seed_domain
..\.venv\Scripts\python.exe -m app.bootstrap_auth
Set-Location ..
```

Comptes : `demo-agent`, `demo-validator`, `demo-admin`. Les mots de passe initiaux aléatoires
sont sauvegardés dans `.local/demo-credentials.json`, exclu de Git et de Docker.
Ne pas partager ce fichier. Le bootstrap ne réinitialise pas un compte existant ; après
changement de mot de passe, le fichier initial n'est plus une référence de connexion à jour.
Le bootstrap ajoute aussi le citoyen fictif `DEMO-CIN-0001`, sans compte à mot de passe.

Sous WSL, utiliser `../.venv/bin/python` depuis `backend/`. Ne pas réutiliser le venv Windows.
Le bootstrap est prévu sur l'hôte : dans l'image non root, `/workspace/.local` n'est pas
un dossier de livraison des secrets. L'API Docker lit les mêmes comptes dans PostgreSQL.

## Connexion et déconnexion PowerShell

```powershell
$credentials = Get-Content .local/demo-credentials.json -Raw | ConvertFrom-Json
$body = @{ username = 'demo-agent'; password = $credentials.'demo-agent' } | ConvertTo-Json
$session = Invoke-RestMethod http://127.0.0.1:8000/api/v1/auth/login -Method Post -ContentType 'application/json' -Body $body
$headers = @{ Authorization = "Bearer $($session.access_token)" }
Invoke-RestMethod http://127.0.0.1:8000/api/v1/auth/me -Headers $headers
Invoke-RestMethod http://127.0.0.1:8000/api/v1/reports -Headers $headers
Invoke-RestMethod http://127.0.0.1:8000/api/v1/auth/logout -Method Post -Headers $headers
```

Ne pas imprimer `$body`, `$session` ou `$headers`. Dans Swagger `/docs`, se connecter puis
utiliser **Authorize** avec le jeton Bearer. Pas de jeton en URL. Aucun cookie de session
n'est créé ; le frontend futur gardera les jetons en mémoire, sans persistance en localStorage.

## Routes nouvelles

| Méthode | Route `/api/v1` | Accès / fonction |
|---|---|---|
| POST | `/auth/login` | Username et password ; retourne access_token, token_type, expires_at |
| GET | `/auth/me` | Session valide ; identité et rôle serveur |
| POST | `/auth/logout` | Session valide ; révoque ce jeton |
| POST | `/auth/password` | Mot de passe actuel et nouveau ; révoque toutes les sessions du compte |
| GET, POST | `/accounts` | ADMIN : liste / création de comptes opérationnels |
| PUT | `/accounts/{user_id}` | ADMIN : rôle unique et activation ; sessions révoquées |
| POST | `/accounts/{user_id}/password` | ADMIN : nouveau mot de passe d'un autre compte ; sessions révoquées |
| GET | `/audit` | ADMIN : événements de sécurité et changements de référentiels paginés |
| POST | `/reports/{id}/revisions/{number}/review` | VALIDATOR : démarrer la vérification humaine d'un PV soumis |
| POST | `/reports/{id}/revisions/{number}/decision` | VALIDATOR : APPROVED ou REJECTED ; motif pour rejet |
| POST | `/auth/citizen/request-otp` | Simulation optionnelle : demande avec CIN fictive |
| POST | `/auth/citizen/verify-otp` | challenge_id et code ; retourne une session citoyen |
| GET | `/citizen/polling-station` | CITIZEN : son bureau uniquement |

Les modèles Pydantic complets sont exposés dans OpenAPI. Mots de passe : 12 à 128 caractères.
Les usernames créés sont synthétiques et commencent par `demo-`. Les champs supplémentaires,
y compris rôles ou identités fournis lors d'une connexion, sont rejetés.

## Matrice des droits

| Opération | ADMIN | AGENT | VALIDATOR | CITIZEN |
|---|---|---|---|---|
| Référentiels de scrutin et candidats | Lire / gérer | Lire | Lire | Non |
| Bureaux inscrits à un scrutin | Tous | Ses affectations | Tous | Sa route dédiée |
| Comptes / rôles / audit | Gérer / lire | Non | Non | Non |
| Affectations | Gérer / lire toutes | Lire les siennes | Lire les siennes | Non |
| Dossiers PV / historique | Lire tous | Ses propres dossiers affectés | Dossiers dont la révision courante n'est pas DRAFT | Non |
| Créer / saisir / soumettre / corriger PV | Non | Auteur affecté | Non | Non |
| Démarrer revue / approuver / rejeter | Non | Non | Oui, jamais son propre dossier | Non |
| Publication | Non | Non | Non | Non |

Les lectures publiques héritées de `/polling-stations` restent un annuaire fictif sans
résultats ni identité citoyenne. Toute consultation des PV est protégée. Un dossier hors
du périmètre d'un agent répond 404, pour éviter de révéler son existence.
Les références avec plusieurs rôles ne peuvent pas s'authentifier dans ce MVP.

## Validation humaine

Un agent soumet le PV comme en phase 2 : statut SUBMITTED, `edit_version` incrémentée.
Le validateur appelle `.../review` avec `{"expected_version": 3}` dans l'exemple standard.
Le serveur recontrôle les résultats et passe à PENDING_VALIDATION, version 4.
Ensuite `.../decision` :

```json
{"expected_version": 4, "decision": "REJECTED", "reason": "Incohérence de la pièce fictive à corriger"}
```

Ou `{"expected_version": 4, "decision": "APPROVED"}`. L'approbation vérifie à nouveau
les totaux. Une seule décision par révision ; actions concurrentes ou versions obsolètes
retournent 409. L'agent peut corriger un rejet en créant une nouvelle révision, sans effacer
la décision. Une approbation n'est jamais une publication. En phase 3, la revue ne porte
que sur les données structurées : aucun document S3 ni traitement Lambda n'est simulé.

## OTP local optionnel

```powershell
python scripts/configure_otp.py --enable
docker compose up -d --force-recreate --wait api
```

Le script génère `OTP_HMAC_KEY` et active `CITIZEN_OTP_ENABLED`. Chaque réactivation
renouvelle le secret et invalide les anciens codes. `--disable` retire la clé et désactive
les demandes/vérifications après redémarrage. Les sessions déjà délivrées expirent normalement.

Demander un code avec `{"cin": "DEMO-CIN-0001"}`. La réponse 202 contient uniquement un
`challenge_id` et un message générique, même pour une référence inconnue. Le SMS fictif
est déposé dans `.local/sms/<challenge_id>.json` avec Uvicorn hôte, ou
`/tmp/electionhub-sms/<challenge_id>.json` dans le conteneur. Pour le lire localement :

```powershell
docker compose exec api cat /tmp/electionhub-sms/<challenge_id>.json
```

Remplacer `<challenge_id>` par l'identifiant reçu. Ce fichier est la boîte de réception
du simulateur, réservée au développeur ; ne pas l'exposer via HTTP ou le commiter. Il
contient volontairement le code lisible, comme un SMS, mais la base ne contient que son
HMAC. Aucun numéro réel, appel SNS, message externe ou frais SMS.

Soumettre ensuite `{"challenge_id": "…", "code": "…"}` à `/auth/citizen/verify-otp`.
Durée 5 minutes, 5 essais, usage unique, anciens défis invalidés à la nouvelle demande.
Les tentatives sont persistées même en cas de code incorrect.

## Limites d'essais et exploitation

Login : 5 tentatives par identifiant et 30 par IP sur 15 minutes, succès compris.
Demandes OTP : 3 par CIN et 30 par IP sur 5 minutes. Vérification OTP : 10 requêtes par
défi et 30 par IP sur 5 minutes, en plus des 5 essais internes au défi.
Réponse 429 et `Retry-After` à dépassement. Le backend utilise l'adresse du pair ; les
en-têtes de proxy non fiables ne doivent pas être utilisés pour contourner ces limites.
La configuration explicite des proxys de confiance sera traitée avant déploiement.
Les commandes Uvicorn fournies et l'image Docker utilisent `--no-proxy-headers` ;
le test HTTP autonome désactive aussi cette interprétation.

Sessions et limites sont stockées dans PostgreSQL, donc partagées entre processus.
Le nettoyage périodique des lignes expirées et fichiers SMS de simulation reste à préparer.
Le mode local/test n'est pas une autorisation de déploiement Internet ; TLS, gestion des
secrets cloud, récupération de mot de passe et protections de bordure restent planifiés.
