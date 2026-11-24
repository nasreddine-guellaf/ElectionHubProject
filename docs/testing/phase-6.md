# Vérifications phase 6 — préparation GCP hors ligne

Date : 24 novembre 2026. Aucun déploiement GCP n'a été fait. Seuls les essais réellement
exécutés sur un poste Windows avec Docker Desktop et Terraform 1.17.2 sont listés.

| Vérification | Résultat |
|---|---|
| `scripts/test_api_container.py` (6 tests de conteneur) | **6 réussis** |
| `terraform fmt -check`, `init -backend=false`, `validate` sur `infra/gcp` | Réussis |
| `terraform plan` avec jeton factice, `enable_new_resources=true` | 36 ressources à créer, 0 modification, 0 suppression |
| Modèle de démarrage rendu puis `bash -n` | Syntaxe valide, aucun marqueur de modèle restant |
| `migrate.sh --dry-run` et refus du tag `latest` | Conformes |
| Tests backend / frontend, première exécution (phase 7) | 117 / 19 réussis |
| Après fusion avec `main` (incidents, Lambda PV) et correction SEC-02 | backend **135 réussis**, frontend **20 réussis**, Ruff OK ; conteneurs web 8/8 et API 6/6 |
| Test de régression SEC-02 `test_health_reports_cloud_environment` | échoue sans la correction (erreur de validation pydantic), réussit avec |
| `terraform plan` réel, `apply`, démarrage d'une VM, LB, accès RDS, accès S3 | **Non exécutés** : pas de compte GCP |

Les 6 tests de conteneur couvrent : refus de démarrer en mode cloud sans bundle CA ou avec un
TLS plus faible que `verify-full` (sans fuite du mot de passe dans les journaux), sonde de vie
`200` malgré une base injoignable pendant que `/health` répond `503`, exécution sans privilèges
et système de fichiers en lecture seule, nombre de workers piloté par `UVICORN_WORKERS`, et
absence de `.env`, certificats ou clés dans l'image.

Limites : `shellcheck` n'était pas installé, donc le script de démarrage n'a été vérifié que par
`bash -n` ; il n'a jamais tourné sur une VM Debian réelle.

## À exécuter après obtention d'un projet GCP (non exécuté)

| Cas | Attendu |
|---|---|
| Démarrage d'une instance | `electionhub-api.service` actif, journal de démarrage sans erreur |
| `/health` via le LB en HTTPS | 200, `environment: cloud`, schéma `0005_incidents` (version attendue par le code) |
| HTTP clair | redirection 301 |
| Instance arrêtée | remplacée par le MIG, trafic maintenu |
| Parcours métier contre RDS en `verify-full` | succès ; échec si la CA est retirée |
| Téléversement de pièce vers S3 | 201, identifiants temporaires seulement |
| Recherche de secrets dans la config des VM et les journaux | aucun |
