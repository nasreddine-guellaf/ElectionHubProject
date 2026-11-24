# Compte B — guide de développement pour Bouzadi Badreddine

Tu prends en charge Lambda OTP, Lambda PV, SNS SMS Sandbox, les rôles
d'exécution, les alertes et la recette serverless. Nasr Eddine gère S3, RDS,
EC2, le réseau et Terraform côté A. Commence par les tests et les mocks
ci-dessous. Les [contrats et la checklist commune](aws-two-accounts.md) indiquent
quand demander les ARN et les accès à A.

## 1. Préparer le poste et vérifier le compte

Depuis la racine du dépôt dans le terminal PowerShell de VS Code, vérifie que ta
branche part de `main` avec AWS-5A (`1f87277`) et AWS-5B (`8809703`), puis
utilise ton propre profil AWS. Active
MFA, notamment sur le compte racine, et utilise une identité nominative ou fédérée
pour le développement. Pour IAM Identity Center, utilise `aws configure sso
--profile electionhub-serverless` puis `aws sso login --profile electionhub-serverless`
à la place d'`aws login`. Garde les sessions et le cache AWS sur ton poste.

```powershell
git status --short
git show --oneline --no-patch 1f87277 8809703
aws --version
$profileB = "electionhub-serverless"
$regionB = "eu-north-1"
aws login --profile $profileB
aws sts get-caller-identity --profile $profileB --region $regionB
aws account list-regions --profile $profileB --query "Regions[?RegionName=='eu-north-1']"
aws lambda list-functions --profile $profileB --region $regionB --max-items 1
aws sns get-sms-sandbox-account-status --profile $profileB --region $regionB
```

Compare `Account` dans la réponse STS à l'ID de ton compte affiché dans la console.
Si la valeur est `749251635900`, arrête-toi et corrige le profil. Si `ListRegions`
est refusé, vérifie la région dans la console. Avec AWS (new), distingue la région
affichée dans cette expérience du droit effectif d'utiliser cette région via
les API. Un appel de lecture réussi prouve seulement la lecture. Le compte doit
aussi pouvoir créer ou utiliser les rôles prévus et passer ces rôles à Lambda,
configurer Lambda, SNS, CloudWatch et SQS et, si retenu, gérer le réseau B.
Vérifie avec le propriétaire du compte les autorisations IAM effectives et les
restrictions du plan avant de tenter un déploiement.

Dans **Billing and Cost Management**, relève le type de plan, les crédits
restants, la date d'expiration et les services éligibles. Partage avec Nasr
l'ID, la région et les capacités vérifiées. Ne copie ni jetons, ni clés, ni
cache, ni coordonnées dans le dépôt. Les deux comptes ont des crédits et
limitations propres. Si ton offre est le Free account plan, elle prend fin au
plus tard à six mois ou à épuisement des crédits. Une opération peut être
indisponible même si l'API de lecture répond. Conserve les mocks en cas de
blocage. [Connexion CLI temporaire](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html) ·
[Offres Free Tier](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html)

## 2. Démarrer hors ligne

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.lock
Push-Location backend
..\.venv\Scripts\python.exe -m pytest -q tests/test_lambda_pv.py
..\.venv\Scripts\python.exe -m ruff check .
Pop-Location
```

**PV.** Pars de `backend/app/lambda_pv.py` et
`backend/tests/test_lambda_pv.py`. La fixture remplace le client S3 et la
connexion SQL. Rejoue le même événement, altère taille, digest ou métadonnée,
simule une transaction API encore invisible et vérifie le rejet d'une clé
`incidents/`. Ajoute la couverture qui manque à la cible B, notamment la
lecture par `VersionId`, le traitement explicite de `s3:TestEvent`, les
échecs du lot et la reprise. Conserve les vérifications actuelles. Le handler
ouvre aujourd'hui une connexion réelle à l'entrée. Pour un test Lambda en
ligne sans RDS, prépare un point d'entrée de test dédié, avec S3/SQL factices
et fixtures déterministes dans le paquet de test. Un simple JSON de test ne
suffit pas avec le handler actuel. Le paquet intégré doit exclure le point
d'entrée simulé.

**OTP.** Implémente un handler pour le contrat v1 proposé avec transport injecté.
Commence par un transport factice sans appel AWS. Ajoute ensuite l'adaptateur
SNS, activé par configuration de déploiement. Valide UUID, version, code à
six chiffres et référence de destinataire. Teste le zéro initial, l'acceptation,
le rejet sans appel SNS, l'erreur AWS et le timeout ambigu. Vérifie que le code
et le numéro sont absents des réponses et logs. Coordonne avec Nasr ou l'équipe
GCP l'adaptateur FastAPI, le mapping de la référence et les tests de
non-divulgation, d'expiration et d'usage unique.

## 3. Préparer les rôles et le déploiement B

Prépare une racine Terraform B distincte d'`infra/aws`, avec identité attendue,
région, noms et tags explicites. Livre le code, les tests, les fixtures et le
plan B pour revue. Les exemples ci-dessous décrivent les tests après
déploiement approuvé. Aucun rôle, fonction ou état B n'existe dans le dépôt actuel.

| Identité | Droits à préparer |
|---|---|
| Déploiement B | Gérer uniquement les ressources ElectionHub B prévues. Limiter `iam:PassRole` aux ARN des rôles d'exécution B avec `iam:PassedToService=lambda.amazonaws.com`. Séparer administration SNS et exécution. |
| Exécution OTP | Confiance `lambda.amazonaws.com`. Écriture dans son log group précréé. Idéalement `sns:Publish` sur un topic de test dédié à un seul destinataire vérifié, avec abonnement géré séparément. Si l'envoi direct `PhoneNumber` est requis, documenter et qualifier le `Resource: "*"` nécessaire en l'absence d'ARN de topic, restreindre la région et appliquer l'allowlist fixe de destinataires côté handler. |
| Exécution PV | Confiance `lambda.amazonaws.com`. Logs de la fonction et `sqs:SendMessage` uniquement sur sa DLQ. Aucun droit S3 A ou DB pour la variante mock. Variante intégrée avec doubles autorisations S3 et `sts:AssumeRole` vers le rôle RDS A exact. Ajouter les droits ENI requis uniquement pour la fonction VPC, en suivant la procédure Lambda pour limiter ces droits à la gestion réseau. |
| Invocateurs | Réserver `lambda:InvokeFunction` à l'ARN de fonction ou d'alias nécessaire. La permission S3 est une politique de ressource PV avec le bucket et le compte A comme conditions. |

Utilise un ZIP reproductible et un runtime compatible. Le script
`scripts/build_lambda_pv.ps1` est la référence pour le paquet intégré Linux
x86-64 et la CA officielle. Côté B, garde les invocations manuelles et la
version avec faux transport séparées de la version SNS. Après mise en service
de l'environnement B approuvé, teste d'abord les deux handlers de test par
invocation synchrone, avec des fixtures sans données personnelles.

Une fois la racine proposée créée, prépare d'abord un plan des seules ressources
B, avec SNS désactivé et sans référence au bucket A ni à RDS. Vérifie l'identité
du provider via `allowed_account_ids`, le backend d'état B et le SHA des ZIP.
Pour un environnement déjà approuvé, la mise en service B suit la revue de
ce plan et publie des versions distinctes avec leurs alias. Les variables,
noms de fonctions et noms de profil sont à fixer dans la racine B.

```powershell
$env:AWS_PROFILE = $profileB
terraform -chdir=infra/aws-serverless fmt -check -recursive
terraform -chdir=infra/aws-serverless init
terraform -chdir=infra/aws-serverless validate
terraform -chdir=infra/aws-serverless plan -input=false
```

Revoir l'état de la session et le compte après le plan. Lancer les invocations
ci-dessous seulement après le déploiement des versions mock.

```powershell
aws lambda invoke --profile $profileB --region $regionB --function-name electionhub-otp-mock --cli-binary-format raw-in-base64-out --payload file://otp-mock.json otp-response.json
aws lambda invoke --profile $profileB --region $regionB --function-name electionhub-pv-mock --cli-binary-format raw-in-base64-out --payload file://pv-mock.json pv-response.json
```

Crée `otp-mock.json` à partir du contrat v1 avec un UUID fictif et le code fictif
`012345`. Exporte la fixture S3 du test vers `pv-mock.json` avec le bucket
simulé choisi par le handler de test. Les noms de fonctions sont proposés.
Vérifie `FunctionError` et les fichiers de réponse. Pour tester les reprises et
la DLQ, utilise une **invocation asynchrone** (`--invocation-type Event`) de
la fonction de test avec un échec déterministe. Un statut d'acceptation CLI
ne prouve pas l'exécution. Vérifie les tentatives puis le message dans la DLQ.

[Autorisations SNS](https://docs.aws.amazon.com/service-authorization/latest/reference/list_sns.html) ·
[Lambda dans un VPC](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html)

## 4. Qualifier SNS SMS Sandbox

Stockholm figure dans les régions SMS d'AWS. Vérifie l'accès réel du compte B à
SNS SMS dans la région choisie pour OTP et l'éligibilité de la destination et
de l'identité d'origine. En cas de région OTP différente, utilise cette région
pour Lambda OTP, SNS et ses destinations sandbox. Cela ne change pas la région
requise pour PV. [Régions SMS](https://docs.aws.amazon.com/sms-voice/latest/userguide/what-is-sms-mms.html) ·
[Pays et origines SMS](https://docs.aws.amazon.com/sms-voice/latest/userguide/phone-numbers-sms-by-country.html)

1. Avec la session B, ouvre **Amazon SNS → Text messaging (SMS)** et confirme
   le statut Sandbox. Vérifie le plafond de dépense et le coût vers la destination.
2. Quand l'envoi est approuvé et le titulaire consentant, ajoute un seul
   numéro autorisé dans la console. L'ajout envoie un code de vérification AWS.
   Saisis ce code dans la console et confirme le statut Verified. Vérifie les
   obligations d'identité d'origine avant tout achat ou enregistrement.
3. Si le transport choisi utilise un topic, limite ses abonnements au seul
   numéro de test. Active le transport SNS sur la Lambda dédiée après vérification.
   Lance un seul parcours fictif, observe la réception et l'expiration sans
   exporter le code ou le numéro. Garde le compte en sandbox.

```powershell
$otpRegion = $regionB
aws sns get-sms-sandbox-account-status --profile $profileB --region $otpRegion
aws sns get-sms-attributes --profile $profileB --region $otpRegion --attributes MonthlySpendLimit
```

[Vérification des destinations](https://docs.aws.amazon.com/sns/latest/dg/sns-sms-sandbox-verifying-phone-numbers.html) ·
[Règles du sandbox](https://docs.aws.amazon.com/sns/latest/dg/sns-sms-sandbox.html)

## 5. Coûts, observabilité, nettoyage et remise

- Relever le plan et les crédits avant les essais. Configurer une alerte AWS
  Budgets selon le seuil convenu et vérifier le coût des SMS, des journaux,
  des requêtes, de la DLQ et du réseau. Une alerte ne coupe pas les dépenses.
  Borner la concurrence et les reprises, fixer une rétention courte des logs
  et contrôler les seuils dans la région cible. Pour PV, conserver la cible
  de concurrence réservée à deux sous réserve du quota B et de la recette RDS.
- Suivre `Errors`, `Throttles`, durée et profondeur DLQ. Corréler les événements
  par UUID de challenge ou ID d'événement, sans payload brut dans les logs.
  Restreindre aussi la lecture de la DLQ, qui peut contenir les événements source.
- À la fin de l'essai, vérifier l'ID du compte, la région, les tags et les
  ressources exactes. Pour la recette intégrée, A retire d'abord la
  notification de test en préservant les autres destinations. B désactive les
  invocations de test et retire les artefacts et ressources B temporaires
  après collecte des preuves. Inclure les versions/alias de test, groupes de logs,
  alarmes, DLQ, rôles, topics et abonnements dédiés. Si une identité d'origine
  payante a été approuvée, vérifier sa libération. Supprimer la destination
  sandbox selon le délai AWS de 24 h depuis la dernière tentative de vérification.
  A coordonne le nettoyage de ses seules données de recette approuvées.
- Remettre la branche avec code, IaC et fixtures, les commandes de reproduction,
  résultats unitaires et de déploiement, plan B, preuve de coût et de nettoyage,
  les ARN et les régions utiles. Avant la recette commune, signaler tout
  refus de compte, de région ou de service et toute différence de contrat.
