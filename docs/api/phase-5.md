# Stockage documentaire et adaptateurs AWS — Phase 5 en cours

La première tranche de la phase 5 ajoute le stockage privé des pièces justificatives sans
créer de ressource AWS. Elle conserve les binaires hors de PostgreSQL et permet de choisir
le provider par configuration.

## État actuel

**Implémenté et testé localement :**

- migration `0004_private_documents` ;
- métadonnées, taille, type MIME, empreinte SHA-256 et état de traitement ;
- stockage local privé pour le développement ;
- adaptateur Amazon S3 utilisant le mécanisme d'identité standard du SDK AWS ;
- chiffrement serveur `AES256` demandé à chaque dépôt S3 ;
- formats autorisés : PDF, JPEG et PNG ;
- limite configurable, 10 Mio par défaut et 25 Mio au maximum ;
- contrôle de la signature du contenu, nom assaini et clé objet générée par le serveur ;
- dépôt et suppression réservés à l'agent auteur tant que la révision est `DRAFT` ;
- lecture/téléchargement soumis au même RBAC que le dossier PV ;
- événements d'audit `DOCUMENT_UPLOADED` et `DOCUMENT_DELETED` ;
- table `object_events` préparée pour la déduplication des événements Lambda PV.

**Pas encore déployé ni testé sur AWS :** bucket S3, politiques IAM, notifications S3,
Lambda PV, RDS, Lambda OTP et SNS. Le statut `STORED` indique seulement que l'adaptateur a
accepté le fichier ; il ne prétend pas qu'une Lambda l'a traité.

## Configuration

Le mode par défaut reste local :

```dotenv
OBJECT_STORAGE_BACKEND=local
LOCAL_OBJECT_DIRECTORY=.local/objects
OBJECT_UPLOAD_MAX_BYTES=10485760
```

La future activation S3 utilisera :

```dotenv
OBJECT_STORAGE_BACKEND=s3
AWS_REGION=eu-west-3
S3_BUCKET=<nom-du-bucket-prive>
```

Les identifiants AWS ne doivent pas être ajoutés au dépôt. En cloud, l'application devra
utiliser un rôle d'instance ou une identité de workload. Pour une démonstration locale, le
SDK peut utiliser un profil AWS configuré hors du projet. `S3_ENDPOINT_URL` est disponible
uniquement pour un endpoint S3 compatible explicitement approuvé.

Le bucket cible devra bloquer l'accès public, activer le chiffrement, limiter le rôle de
l'API à son préfixe d'objets et refuser les transports non TLS. Le rôle Lambda recevra des
droits distincts et minimaux.

## API

Les routes suivantes exigent une session Bearer et l'accès au dossier :

| Méthode | Route | Autorisation |
|---|---|---|
| `GET` | `/api/v1/reports/{id}/revisions/{n}/documents` | acteur autorisé sur le PV |
| `POST` | `/api/v1/reports/{id}/revisions/{n}/documents` | agent auteur, révision courante en brouillon |
| `GET` | `/api/v1/reports/{id}/revisions/{n}/documents/{document_id}/content` | acteur autorisé sur le PV |
| `DELETE` | `/api/v1/reports/{id}/revisions/{n}/documents/{document_id}` | agent auteur, révision courante en brouillon |

Le dépôt utilise `multipart/form-data` avec `expected_version` et `file`. L'API ne retourne
jamais la clé interne de l'objet ni une URL publique. Le téléchargement repasse par le
contrôle d'accès du backend.

## Prochaine tranche de phase 5

1. Définir et valider la région, le budget et la convention de nommage AWS.
2. Écrire l'Infrastructure as Code du bucket privé, des rôles et des notifications.
3. Implémenter Lambda PV et le traitement idempotent de `object_events`.
4. Ajouter les incidents et leurs photographies.
5. Préparer RDS et tester la migration/restauration avec TLS.
6. Remplacer le simulateur OTP par Lambda OTP + SNS dans un sandbox approuvé.
