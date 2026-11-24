# AWS-3 — Terraform, IAM et préparation RDS

Date de vérification : 23 novembre 2026. Aucun composant n'a été provisionné pendant cette
préparation et le bucket existant n'a pas été modifié.

## Compte et capacités vérifiées

- compte `FREE` actif, région imposée `eu-north-1` ;
- 100 USD de crédits restants, expiration annoncée le 22 mai 2027 ;
- RDS, IAM et VPC accessibles par les API en lecture ;
- aucun RDS existant ; quotas : 40 instances RDS, 50 groupes de sous-réseaux et 5 VPC ;
- PostgreSQL 16.15 et `db.t4g.micro` disponibles dans la région ;
- trois sous-réseaux existent dans le VPC par défaut, mais le plan utilise un VPC dédié ;
- Terraform n'est pas installé localement. Il pourra utiliser le profil temporaire
  `electionhub-demo`, mais les opérations de création ne seront prouvées qu'après un plan
  validé puis une autorisation explicite d'appliquer.

La configuration a été validée avec Terraform 1.17.2 et le provider AWS 6.73.0 depuis
un binaire temporaire officiel dont le SHA-256 a été vérifié. Le plan S3 réel annonce
**6 imports, 0 création, 0 modification et 0 destruction**. Le plan privé IAM/VPC/RDS
annonce **6 imports et 14 créations, 0 modification et 0 destruction**. Aucun plan n'a
été appliqué et aucun fichier d'état n'a été créé.

Le rôle humain `managed/AccountFullAccessRole` possède `AdministratorAccess`. Il reste un
rôle d'administration et de bootstrap ; il ne doit plus être utilisé comme identité
d'exécution de l'application.

## Configuration RDS la moins chère retenue

| Élément | Choix |
|---|---|
| Moteur | PostgreSQL 16.15, cohérent avec PostgreSQL 16 local |
| Classe | `db.t4g.micro`, 2 vCPU burstables et 1 Gio RAM |
| Disponibilité | Single-AZ |
| Stockage | 20 Gio gp3, chiffré, sans autoscaling |
| Sauvegardes | 1 jour ; stockage gratuit jusqu'au volume provisionné total de la région |
| Observabilité payante | Performance Insights désactivé, enhanced monitoring désactivé |
| TLS | `rds.force_ssl=1`, CA `rds-ca-rsa2048-g1`, client `verify-full` |
| Protection | suppression protégée et snapshot final requis |

Estimation à 730 heures par mois, hors taxes et transferts :

- instance : `730 × 0,016 USD` = **11,68 USD/mois** ;
- stockage : `20 × 0,12 USD` = **2,40 USD/mois** ;
- base privée minimale : **14,08 USD/mois** ;
- secret maître géré par RDS/Secrets Manager : environ **0,40 USD/mois** hors appels ;
- endpoint public filtré : ajouter une IPv4 à `0,005 USD/heure`, soit **3,65 USD/mois** ;
- cible publique filtrée avec secret géré : environ **18,13 USD/mois**, plus trafic,
  journaux, snapshots excédentaires et taxes éventuelles.

Les crédits couvrent ces frais tant qu'ils restent disponibles, mais ils sont partagés avec
les autres services AWS. Une base arrêtée conserve des coûts de stockage et de sauvegarde.

## Réseau et dépendance GCP

Le compte simplifié ne permet pas AWS Site-to-Site VPN. Deux options restent donc ouvertes :

1. garder RDS privé jusqu'à la préparation d'une connectivité autorisée ; cette option est
   la plus sûre mais l'API GCP ne pourra pas encore s'y connecter ;
2. pour la démonstration multi-cloud, activer un endpoint RDS public uniquement après avoir
   réservé une IPv4 de sortie GCP fixe, puis autoriser exactement son `/32` dans le groupe
   de sécurité et imposer TLS `verify-full`.

Le plan Terraform choisit l'option 1 par défaut. Il refuse une base publique sans CIDR et
refuse les CIDR universels.

## IAM à privilèges minimaux

`ElectionHubApplicationRole` remplace le rôle administrateur pour le processus applicatif :

- confiance initiale limitée au rôle humain géré, uniquement pour `sts:AssumeRole` pendant
  le développement local ;
- lecture de la localisation du bucket et gestion multipart minimale ;
- `GetObject`, `PutObject`, `DeleteObject`, `AbortMultipartUpload` et
  `ListMultipartUploadParts` limités à `reports/*` ;
- `PutObject` autorisé seulement avec `AES256` ;
- aucun droit IAM, VPC, RDS control plane, suppression de bucket ou lecture d'autres objets.

En phase GCP, la confiance locale sera remplacée par une fédération OIDC ciblant une seule
identité de service GCP. Le rôle d'exécution Lambda PV sera distinct du rôle API. L'accès SQL
sera accordé dans PostgreSQL à un utilisateur applicatif sans droits de propriétaire ; le
secret maître ne sera jamais fourni à FastAPI.

## Changements backend AWS-4A

AWS-4A est implémenté localement : `POSTGRES_SSLMODE`, `POSTGRES_SSLROOTCERT`, les délais
et le pool sont typés ; RDS/cloud exige `verify-full` et une CA analysable ; Psycopg reçoit
les paramètres TLS ; `pool_pre_ping`, `pool_size`, `max_overflow` et `pool_recycle` sont
bornés et testés. Le workflow local PostgreSQL 16/Alembic reste fonctionnel.

Restent à effectuer après provisionnement : monter le bundle CA AWS, injecter le secret de
l'utilisateur applicatif depuis GCP Secret Manager, tester le vrai certificat RDS, exécuter
Alembic sur une base vide et prouver la restauration avant toute migration synthétique.

## Risques et gardes-fous

- **Coût** : RDS facture tant qu'il est disponible ; aucun `apply` avant budget accepté.
- **Connectivité** : RDS privé n'est pas accessible depuis GCP sans chemin réseau ; un
  endpoint public exige une sortie GCP fixe et une règle `/32`.
- **État Terraform** : l'import n'existe qu'après `apply` ; vérifier que le plan S3 contient
  des imports sans mise à jour ni destruction. `prevent_destroy` protège chaque ressource S3.
- **Secrets** : le rôle administrateur et le compte maître DB ne sont pas des identités
  applicatives.
- **Capacité** : 1 Gio de RAM convient à une démonstration, pas à une charge de production.
- **Disponibilité** : Single-AZ est économique mais accepte une interruption pendant une
  panne ou maintenance ; Multi-AZ est reporté car son coût est supérieur.
- **Crédits** : les 100 USD sont temporaires et partagés ; l'expiration du compte gratuit
  précède une exploitation durable.

## Ordre d'implémentation exact

1. Installer Terraform, exécuter `init`, `fmt -check` et `validate`.
2. Générer le plan d'import S3 avec `enable_new_resources=false` ; exiger zéro changement
   distant et ne pas appliquer sans nouvelle autorisation.
3. Générer séparément le plan IAM/VPC/RDS avec `enable_new_resources=true`, toujours sans
   appliquer, et comparer son coût au budget AWS.
4. ~~Implémenter et tester le support TLS RDS dans FastAPI.~~ Terminé dans AWS-4A ; la
   qualification contre une instance RDS réelle reste bloquée jusqu'au provisionnement.
5. Choisir la connectivité GCP : privée si le compte évolue, sinon IPv4 fixe + `/32`.
6. Après approbation explicite seulement : importer S3 dans l'état, créer le rôle applicatif,
   le VPC et RDS, créer l'utilisateur SQL applicatif, exécuter Alembic sur une base vide.
7. Effectuer une sauvegarde/restauration de données synthétiques avant toute migration.
