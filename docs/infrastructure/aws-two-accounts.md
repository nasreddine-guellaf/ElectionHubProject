# ElectionHub — intégration AWS entre les comptes A et B

La [feuille de route](../ROADMAP.md#phase-5--données-et-événements-aws) suit l'avancement.
Ce dossier fixe les interfaces de travail et les conditions de recette. Le
[guide du compte B](aws-account-b-onboarding.md) permet de démarrer sans accès à A.

## Propriété et état Terraform

| Composant | Propriétaire | Contrat de déploiement |
|---|---|---|
| S3 privé existant, RDS, VPC A, runner SSM, migrations, API de secours EC2 | Nasr Eddine Guellaf, A, `749251635900`, `eu-north-1` | A gère seul le bucket, sa politique et sa configuration complète de notifications. |
| Lambda PV, Lambda OTP, SNS Sandbox, rôles d'exécution, journalisation et DLQ | Bouzadi Badreddine, B, ID et capacités à vérifier | B prépare une racine IaC indépendante, par exemple `infra/aws-serverless/`, et un état distinct. |
| Identité GCP et accès AWS depuis FastAPI | Équipe GCP avec A et B | B possède le rôle d'invocation OTP. A possède les rôles de ses ressources. Échanger les identifiants utiles via la documentation d'intégration, éventuellement les ARN via un canal d'équipe. |

Le [prototype AWS-5A](aws-5a-lambda-pv.md) regroupe Lambda, notification, endpoint S3,
VPC et RDS dans un seul compte. Les plans existants restent des preuves historiques.
Dans la racine `infra/aws`, garder `enable_pv_lambda=false` pour la cible A et conserver
le code de référence. Prévoir une notification A découplée de la création de Lambda,
avec ARN B en entrée. Les deux plans doivent vérifier le compte du provider, utiliser
des profils et des états distincts et éviter de partager un état contenant des données
sensibles. Les valeurs échangées sont des ID, régions, ARN, CIDR et versions de contrat.

## S3 A → Lambda PV B

1. B crée, lors du futur déploiement approuvé, la fonction PV en `eu-north-1`. La
   notification S3 directe exige exactement la région du bucket. B accorde sur la
   fonction ou sur l'alias ciblé `lambda:InvokeFunction` à `s3.amazonaws.com`, avec
   `SourceArn=arn:aws:s3:::electionhub-demo-749251635900-eu-north-1` et
  `SourceAccount=749251635900`. Cette permission précède la configuration A.
2. B accorde à son rôle d'exécution `s3:GetObject` et `s3:GetObjectVersion` sur
   `arn:aws:s3:::electionhub-demo-749251635900-eu-north-1/reports/*`. A autorise ce
   même ARN de rôle dans la bucket policy avec les mêmes actions et ressources.
   Garder le blocage public, l'enforcement TLS et SSE-S3 existants. Aucun droit sur
   `incidents/*`, ni accès pour l'ensemble du compte B. L'invocation et la lecture
   sont deux autorisations distinctes.
3. A relève la configuration de notifications et la conserve intégralement en y
   ajoutant seulement `s3:ObjectCreated:*` pour `reports/`. Le PUT remplace la
   configuration complète. A vérifie les filtres qui se chevauchent et garde un
   instantané de la configuration précédente pour le retour arrière. Tester la
   validation de destination S3 et le traitement des événements de test S3
   (`s3:TestEvent`, format distinct de `Records`).

Si B ne peut pas déployer en `eu-north-1`, garder PV en mode simulé et décider
ensemble d'un relais régional explicite ou d'un autre compte B compatible. OTP
peut avancer dans une région B éligible au SMS. Références AWS :
[destinations S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-how-to-event-types-and-destinations.html)
et [procédure S3 → Lambda intercomptes](https://repost.aws/knowledge-center/lambda-s3-cross-account-function-invoke).

## Lambda PV B → RDS privé A

**Option à valider ensemble.** Raccorder PV aux sous-réseaux privés d'un VPC B
et établir un peering direct avec A. Réserver des CIDR sans chevauchement, valider
les routes aller-retour, DNS et NACL, puis restreindre TCP 5432 à la source PV
approuvée. Tester la résolution du vrai nom RDS et `sslmode=verify-full` avec la CA
régionale depuis le runtime B. Le Gateway Endpoint S3 du prototype A ne se partage
pas à travers le peering. Chiffrer un endpoint S3 propre à B et un chemin vers STS
régional, par exemple via endpoint d'interface ou sortie approuvée, selon l'option.

B autorise `sts:AssumeRole` vers le rôle dédié dans A. A limite sa confiance au
rôle d'exécution PV B et accorde `rds-db:connect` sur
`arn:aws:rds-db:eu-north-1:749251635900:dbuser:<DbResourceId>/electionhub_event_processor`.
Après Alembic, A crée le login non propriétaire avec `rds_iam` et les droits SQL
de contrôle du prototype. B adapte `database_connection()` pour signer le jeton
RDS avec la session STS de A. Le code actuel signe avec la chaîne d'identité par
défaut et doit être adapté. Le rôle d'exécution B conserve son identité pour S3.

Avant de choisir le peering, vérifier l'éligibilité des deux comptes et chiffrer
les endpoints, le trafic et les logs. Si la liaison directe est impossible, étudier
une remise des résultats à un service privé/authentifié en A qui possède l'écriture
SQL, avec nouveau contrat, reprises et coût approuvés. Garder la notification
réelle désactivée tant que le chemin retenu n'est pas qualifié.
[Peering AWS](https://docs.aws.amazon.com/vpc/latest/peering/vpc-peering-basics.html) ·
[Politique IAM RDS intercompte](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.IAMPolicy.html)

## FastAPI GCP et EC2 A → Lambda OTP B

Proposition pour GCP. Utiliser le service account dédié de Compute Engine pour
obtenir un ID token Google, puis `AssumeRoleWithWebIdentity` vers un rôle
d'invocation B. Restreindre la confiance au `sub` numérique du service account
et à l'audience convenue. Avec `azp` présent, valider le mapping IAM
`accounts.google.com:aud` → `azp` et `accounts.google.com:oaud` → `aud`.
Limiter le rôle à `lambda:InvokeFunction` sur l'ARN d'alias OTP convenu.
L'adaptateur signe l'invocation AWS avec des identifiants STS temporaires renouvelés.
Un service account différent ou une audience incorrecte doit échouer.

Pour EC2 A, prévoir que le rôle d'instance assume un rôle d'invocation dédié dans
B, avec confiance limitée au rôle EC2 exact et permission limitée à l'alias OTP.
Tester cette route avec l'API de secours. Pour PV, FastAPI écrit dans S3 et
l'événement reste la responsabilité de S3. La fédération AWS ne crée pas le
chemin réseau GCP→RDS. Garder les clés permanentes hors du projet et des workloads.
[Fédération GCP vers AWS](https://aws.amazon.com/blogs/security/access-aws-using-a-google-cloud-platform-native-workload-identity/)

## Contrats de développement

### OTP, proposition v1 à valider avant de coder l'adaptateur

Dans le backend actuel, `POST /api/v1/auth/citizen/request-otp` crée le code à
six chiffres et le challenge HMAC. `POST /api/v1/auth/citizen/verify-otp` vérifie
le code puis émet la session. Conserver ces responsabilités dans FastAPI pour
remplacer le transport local sans déplacer l'état, les limites ni l'authentification.
Le diagramme initial envisageait la génération Lambda. La déplacer demanderait
un autre contrat de vérification et une décision d'équipe.

| Élément | Contrat proposé |
|---|---|
| Appel interne | Invocation synchrone authentifiée, JSON `{"version":1,"challenge_id":"<uuid>","recipient_ref":"demo-otp","code":"012345"}`. `code` est une chaîne. Aucune CIN, identité citoyenne, clé HMAC ou destination fournie par le client. |
| Destinataire | B résout `recipient_ref` vers une destination prédéfinie et vérifiée dans le sandbox. FastAPI mappe son destinataire simulé vers cette référence. |
| Retour | `{"version":1,"status":"accepted"}` après acceptation du transport. Le statut confirme la soumission, la réception se vérifie séparément. Rejets stables `invalid_request` / `recipient_not_allowed` et erreur normalisée `provider_unavailable`. Ne renvoyer ni code, ni numéro, ni détail SNS. |
| Échecs | L'adaptateur contrôle aussi `FunctionError` et la forme du JSON. Échec ou timeout rend le challenge inutilisable côté API. Éviter les renvois automatiques en cas de résultat SNS ambigu, car un timeout peut suivre un envoi accepté. Corréler avec le UUID et tester la non-divulgation d'éligibilité. |
| Garde-fous | Conserver cinq minutes de validité, cinq essais, usage unique et throttling côté API. Tester le faux transport puis une destination consentante. Pas de journalisation du payload, du code ou du numéro, y compris dans les exceptions et traces. |

### PV, contrat existant AWS-5A

- Entrée `Records[]` S3, `eventSource=aws:s3`, `eventName=ObjectCreated:Put`
  ou autre type `ObjectCreated:…`, `s3.bucket.name`, `s3.object.key`
  (encodage URL), `sequencer` et `versionId` lorsqu'ils sont fournis.
- Clé `reports/<report_uuid>/revisions/<n>/<document_uuid>.<pdf|png|jpg>`.
  Relire la version de l'objet portée par l'événement et vérifier la métadonnée
  `document-id`, la taille et le SHA-256 contre `report_documents`. Aucune photo
  `incidents/` ne participe à ce flux.
- Dédoublonner avec l'empreinte du bucket, de la clé, de la version, du type
  d'événement et du sequencer. Insérer dans `object_events` et mettre à jour
  `processing_status`, `processed_at` et `failure_reason` transactionnellement.
  Intégrité incorrecte → `FAILED`. Métadonnée absente ou panne transitoire → reprise.
  Les erreurs asynchrones épuisées vont en DLQ. Résultat du handler pour les tests
  `{"processed":1,"duplicate":0,"failed":0}`. La validation humaine reste séparée.

## Recette et décisions à consigner

- [ ] **A seul** — Valider l'état, le coût, les plans sans destruction, l'adoption
  S3 sans mutation, RDS privé, les rôles SQL non propriétaires, Alembic et le test
  TLS positif/négatif. Préparer EC2 et vérifier son rôle d'instance et la parité API.
- [ ] **B seul** — Confirmer ID, région, crédits, limites et droits effectifs. Livrer
  OTP simulé et PV sur événements synthétiques, tests, plans B et preuves de logs
  expurgés, métriques et DLQ.
- [ ] **A+B** — Choisir le réseau PV→RDS, ses CIDR, ses coûts et le rôle STS. Échanger
  ARN de fonction/alias PV, ARN de rôle PV, ARN du bucket, endpoint RDS et CA
  publique. Tester TLS, refus hors périmètre, droits SQL et lecture S3 versionnée.
- [ ] **A+B+GCP** — Valider audience, service account, alias OTP et politique
  d'invocation. Tester les identités autorisées et refusées, puis le parcours OTP
  avec consentement, y compris expiration, rejeu et absence de secret dans les logs.
- [ ] **A+B** — Après validation du chemin complet, activer la notification. Un dépôt
  fictif devient `PROCESSED`, un rejeu donne une seule écriture logique, une pièce
  altérée devient `FAILED` et une panne répétée rejoint la DLQ. Vérifier que
  `incidents/` ne déclenche rien, que le PV attend toujours une décision humaine
  et que le retour à la configuration de notifications précédente est documenté.
