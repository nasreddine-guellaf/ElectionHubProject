# Phase 7 — Préparation du déploiement Azure (hors ligne)

Date : 24 novembre 2026. Cette tranche prépare le frontend pour un **unique Azure App
Service** sans créer de ressource Azure, sans exécuter `terraform apply` et sans identifiant
cloud. Elle ne marque pas la phase 7 comme terminée.

## Principe

Le portail citoyen/agent et le back-office forment **une seule application React** servie par
Nginx. Le navigateur appelle toujours `/api/v1` sur **la même origine** ; Nginx relaie `/api/`
vers le backend FastAPI. Avantages : pas de CORS, CSP `connect-src 'self'` conservée, l'URL du
backend n'est jamais compilée dans le bundle JavaScript, et FastAPI reste l'unique autorité
d'accès (les rôles ne sont pas décidés côté Azure).

```text
Navigateur ── HTTPS ──> Azure App Service (Nginx + React) ── HTTPS /api/ ──> API GCP (FastAPI)
```

## Upstream configurable

`frontend/nginx.conf.template` est rendu au démarrage par l'entrypoint de l'image Nginx
(`envsubst`). Seules les variables `API_*` sont substituées (`NGINX_ENVSUBST_FILTER=^API_`),
donc `$host`, `$uri`… restent des variables Nginx.

| Variable | Défaut (Compose local) | Cible Azure |
|---|---|---|
| `API_UPSTREAM` | `http://api:8000` | URL HTTPS stable de l'API GCP, sans chemin |
| `API_HOST_HEADER` | `$host` | nom d'hôte de l'API, sans schéma |

Comportements ajoutés :

- si l'amont est en HTTPS, Nginx envoie le SNI et **vérifie le certificat** (bundle CA du système) ;
- si l'API est injoignable (502/503/504), `/api/` répond `503` avec `{"detail":"API indisponible."}`
  tandis que le portail et `/healthz` restent servis ;
- l'en-tête `X-Forwarded-For` du client n'est toujours pas relayé.

Compose monte `/etc/nginx/conf.d` en `tmpfs` (propriétaire `101:101`) pour que le conteneur
reste en lecture seule : le fichier rendu est écrit en mémoire, jamais dans l'image.

Limite connue : Nginx résout le nom de l'amont **au démarrage**. Si le DNS de l'API n'est pas
encore résolvable, le conteneur s'arrête avec `host not found in upstream`. Le nom GCP doit
donc exister avant le démarrage du Web App.

## Terraform `infra/azure/`

Un seul `azurerm_linux_web_app` Linux conteneurisé, son plan App Service, un espace Log
Analytics et des journaux de diagnostic. Réglages de sécurité : HTTPS uniquement, TLS ≥ 1.2,
FTPS désactivé, identité managée, sonde `/healthz`, aucun secret dans `app_settings`.

Garde-fou identique à AWS : `enable_new_resources = false` par défaut, donc un plan ne crée
rien. `subscription_id` est obligatoire, la région et le SKU sont des variables, et le tag
d'image `latest` est refusé.

```powershell
Set-Location infra/azure
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
```

`terraform plan` exige une connexion Azure (`az login`) même sans ressource à créer : il n'a
pas pu être exécuté hors ligne. Après autorisation :

```powershell
terraform plan -var-file=terraform.tfvars -var "enable_new_resources=true"
```

## Construire et publier l'image (après décision sur le registre)

```powershell
docker build -t <registre>/electionhub/web:<version> ./frontend
docker push <registre>/electionhub/web:<version>
```

Deux options de registre : Azure Container Registry (renseigner `acr_resource_id` pour que
l'identité du Web App reçoive `AcrPull`) ou un registre public/privé externe. Aucun choix n'a
été fait.

## Rollback et suppression

- Retour arrière : redéployer le tag d'image précédent (`container_image_tag`) puis `apply`.
- Suppression complète : supprimer le groupe de ressources `rg-electionhub-demo-web` (sortie
  `resource_group_name`) ou `terraform destroy`. Le groupe ne contient que cette phase.

## Abonnement vérifié (lecture seule, 24 novembre 2026)

Abonnement **Azure for Students**, état `Enabled`, locataire de l'école. Constats :

- La politique « Allowed resource deployment regions » n'autorise que `austriaeast`,
  `denmarkeast`, `polandcentral`, `germanywestcentral` et `francecentral`. La région par défaut
  initiale (`swedencentral`) était refusée ; le défaut est maintenant `francecentral`.
- Les fournisseurs `Microsoft.Web`, `Microsoft.OperationalInsights` et `Microsoft.Insights`
  n'étaient pas enregistrés. Comme `versions.tf` désactive l'enregistrement automatique, ils ont
  été enregistrés à la main (`az provider register`), avec l'accord du propriétaire du compte.
- Non vérifié : disponibilité du SKU `B1` et des quotas App Service sur cet abonnement ; à
  contrôler au premier `terraform plan` réel ou en cas d'erreur de quota.

## Dépendances à obtenir avant un déploiement

Budget, registre d'images, domaine et DNS éventuels, identité autorisée à lire l'image et
**URL HTTPS stable de l'API GCP** (donc dépend de la phase 6).
