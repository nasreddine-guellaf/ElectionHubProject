# Phase 9 — Sauvegarde et restauration (préparation AWS)

État : procédures et objectifs préparés sur le dépôt. Aucun compte AWS n'a été interrogé dans
cette étape ; aucun backup, objet versionné, snapshot, restauration ni test cloud n'a été
exécuté. Les objectifs ci-dessous sont des cibles initiales à mesurer avec l'équipe AWS.

## Configuration constatée dans le dépôt

- `infra/aws/rds.tf` chiffre le stockage RDS (`storage_encrypted = true`), active les sauvegardes
  automatiques avec `var.rds_backup_retention_days`, définit la fenêtre `02:00-03:00`, copie les
  tags dans les snapshots, protège la suppression et exige un snapshot final. L'instance est
  Single-AZ et privée. `infra/aws/variables.tf` fixe la rétention à 7 jours par défaut et limite
  la variable à 1–7 jours. La rétention de sept jours est donc déjà prévue dans Terraform ; elle
  n'est pas activée sur une instance réelle tant qu'aucun déploiement approuvé n'a eu lieu.
- `infra/aws/s3.tf` prévoit le versioning activé, le chiffrement serveur SSE-S3 (`AES256`), le
  blocage des quatre formes d'accès public, l'accès HTTPS obligatoire et `prevent_destroy`.
  `infra/aws/iam.tf` limite le rôle d'application au préfixe `reports/*` et exige SSE-S3 lors
  des uploads. Ce rôle ne reçoit pas les droits `s3:ListBucketVersions`, `s3:GetObjectVersion`
  ou `s3:DeleteObjectVersion` nécessaires à une restauration administrative.
- `docs/infrastructure/aws-4b-rds-plan.md` indique que les ressources S3 sont une adoption d'un
  bucket existant, que les plans préparés n'ont pas été appliqués et que la dernière vérification
  du compte rapportée confirmait le versioning, AES256 et les blocages publics. Il s'agit d'une
  preuve datée antérieure, pas d'une vérification faite pendant cette préparation.
- `scripts/smoke_s3.py` utilise une clé synthétique unique et supprime ses propres versions après
  le test. Il ne constitue pas une procédure de restauration ni un test de backup RDS.

Le chiffrement RDS est activé dans le code Terraform, mais la clé KMS réellement utilisée et les
droits de récupération ne seront vérifiables qu'après déploiement. S3 est configuré en SSE-S3,
pas SSE-KMS. Le versioning S3 conserve les anciennes versions et marqueurs de suppression, mais
ne protège pas d'un opérateur autorisé à effacer définitivement toutes les versions. Aucune
expiration des anciennes versions, réplication inter-région, verrouillage Object Lock, coffre de
sauvegardes séparé ou règle d'immutabilité n'est définie ici. Chacune de ces options demande une
analyse d'accès, de rétention et de coûts avant modification.

## Objectifs initiaux (à approuver et mesurer)

| Donnée | Protection préparée | RPO cible | RTO cible initial | Mesure réelle |
|---|---|---:|---:|---|
| PostgreSQL | Backup RDS automatique, 7 jours, restauration à un instant donné (PITR) | ≤ 5 min | ≤ 4 h | Non mesuré : aucune restauration exécutée |
| Document S3 | Versioning ; récupérer l'ancienne version ou retirer le delete marker | Version précédente encore conservée dans S3 | ≤ 1 h par document courant | Non mesuré : aucun objet de production vérifié |

Le RPO PostgreSQL de cinq minutes est une cible de conception fondée sur la fréquence habituelle
de transfert des journaux de transaction RDS, pas une garantie ni une mesure de cette instance.
PITR n'est possible que dans la fenêtre de rétention et jusqu'au dernier instant restaurable
fourni par RDS. Le RTO de quatre heures inclut une restauration vers une nouvelle instance,
l'attente de disponibilité, les contrôles TLS/migrations et une décision humaine de bascule ;
il est une hypothèse à chronométrer. Les délais S3 dépendent du volume et de l'accès IAM.
Confirmer les exigences métier, le plan AWS, les quotas, la région, la clé de chiffrement et le
budget avec les responsables avant de déclarer ces objectifs acceptés.

## Runbook — restauration PostgreSQL

### Avant l'incident

1. Confirmer pour l'instance : `BackupRetentionPeriod = 7`, état disponible, chiffrement,
   sauvegarde la plus récente et `LatestRestorableTime`. Consigner l'heure et l'identité de
   l'opérateur, sans copier de secret dans le ticket.
2. Restreindre les opérations de restauration et de snapshots aux rôles d'exploitation dédiés.
   Le rôle applicatif ne doit pas recevoir de permissions RDS ou de récupération de secrets.
3. Vérifier que les personnes de garde peuvent lire le secret via Secrets Manager et que les
   politiques IAM/KMS permettent la restauration. Ne pas inscrire de mot de passe dans une
   commande, un journal ou ce dépôt.

### Incident ou exercice approuvé

1. Déclarer l'incident, arrêter si possible les écritures applicatives affectées, enregistrer
   l'heure de détection et choisir avec le responsable de données l'instant cible juste avant
   la corruption/perte. Éviter un retour arrière sur une instance active avant d'avoir conservé
   les preuves et identifié l'étendue.
2. Dans RDS > **Automated backups** > instance > **Actions > Restore to point in time**, ou via
   `aws rds restore-db-instance-to-point-in-time`, créer une **nouvelle** instance avec un
   identifiant de récupération distinct. Sélectionner l'instant, le sous-réseau privé et les
   groupes de sécurité approuvés. Ne jamais rendre l'instance publique pour accélérer l'accès.
3. Attendre l'état `available`. Relever l'endpoint, l'instant restauré, les événements RDS et
   les IDs de snapshots. Les restaurations PITR créent une instance distincte ; planifier
   séparément le changement d'endpoint ou de secret après validation.
4. Depuis un accès privé approuvé, vérifier TLS `verify-full` avec la CA, la base et le schéma,
   l'état Alembic, les comptes et élections synthétiques attendus, les contraintes d'intégrité,
   les résultats, les journaux d'audit, la cohérence applicative et l'heure de dernière donnée.
   Utiliser des identifiants non secrets et des échantillons minimisés dans le compte rendu.
5. Faire valider les écarts par le responsable métier et l'exploitation. Réactiver les écritures
   uniquement après accord, mettre à jour le secret/configuration via le gestionnaire approuvé,
   surveiller les erreurs puis confirmer le parcours applicatif. Conserver l'ancienne base
   isolée jusqu'à décision de rétention, sans la supprimer automatiquement.
6. Pour une sauvegarde ponctuelle, restaurer le snapshot vers une instance séparée et appliquer
   les mêmes contrôles. Une restauration de snapshot revient à l'instant du snapshot, pas à un
   instant arbitraire dans les journaux.

### Vérifications et nettoyage

Consigner durée réelle, instant demandé/restauré, RPO observé, temps jusqu'à `available`, temps
de validation et temps de reprise (RTO), erreurs, décision et opérateurs. Nettoyer seulement les
ressources temporaires d'un exercice après autorisation et après avoir confirmé qu'elles ne sont
pas la source de reprise. Les sauvegardes RDS et snapshots chiffrés exigent l'accès à leur clé ;
ne pas désactiver ni supprimer une clé utilisée par des backups.

## Runbook — document S3 supprimé ou remplacé

1. Confirmer le bucket, la clé exacte et l'heure de suppression/remplacement avec le propriétaire
   du document. Ne pas recopier le contenu du fichier dans les tickets ou logs.
2. Avec un rôle de récupération dédié, lister les versions de la clé et repérer le `VersionId`
   de la version valide et, le cas échéant, du delete marker :

   ```powershell
   aws s3api list-object-versions --bucket <bucket> --prefix <clé-exacte>
   aws s3api head-object --bucket <bucket> --key <clé-exacte> --version-id <version-id>
   ```

3. Pour une modification, récupérer d'abord la version précédente vers un emplacement de
   quarantaine privé, vérifier taille, type, somme de contrôle et accès, puis restaurer par
   copie vers la clé courante après accord du propriétaire :

   ```powershell
   aws s3api get-object --bucket <bucket> --key <clé-exacte> --version-id <version-id> <fichier-temporaire>
   aws s3api copy-object --bucket <bucket> --key <clé-exacte> --copy-source <bucket>/<clé-encodée>?versionId=<version-id> --server-side-encryption AES256
   ```

   La copie crée une nouvelle version courante ; l'historique reste disponible.
4. Pour une suppression représentée par un delete marker, préférer la restauration par copie de
   la version précédente (étape 3) : elle laisse le marqueur dans l'historique. Retirer le
   marqueur avec `delete-object --version-id <marker-version-id>` rend aussi la version
   précédente courante, mais supprime définitivement ce marqueur ; réserver cette action à un
   opérateur autorisé après validation à deux personnes.
5. Valider `head-object` de la clé courante, l'ID de version, le chiffrement, les métadonnées et
   l'ouverture via l'API d'autorisation. Documenter la récupération et supprimer seulement le
   fichier temporaire après vérification. Ne jamais utiliser `aws s3 rm --recursive` ni purger
   des versions dans le cadre d'une récupération.

Les commandes ci-dessus sont des modèles non exécutés. Les permissions du rôle applicatif
actuelles ne suffisent pas à cette procédure : l'équipe AWS doit définir un rôle d'opérateur
distinct, à privilèges minimaux, journalisé et soumis à approbation. Éviter d'accorder les droits
de récupération au compte de service de l'application.

## Exercices à réaliser après disponibilité d'un environnement isolé

Ne pas utiliser de données de vote réelles. Générer des comptes, élections, résultats et PDF
synthétiques avec préfixe/identifiant de test, puis supprimer ces seules données après preuve.

1. Vérifier la configuration et l'état réel : rétention RDS, dernière sauvegarde, dernier instant
   restaurable, chiffrement RDS, versioning/SSE-S3 S3, blocage public et identité de l'opérateur.
2. Créer une base jetable, insérer des lignes synthétiques à intervalles connus, noter les heures,
   déclencher un backup manuel, puis restaurer ce backup dans une instance isolée et comparer
   lignes, contraintes et contrôles Alembic.
3. Pour PITR, créer des marqueurs de données avant et après un instant cible, restaurer dans une
   instance jetable à cet instant et vérifier l'absence du marqueur postérieur. Mesurer le RPO et
   le RTO avec horodatages indépendants.
4. Déposer un objet S3 synthétique, le remplacer et le supprimer ; lister les versions, récupérer
   une version dans une clé de quarantaine puis valider le retour. Confirmer que le rôle
   applicatif ne peut pas effacer une version historique et que le rôle de récupération ne peut
   pas lire d'autres préfixes.
5. Tester accès refusé aux backups/versions sans rôle approuvé, absence d'accès public et lecture
   TLS obligatoire. Vérifier que chiffrement, identité opérateur et événements sont auditables.
6. Chronométrer et consigner preuves, échecs, écarts par rapport aux cibles RPO/RTO, coût estimé,
   nettoyage des seules ressources de test et validation du responsable.

## Dépendances et blocages

- Déploiement AWS-4B et accès de lecture RDS/S3 pour vérifier l'état réel ; aucun n'est établi
  par cette préparation documentaire.
- Rôle de récupération, droits de lecture/suppression de versions, accès de déchiffrement et
  séparation de tâches à valider par les responsables AWS/sécurité.
- Accord sur les objectifs RPO/RTO, région secondaire éventuelle, rétention réglementaire et
  budget de stockage/versioning. Les copies inter-région ou immuables ne sont ni configurées ni
  chiffrées/estimées ici.
- Fenêtre d'exercice, endpoints privés et opérateur habilité nécessaires à toute restauration
  réelle. Aucun `terraform apply`, accès AWS ou coût n'est engagé par cette étape.

## Références AWS

- [Sauvegarde et restauration RDS](https://docs.aws.amazon.com/AmazonRDS/latest/gettingstartedguide/managing-backup-restore.html)
- [Période de rétention des sauvegardes automatiques RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithAutomatedBackups.BackupRetention.html)
- [Récupérer un objet supprimé avec S3 Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/troubleshooting-versioning.html)
- [Récupérer les versions d'un objet S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/RetrievingObjectVersions.html)
