# AWS-4B — Plan contrôlé RDS PostgreSQL privé

Date de qualification : 24 novembre 2026. Cette tranche prépare le déploiement mais ne crée
aucune ressource, n'applique aucun plan, ne modifie pas S3 et ne migre aucune donnée.

## État vérifié du compte

Les contrôles ont utilisé le profil `electionhub-demo` et des API AWS en lecture seule.

| Contrôle | Résultat observé |
|---|---|
| Compte/région | compte projet `749251635900`, région imposée `eu-north-1` |
| Plan | `FREE`, `ACTIVE` |
| Crédits | `99.999782 USD` restants |
| Expiration du plan | `2027-05-22T22:47:16.654Z` |
| Coût estimé du mois | `0 USD` au moment du contrôle |
| Budget AWS Budgets | aucun budget configuré |
| RDS | 0 instance sur un quota de 40 ; 0 stockage sur 100 000 GiB |
| PostgreSQL | versions 16.11 à 16.15 disponibles ; 16.15 retenue |
| Configuration | `db.t4g.micro`, gp3 et chiffrement disponibles en Single-AZ |
| Certificat | `rds-ca-rsa2048-g1`, valide jusqu'en 2061 et rotation sans redémarrage prise en charge |
| Ressources existantes | aucun RDS, EC2 ou secret ; uniquement le VPC par défaut côté réseau |

RDS, EC2, VPC, IAM, Secrets Manager, SSM et les outils AWS font partie des services accessibles
au plan Free dans la nouvelle expérience AWS. La simulation IAM, exécutée avec le contexte
obligatoire `aws:RequestedRegion=eu-north-1`, autorise les créations nécessaires. Une simulation
sans ce contexte affiche à tort des refus explicites à cause de la politique régionale du compte.
Cela ne garantit pas qu'un futur `apply` réussira : seul un déploiement approuvé pourra confirmer
les dernières contraintes de capacité et de politique au moment choisi.

## Architecture préparée

- VPC dédié `10.40.0.0/16` ;
- deux sous-réseaux RDS isolés, `10.40.10.0/24` et `10.40.11.0/24`, dans deux AZ ;
- aucune route Internet, NAT Gateway ou IP publique dans les sous-réseaux de base de données ;
- RDS PostgreSQL 16.15, `db.t4g.micro`, Single-AZ, 20 GiB gp3 chiffrés ;
- endpoint RDS forcé à `publicly_accessible = false` ;
- groupe de sécurité RDS sans sortie et sans entrée lorsque le runner est absent ;
- paramètre `rds.force_ssl=1`, CA `rds-ca-rsa2048-g1`, sauvegardes automatiques sept jours ;
- mot de passe maître produit et conservé par RDS dans Secrets Manager ;
- conteneur de secret distinct pour le compte applicatif non propriétaire ;
- protection contre la suppression et snapshot final obligatoires.

Le runner est un lot séparé, désactivé par défaut. Lorsqu'il est approuvé, Terraform prépare une
instance Amazon Linux 2023 ARM `t4g.micro` dans un sous-réseau public de gestion. Elle n'a aucune
règle entrante ni clé SSH, exige IMDSv2 et n'est joignable que par SSM. Sa sortie est limitée à
HTTPS et PostgreSQL vers le groupe RDS. Le disque gp3 de 8 GiB est chiffré et supprimé avec
l'instance. Un arrêt programmé au bout de deux heures termine l'instance.

Le runner télécharge le bundle CA régional depuis le trust store AWS officiel, utilise
`verify-full`, vérifie `pg_stat_ssl`, exige l'échec de `sslmode=disable`, exécute Alembic avec un
compte migrateur séparé, puis désactive ce login. Le compte `electionhub_app` n'est ni superuser,
ni propriétaire, ni créateur de rôles/bases/tables. Il ne reçoit que les privilèges DML requis.

## Plans générés

Terraform 1.17.2 a été installé dans `.local/tools`, hors Git, après comparaison SHA-256 avec le
fichier officiel HashiCorp. Le provider verrouillé est `hashicorp/aws` 6.73.0.

| Plan ignoré localement | Imports | Ajouts | Modifications | Destructions |
|---|---:|---:|---:|---:|
| `aws4b-s3-only.tfplan` | 6 | 0 | 0 | 0 |
| `aws4b-private-rds.tfplan` | 6 | 13 | 0 | 0 |
| `aws4b-private-rds-runner.tfplan` | 6 | 27 | 0 | 0 |

Les six imports correspondent exclusivement au bucket existant et à ses contrôles déjà actifs.
Le plan S3 confirme **0 ajout, 0 modification et 0 destruction**. Aucun plan n'a été appliqué et
aucun fichier d'état n'a été créé. Les plans sauvegardés ne doivent jamais être appliqués après
expiration de la session : ils servent uniquement de preuve et doivent être régénérés.

Contrôles locaux effectués : `terraform fmt -recursive`, `terraform validate` et
`git diff --check` réussissent. Les trois plans ci-dessus ont été relus au format JSON : chacun
contient zéro mise à jour, zéro suppression et zéro mutation S3. Une vérification AWS finale
confirme toujours 0 RDS, 0 EC2 et 0 secret ; le bucket conserve le versioning, le chiffrement
`AES256` et les quatre blocages d'accès public. La syntaxe Bash n'a pas pu être exécutée sous
Windows car le shim Bash local était inaccessible ; les scripts ont donc été relus mais devront
passer `bash -n` sur le runner avant toute exécution. Les tests backend n'ont pas été relancés,
car AWS-4B ne modifie aucun code backend et les 117 tests d'AWS-4A étaient déjà verts.

## Estimation mensuelle hors crédits

Les tarifs ont été lus dans l'API AWS Price List pour Europe (Stockholm), le 24 novembre 2026.

| Élément | Calcul | Estimation USD |
|---|---:|---:|
| RDS `db.t4g.micro` | 730 h × 0,016 USD | 11,68/mois |
| RDS gp3 | 20 GiB × 0,12 USD | 2,40/mois |
| Secret maître RDS | 1 × 0,40 USD | 0,40/mois |
| Secret applicatif | 1 × 0,40 USD | 0,40/mois |
| Sauvegardes ≤ 20 GiB | allocation gratuite égale au stockage provisionné | 0,00 |
| VPC, sous-réseaux, groupes, IGW | pas de coût horaire direct | 0,00 |
| **Socle RDS estimé** | | **14,88 USD/mois** |

Un runner conservé deux heures coûte environ 0,0172 USD de calcul, 0,0100 USD d'IPv4 publique
et 0,0018 USD de disque gp3 proratisé, soit **environ 0,03 USD par session**, hors transfert
négligeable. Aucun NAT Gateway ni interface VPC Endpoint payante n'est prévu. Les secrets peuvent
bénéficier d'un essai initial, mais l'estimation retient leur tarif normal.

Les crédits actuels couvriraient théoriquement plus de six mois de ce seul socle, mais le plan
Free expire le 22 mai 2027 même s'il reste des crédits. Après expiration, le projet est suspendu
si le compte n'est pas converti. Il faut donc approuver soit la suppression avant cette date,
soit une mise à niveau maîtrisée du plan.

## Étapes exactes après approbation

1. Choisir le stockage de l'état Terraform. Recommandation : un backend S3 dédié à l'état avec
   verrouillage natif, distinct du bucket documentaire. La solution locale n'est acceptable que
   temporairement sur un poste chiffré et sauvegardé. Le bucket documentaire ne doit pas servir
   de backend.
2. Renouveler `aws login --profile electionhub-demo`, confirmer l'identité et les crédits, puis
   exécuter `terraform init`, `fmt -check` et `validate`.
3. Régénérer le plan S3 seul. Exiger exactement `6 import, 0 add, 0 change, 0 destroy`.
4. Après une première approbation distincte, appliquer uniquement l'adoption S3 afin d'écrire
   l'état sans changer AWS. Contrôler immédiatement S3 par CLI et par un nouveau plan vide.
5. Régénérer le plan RDS avec `enable_new_resources=true` et `enable_test_runner=false`.
   Vérifier que RDS reste privé, que les sous-réseaux DB n'ont aucune route Internet et que le
   plan ne contient aucune destruction. Faire approuver le coût mensuel avant l'`apply`.
6. Appliquer le socle RDS. Attendre l'état `available`, puis vérifier chiffrement, sauvegardes,
   certificat, paramètre SSL, secret maître, endpoint privé et groupes de sécurité. Ne pas encore
   migrer de données.
7. Régénérer un plan avec `enable_test_runner=true`, l'approuver séparément, puis créer le runner.
   Attendre que l'instance soit `Online` dans SSM et que `/opt/electionhub/READY` existe.
8. Envoyer par SSM les variables non secrètes suivantes au script
   `infra/aws/runner/bootstrap_rds.sh` : endpoint RDS, ARN du secret maître, ARN du secret
   applicatif et SHA Git exact et relu. Le script génère les mots de passe sur l'instance ; ils
   ne doivent jamais apparaître dans la commande SSM, Terraform, Git ou les journaux.
9. Collecter les preuves : connexion `verify-full`, `pg_stat_ssl.ssl=true`, refus sans TLS,
   Alembic à jour, lecture applicative réussie et création de table refusée au runtime.
10. Passer immédiatement `enable_test_runner=false`, planifier puis appliquer uniquement la
    suppression du runner et de ses ressources temporaires. Vérifier qu'aucune instance, IP
    publique, route Internet ou rôle runner ne reste actif.
11. Injecter plus tard le secret applicatif dans GCP Secret Manager par un canal approuvé. Le
    backend GCP doit utiliser `POSTGRES_SSLMODE=verify-full` et le bundle CA monté en lecture seule.

## Approbations et blocages

Avant tout déploiement, le propriétaire doit approuver explicitement :

1. le backend d'état Terraform et, le cas échéant, un nouveau bucket d'état dédié ;
2. le coût récurrent estimé à 14,88 USD/mois, couvert par les crédits tant qu'ils existent ;
3. l'application du plan d'adoption S3, même s'il ne change pas la ressource ;
4. la création du VPC, de RDS, des deux secrets et du rôle applicatif ;
5. une fenêtre distincte de deux heures pour le runner temporaire ;
6. le SHA Git exact autorisé à exécuter Alembic ;
7. la stratégie avant le 22 mai 2027 : suppression ou passage contrôlé à un plan payant.

RDS Single-AZ reste un point de panne acceptable uniquement pour la démonstration. Le futur accès
GCP→RDS privé n'est pas résolu par AWS-4B : il nécessitera un chemin réseau inter-cloud pris en
charge ou une décision d'architecture différente. Il ne faut pas rendre RDS public pour contourner
ce blocage.
