# Phase 6 — Préparation du backend sur GCP (hors ligne)

Date : 24 novembre 2026. Cette tranche prépare l'API FastAPI pour Compute Engine **sans créer
de ressource GCP, sans `terraform apply` et sans identifiant cloud**. La phase 6 n'est pas
terminée : elle ne le sera qu'après un test réel contre RDS et S3.

## Architecture cible

```text
Azure (Nginx) ─HTTPS─> Load Balancer HTTPS global ─> MIG régional (1 à 2 VM Debian, sans IP publique)
                                                        │ conteneur API non privilégié
                                                        ├─ TLS verify-full ─> RDS PostgreSQL (AWS)   via Cloud NAT, IPv4 fixe
                                                        └─ jeton OIDC Google ─> AssumeRole AWS ─> S3 (identifiants temporaires)
```

| Besoin | Choix | Pourquoi |
|---|---|---|
| Exécution | Debian 12 + Docker, un conteneur systemd | image identique à Compose, simple à expliquer et à déboguer |
| Mise à l'échelle | MIG régional + autoscaler CPU 60 %, 1 à 2 instances | tolérance à la perte d'une zone, coût borné |
| Entrée | LB HTTPS global, certificat géré, TLS ≥ 1.2, HTTP → 301 vers HTTPS | une seule IP publique, pas d'IP sur les VM |
| Sortie | Cloud NAT avec **IPv4 réservée** | RDS public filtré sur un seul `/32` (repli pédagogique) |
| Secrets | Secret Manager lu avec l'identité de l'instance | rien dans l'image, le dépôt, les métadonnées ou Terraform |
| Accès S3 | OIDC Google puis `AssumeRole` AWS | aucune clé AWS durable côté GCP |

## Secrets : comment ils circulent

Terraform crée deux **conteneurs de secret vides** (`electionhub-postgres-password`,
`electionhub-rds-ca-bundle`). Les valeurs sont ajoutées à la main, hors Terraform :

```powershell
# Mot de passe de l'utilisateur SQL applicatif (jamais le propriétaire de la base)
gcloud secrets versions add electionhub-postgres-password --data-file=-
# Bundle CA public AWS RDS (téléchargé depuis la page officielle AWS)
gcloud secrets versions add electionhub-rds-ca-bundle --data-file=global-bundle.pem
```

Au démarrage, `infra/gcp/startup/startup.sh.tftpl` lit les secrets avec le compte de service de
l'instance, écrit un fichier d'environnement en `0600` sous `/run` (mémoire, perdu à l'arrêt) et
monte la CA en lecture seule. Le script s'arrête si un secret est vide ou si la CA n'est pas un
certificat.

Le compte de service n'a que : lecture de **ces deux secrets**, lecture du dépôt d'images,
écriture des journaux et des métriques.

## Migration unique

Les instances ne lancent **jamais** Alembic : plusieurs VM démarrant ensemble migreraient en
concurrence. La migration est une étape explicite, exécutée une fois par version, avant le
déploiement de la nouvelle image :

```bash
PROJECT_ID=... REGION=europe-north1 IMAGE_TAG=0.1.0 RDS_HOST=...rds.amazonaws.com \
RDS_CA_FILE=./global-bundle.pem ./infra/gcp/scripts/migrate.sh --dry-run   # puis sans --dry-run
```

La sonde `/health` compare la version Alembic à celle attendue par le code : une instance dont la
base n'est pas migrée répond 503 et ne reçoit pas de trafic.

## Deux sondes, deux rôles

- **Vie** (`/openapi.json`, auto-réparation du MIG) : ne touche pas la base. Une panne RDS ne
  doit pas faire recréer toutes les VM en boucle.
- **Disponibilité** (`/health`, load balancer) : vérifie la base et la migration.

## Budget de connexions RDS

```text
connexions maximales = max_replicas × workers × (POSTGRES_POOL_SIZE + POSTGRES_MAX_OVERFLOW)
                     = 2 × 1 × (5 + 5) = 20   (valeurs par défaut)
```

La sortie Terraform `max_db_connections` le calcule. À comparer à `SHOW max_connections` sur RDS
(de l'ordre de 80 à 110 pour `db.t4g.micro`, à vérifier) en gardant une marge pour Alembic, les
Lambda et l'administration. `UVICORN_WORKERS` règle le nombre de workers (testé : 2 workers
démarrent bien).

## Connectivité GCP → RDS

**Décision ouverte, non résolue.** Depuis AWS-4B (24 novembre 2026), RDS est forcé en **privé**
(`publicly_accessible = false`, aucune route Internet) et le compte AWS simplifié n'autorise pas
de VPN site à site. La feuille de route traite « GCP → RDS » comme un chantier distinct : aucun
chemin n'existe aujourd'hui entre les VM GCP et la base. Tant qu'il n'est pas tranché, l'API GCP
ne peut pas atteindre RDS et le déploiement réel de la phase 6 reste bloqué.

Pistes à discuter avec Nasr (aucune n'est implémentée ici) :

1. **Endpoint public filtré** : ancien repli de ce document. `terraform output nat_egress_ipv4`,
   puis n'autoriser que `<ip>/32` dans le groupe de sécurité RDS avec TLS `verify-full`,
   jamais `0.0.0.0/0`. Contredit le choix actuel « RDS privé » d'AWS-4B : demande une
   décision explicite et un changement côté `infra/aws`.
2. **Service intermédiaire privé en AWS** qui possède l'accès SQL, et que l'API GCP appelle
   en HTTPS authentifié. Nouveau contrat, nouveau coût, plus de code.
3. **Autre moyen de liaison inter-cloud** si le compte AWS évolue (VPN, interconnexion).

La partie GCP de ce lot (NAT à IPv4 fixe, secrets, TLS `verify-full`) reste valable pour les
pistes 1 et 3.

## Identité inter-cloud pour S3

Chaque instance produit un jeton OIDC Google (audience configurable) renouvelé toutes les
10 minutes dans un répertoire monté en lecture seule. L'API utilise la chaîne d'identifiants
standard du SDK (`AWS_ROLE_ARN`, `AWS_WEB_IDENTITY_TOKEN_FILE`) : aucune modification du code.

Côté AWS (lot de Nasr, **non fait et non testé**) : fournisseur d'identité Google, rôle limité à
`reports/*` avec chiffrement obligatoire, et condition de confiance sur le `sub` du jeton =
`terraform output service_account_unique_id`. Le jeton dure une heure.

## Point à trancher avant tout déploiement : l'adresse IP du client

La limitation d'essais (`throttle` dans `security.py`) compte par `request.client.host`, et
l'API tourne avec `--no-proxy-headers`. Derrière Cloudflare, Nginx Azure et le load balancer GCP,
FastAPI verra donc **l'adresse du load balancer** et non celle de l'utilisateur : le plafond
« 30 tentatives par IP » deviendrait **partagé par tous les utilisateurs** (30 connexions
échouées ou réussies en 15 minutes bloqueraient tout le monde). Nginx vide aussi
`X-Forwarded-For`, ce qui est sûr mais perd l'information.

Pistes, à décider avec Nasr car cela touche la sécurité du backend : faire relayer l'IP par la
chaîne de confiance (Cloudflare → Nginx → LB) puis configurer uvicorn avec
`--proxy-headers --forwarded-allow-ips=<plages du LB>` et un test dédié ; ou limiter par compte
seulement et traiter la protection par IP au bord (Cloudflare, phase 9). Rien n'a été modifié.

## Hypothèses non vérifiées (aucun accès GCP/AWS disponible)

- `gcloud` est préinstallé sur l'image Debian 12 de Compute Engine.
- Les paquets Debian `docker.io` suffisent pour ce conteneur.
- AWS accepte le jeton d'identité Google avec l'audience choisie ; à valider avec le rôle réel.
- Le certificat géré ne devient actif qu'après le DNS A vers `lb_ip_address` (délai possible).
- Quotas, région et facturation du projet.

## Validation hors ligne (voir `docs/testing/phase-6.md`)

```powershell
Set-Location infra/gcp
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
```

`terraform plan` exige des identifiants GCP. Un plan avec un **jeton factice** a servi à vérifier
le rendu du modèle et le graphe de ressources sans contacter de projet réel.

## Rollback et nettoyage

- Retour arrière applicatif : changer `api_image_tag` vers la version précédente (mise à jour
  progressive du MIG, sans indisponibilité). Si la migration n'est pas rétrocompatible, restaurer
  la base d'abord.
- Suppression : `terraform destroy` (les secrets et l'IP réservée sont supprimés avec) puis
  supprimer à la main les versions de secret et le projet de test si nécessaire.

## Dépendances à demander avant un déploiement

Identifiant et région du projet GCP, compte de facturation, budget, rôles autorisés, domaine et
DNS, choix de connectivité, endpoint RDS, utilisateur SQL applicatif et son secret, bundle CA,
rôle AWS fédéré pour S3.
