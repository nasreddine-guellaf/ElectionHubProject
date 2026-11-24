# Vérifications phase 7 — préparation Azure hors ligne

Date : 24 novembre 2026. Cette recette ne couvre **aucun déploiement Azure**. Elle ne contient
que des essais réellement exécutés sur un poste Windows avec Docker Desktop (conteneurs Linux).

| Vérification | Résultat |
|---|---|
| `scripts/test_web_container.py` (8 tests de conteneur) | **8 réussis** |
| Compose complet reconstruit avec le nouveau modèle Nginx | PostgreSQL, API et web sains |
| Proxy `127.0.0.1:3000/api/v1/polling-stations` après changement | 200 |
| Tests backend | **117 réussis**, 1 avertissement de dépendance |
| Tests frontend | **19 réussis** |
| Ruff (`check` et `format --check`) | Réussis |
| `terraform fmt -check`, `init -backend=false`, `validate` sur `infra/azure` | Réussis (Terraform 1.17.2) |
| `terraform plan` sur `infra/azure` | **Non exécutable hors ligne** : le fournisseur exige `az login` |

Les 8 tests de conteneur couvrent : `/healthz`, repli React sur une route profonde, en-têtes de
sécurité (CSP, `nosniff`, `Referrer-Policy`, pas de version Nginx), proxy `/api/` avec l'en-tête
Host configuré, `503` JSON quand l'API est indisponible, comportement par défaut conservé pour
Compose, variables Nginx non substituées et exécution sans privilèges.

Un défaut a été trouvé et corrigé pendant les essais : monter `/etc/nginx/conf.d` en `tmpfs`
appartenant à `root` empêchait l'utilisateur Nginx d'écrire la configuration rendue ; le montage
fixe maintenant `uid=101,gid=101`.

## Matrice de recette à exécuter après déploiement (non exécutée)

| Cas | Attendu |
|---|---|
| Connexion citoyen, agent, administrateur, validateur | chaque profil voit seulement ses écrans |
| Téléversement puis téléchargement d'une pièce (agent auteur) | 201 puis contenu identique |
| Téléchargement par un validateur | autorisé selon le RBAC du PV |
| Session expirée | retour à la connexion sans donnée affichée |
| API arrêtée | message d'erreur lisible, portail toujours servi |
| Rechargement direct d'une route React profonde | page servie, pas de 404 |
| HTTP simple | redirigé ou refusé (HTTPS uniquement) |
| Inspection du bundle et des `app_settings` | aucun secret |
