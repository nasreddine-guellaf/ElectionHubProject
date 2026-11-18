# API locale ElectionHub — Phase 2

**IMPLÉMENTÉ** : routes ci-dessous, schémas Pydantic, documentation `/docs` et `/openapi.json`.
Toutes les nouvelles routes exigent la clé de développement. Les anciennes routes GET
`/health` et `/api/v1/polling-stations[/<uuid>]` conservent leur accès local sans clé.

## Activation explicite

Depuis la racine, après initialisation `.env` et migration :

```powershell
docker compose exec api python -m app.seed_domain
python scripts/configure_dev_api.py --enable
docker compose up -d --force-recreate --wait api
```

Le script génère une nouvelle clé aléatoire dans `.env`, sans l'afficher, et sélectionne
l'agent fictif `30000000-0000-4000-8000-000000000001`. Chaque réactivation renouvelle la clé.
Le fichier `.env` reste exclu de Git. Charger la clé dans un client local sans la publier :

```powershell
$line = Get-Content .env | Where-Object { $_ -match '^DEV_API_KEY=' }
$headers = @{ 'X-Development-Key' = $line.Substring('DEV_API_KEY='.Length) }
Invoke-RestMethod http://127.0.0.1:8000/api/v1/elections -Headers $headers
Invoke-RestMethod http://127.0.0.1:8000/api/v1/reports -Headers $headers
```

Sous WSL, les scripts utilisent `python3.11` et les commandes Compose sont identiques.
Swagger affiche le paramètre `X-Development-Key` sur chaque opération métier. Ne pas
partager de capture contenant la clé. Aucun mot de passe ou jeton cloud n'est nécessaire.

Pour désactiver et supprimer la clé de `.env` :

```powershell
python scripts/configure_dev_api.py --disable
docker compose up -d --force-recreate --wait api
```

Ce mécanisme n'est ni un compte utilisateur ni du RBAC. Le serveur choisit l'acteur via
sa configuration et vérifie qu'il est actif. La création/modification d'un PV exige
l'affectation au bureau et la propriété du dossier. La clé donne aussi accès aux
référentiels et lectures du jeu fictif : elle n'est pas adaptée à plusieurs utilisateurs
ni à une exposition publique. Aucune route d'approbation/publication n'existe.

## Routes versionnées

Préfixe commun : `/api/v1`. Listes : `limit` 1–100, `offset` ≥ 0 ; réponse
`{items, total, limit, offset, data_kind: "synthetic"}`.

| Méthode | Route | Fonction |
|---|---|---|
| GET, POST | `/elections` | Liste / création de scrutin fictif |
| GET, PUT, DELETE | `/elections/{id}` | Lecture / remplacement / suppression si non référencé |
| GET, POST | `/candidates` | Liste / création de candidat ou liste fictive |
| GET | `/candidates/{id}` | Lecture individuelle |
| GET, POST | `/elections/{id}/candidates` | Participants / inscription d'un candidat |
| DELETE | `/elections/{id}/candidates/{candidate_id}` | Retrait avant premier dossier |
| GET, POST | `/elections/{id}/polling-stations` | Bureaux inscrits / inscription avec effectif |
| GET | `/user-references` | Références synthétiques, sans gestion de comptes |
| GET, POST | `/assignments` | Affectations / nouvelle affectation d'un agent déclaré |
| DELETE | `/assignments/{election_id}/{station_id}/{user_id}` | Retrait avant premier dossier |
| GET, POST | `/reports` | Dossiers / nouveau brouillon ; POST renvoie sa révision |
| GET | `/reports/{id}` | Dossier et numéro de révision courante |
| GET | `/reports/{id}/revisions` | Historique paginé des versions et résultats |
| GET | `/reports/{id}/revisions/{number}` | Version avec statut et résultats |
| PUT | `/reports/{id}/revisions/{number}/results` | Remplacement complet d'un brouillon |
| POST | `/reports/{id}/revisions/{number}/submit` | Contrôle puis soumission |
| POST | `/reports/{id}/revisions/{number}/revise` | Nouvelle correction avec motif obligatoire |
| GET | `/reports/{id}/history` | Événements, acteur et version d'édition |
| GET | `/reports/{id}/validations` | Décisions humaines éventuelles ; vide dans le seed phase 2 |

`GET /reports` accepte `election_id` et `polling_station_id` ; `GET /assignments`
accepte `election_id`. Les détails des schémas et champs requis sont dans OpenAPI.
Codes de références créées : `DEMO-` suivi de lettres ASCII majuscules, chiffres ou tirets.
Maximum 500 candidats par scrutin dans ce MVP.

## Exemple de parcours synthétique

Après le seed, le bureau DEMO-BV-003 reste disponible pour un nouveau dossier.
POST `/reports` :

```json
{
  "election_id": "10000000-0000-4000-8000-000000000001",
  "polling_station_id": "00000000-0000-4000-8000-000000000003"
}
```

La réponse 201 contient `report_id`, `revision_number: 1`, `status: "DRAFT"` et
`edit_version: 1`. Utiliser son `report_id` dans le PUT des résultats :

```json
{
  "expected_version": 1,
  "ballots_cast": 100,
  "valid_votes": 90,
  "blank_votes": 6,
  "invalid_votes": 4,
  "results": [
    {"candidate_id": "20000000-0000-4000-8000-000000000001", "votes": 40},
    {"candidate_id": "20000000-0000-4000-8000-000000000002", "votes": 30},
    {"candidate_id": "20000000-0000-4000-8000-000000000003", "votes": 20}
  ]
}
```

Le PUT renvoie `edit_version: 2`. POST `.../submit` avec `{"expected_version": 2}`
renvoie SUBMITTED, version 3. Le rapport demeure **non approuvé et non publié**.
POST `.../revise` avec `{"expected_version": 3, "reason": "Correction fictive de saisie"}`
crée la révision 2 en DRAFT, version d'édition 1. Les résultats antérieurs restent lisibles.
Le client doit toujours réutiliser la version renvoyée et recharger après un conflit.

## Erreurs et limites

| Code | Signification |
|---|---|
| 403 | Clé absente/incorrecte, acteur inactif/non affecté ou auteur différent |
| 404 | Référence, dossier ou révision absent |
| 409 | Doublon, état/version incorrect, référentiel figé ou référence encore utilisée |
| 422 | Champs invalides ou résultats incohérents |
| 503 | API métier désactivée ou PostgreSQL indisponible |

Format : `{"detail": "message français"}`. Aucun détail SQL, valeur secrète ou contenu
de requête invalidé n'est renvoyé. Une requête échouée ne conserve ni modification
partielle ni événement de succès. Aucune route générique de modification de statut.

**PLANIFIÉ** : authentification/RBAC phase 3, documents S3 et traitement Lambda phase 5,
validation humaine autorisée, publication et analytics dans leurs jalons respectifs.
La soumission phase 2 porte sur les résultats structurés ; elle ne prouve pas un dépôt
de document. Aucun téléversement de fichier ni faux événement S3 n'est simulé.
