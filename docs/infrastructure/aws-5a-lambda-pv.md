# AWS-5A — Lambda PV idempotente, préparée sans déploiement

Date de qualification : 24 novembre 2026. Cette tranche ajoute le code et le plan Terraform du
traitement S3, mais n'applique aucun plan, ne modifie pas le bucket et ne crée aucune ressource.

## Contrat de traitement

La fonction reçoit uniquement les événements S3 `ObjectCreated:*` du bucket ElectionHub et du
préfixe `reports/`. Elle décode et valide strictement la clé, retrouve le document déjà validé par
l'API, relit l'objet privé et compare sa taille, son SHA-256 et la métadonnée `document-id`.

Le traitement écrit dans `object_events` avec `ON CONFLICT DO NOTHING`. Une livraison répétée du
même événement est donc un succès sans seconde mise à jour. Un objet dont l'intégrité ne correspond
pas est marqué `FAILED`. Une métadonnée PostgreSQL absente provoque une nouvelle tentative, car S3
peut notifier avant que la transaction API soit visible. Les erreurs épuisant les reprises vont dans
une file SQS chiffrée conservée quatorze jours.

S3 garantit une livraison au moins une fois, sans ordre global. L'identifiant logique inclut bucket,
clé, version, type et `sequencer`, puis est condensé en SHA-256. Cette stratégie ne prétend pas
ordonner des clés différentes.

## Identité et réseau

- rôle IAM Lambda distinct, limité à `GetObject`/`GetObjectVersion` sous `reports/` ;
- `rds-db:connect` limité au Resource ID de l'instance et au login
  `electionhub_event_processor` ;
- rôle PostgreSQL sans mot de passe, non propriétaire, membre de `rds_iam` ;
- droits SQL limités aux colonnes de contrôle de `report_documents` et à `object_events` ;
- TLS `verify-full` avec le bundle CA régional inclus dans l'artefact ;
- Lambda privée, aucune entrée réseau, sortie 5432 vers le groupe RDS et HTTPS vers la seule
  prefix list S3 régionale ;
- endpoint S3 Gateway gratuit, sans NAT ni endpoint Secrets Manager payant ;
- concurrence réservée à deux pour borner la charge sur `db.t4g.micro`.

L'authentification IAM évite tout mot de passe Lambda, mais elle consomme de la mémoire RDS. Ce
point doit être mesuré sur `db.t4g.micro` pendant la qualification ; si la marge est insuffisante,
il faudra approuver une classe supérieure ou une autre méthode de secret, jamais assouplir TLS.

## Construction reproductible

Le script `scripts/build_lambda_pv.ps1` installe des versions épinglées pour Linux x86-64, copie le
handler, télécharge le bundle CA depuis le trust store RDS officiel, valide la CA puis crée
`.local/build/lambda_pv.zip`. Le ZIP et le plan restent ignorés par Git.

```powershell
.\scripts\build_lambda_pv.ps1
```

Le flag Terraform `enable_pv_lambda` vaut `false` par défaut et exige
`enable_new_resources=true`. L'artefact n'est lu que lorsque le flag est activé.

## Vérifications

| Contrôle | Résultat |
|---|---:|
| Tests Lambda ciblés | 10 réussis |
| Suite backend complète | 127 réussis, 2 avertissements de dépendances |
| Import Linux du ZIP en conteneur | psycopg 3.3.9 et Boto3 1.44.9 chargés |
| Ruff lint/format | réussi |
| Terraform format/validate | réussi |
| Plan AWS-5A | 6 imports, 25 ajouts, 0 modification, 0 destruction |

Les six ressources S3 existantes restent `no-op`. Terraform ajoute séparément une notification
S3 filtrée sur `reports/`; il s'agit de l'unique mutation future du bucket dans ce plan. Elle ne
doit être appliquée qu'après l'adoption S3, la création de RDS et un nouveau plan approuvé.

## Ordre de déploiement futur

1. Adopter les six contrôles S3 dans un état Terraform approuvé, sans mutation.
2. Déployer et qualifier le socle RDS AWS-4B.
3. Exécuter le runner afin de créer le login IAM et d'appliquer les droits SQL après Alembic.
4. Reconstruire le ZIP depuis le commit approuvé et conserver son SHA-256 dans la preuve.
5. Planifier avec `enable_pv_lambda=true`, relire IAM, endpoint, groupes et notification.
6. Appliquer dans une fenêtre de test, déposer un PDF synthétique et vérifier `PROCESSED`.
7. Rejouer le même événement et vérifier une seule ligne logique dans `object_events`.
8. Tester un objet altéré, une indisponibilité DB et la DLQ, puis supprimer les données de test.

AWS-5A n'ajoute pas encore les incidents, Lambda OTP ou SNS. Aucun SMS réel n'est autorisé.
