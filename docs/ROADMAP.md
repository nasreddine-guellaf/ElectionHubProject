# Feuille de route ElectionHub V2

Dernière mise à jour : 24 novembre 2026.

Ce document suit les dix phases du plan directeur ElectionHub. Il distingue les éléments
réellement implémentés et testés des travaux encore planifiés. ElectionHub reste une
plateforme de consolidation de résultats par bureau de vote : ce n'est pas un système de
vote électronique.

## Vue d'ensemble

| Phase | Intitulé | Statut | Résultat principal |
|---:|---|---|---|
| 1 | Socle local et dépôt | ✅ Terminée | API FastAPI, PostgreSQL, migrations et données synthétiques |
| 2 | Modèle métier et API | ✅ Terminée | Scrutins, candidats, affectations, PV révisables et résultats structurés |
| 3 | Authentification et autorisation | ✅ Terminée | Sessions, RBAC, OTP citoyen simulé et audit |
| 4 | Application web | ✅ Terminée | Application React locale unique pour tous les profils |
| 5 | Données et événements AWS | 🚧 En cours | S3 opérationnel ; AWS-3 planifié ; préparation backend RDS AWS-4A terminée |
| 6 | Backend principal GCP | 🟡 Prête à démarrer | Lot préparatoire attribuable à Ayman ; déploiement bloqué par les accès GCP et RDS |
| 7 | Déploiement Azure | 🟡 Prête à démarrer | Lot préparatoire attribuable à Ayman ; déploiement bloqué par les accès Azure et l'URL GCP |
| 8 | Analytique et publication | ⏳ À faire | BigQuery, synchronisation et Looker Studio |
| 9 | Sécurité, secours et résilience | ⏳ À faire | Cloudflare, Load Balancing GCP, EC2 et tests de basculement |
| 10 | Recette finale et documentation | ⏳ À faire | Tests multi-cloud de bout en bout et démonstration académique |

Progression fonctionnelle : **4 phases terminées sur 10, phase 5 en cours**. Cela ne signifie pas que 40 %
de l'effort total est consommé : les déploiements et interconnexions multi-cloud restantes
comportent davantage de dépendances externes, de sécurité et de validation.

État de passage au 24 novembre 2026 : le produit local des phases 1 à 4 fonctionne, le stockage
documentaire S3 réel est qualifié et le backend est prêt pour une connexion RDS PostgreSQL 16
avec TLS `verify-full`. Aucune instance RDS, ressource GCP ou ressource Azure n'est encore
déployée. Les phases 6 et 7 peuvent cependant commencer en parallèle sur une branche dédiée,
sans attendre la création de RDS, en préparant l'infrastructure, les images, la configuration,
les tests et les procédures de déploiement.

## Passation à Ayman — phases 6 et 7

Ayman peut reprendre ce dépôt avec son propre Codex. Il doit travailler sur une branche ou un
worktree séparé afin de ne pas mélanger son lot GCP/Azure avec la poursuite AWS. Point de départ
recommandé après publication de cette feuille de route :

```powershell
git clone https://github.com/nasreddine-guellaf/ElectionHubProject.git
Set-Location ElectionHubProject
git switch -c feat/phases-6-7-ayman
python scripts/init_env.py
```

Avant toute modification, Codex doit lire `README.md`, ce fichier, `docs/architecture/v2.md`,
`docs/infrastructure/aws-4a-backend-rds.md`, `.env.example`, `docker-compose.yml` et les
Dockerfiles. Il doit inspecter le code existant, conserver les workflows locaux et exécuter les
tests avant puis après ses changements. Les valeurs secrètes, identifiants cloud, fichiers
Terraform d'état et certificats privés ne doivent jamais être commités.

Prompt de démarrage conseillé pour son Codex :

> Tu travailles sur ElectionHub, branche `feat/phases-6-7-ayman`. Prépare les phases 6 et 7
> décrites dans `docs/ROADMAP.md`. Commence par inspecter l'architecture et exécuter les tests.
> Travaille par petits commits, préserve Docker Compose et PostgreSQL local, n'applique aucun
> Terraform et ne crée aucune ressource cloud sans autorisation explicite. Implémente d'abord
> les éléments testables hors ligne, documente les variables et commandes, puis signale les
> étapes bloquées par les comptes, les secrets, RDS ou les DNS. N'intègre pas les phases 8 à 10.

Répartition recommandée : Ayman possède les fichiers qu'il ajoute sous `infra/gcp/`,
`infra/azure/` et `docs/infrastructure/` pour les phases 6 et 7. Il peut modifier le backend ou
le frontend seulement lorsque c'est requis pour leur déploiement, avec tests associés. Les
changements partagés dans `.env.example`, `docker-compose.yml`, `README.md` et cette feuille de
route doivent rester minimaux afin de faciliter la fusion avec le lot AWS.

## Phases terminées

### Phase 1 — Socle local et dépôt

**Statut : terminée et testée.**

- Structure du monorepo, configuration locale et documentation initiale.
- API FastAPI avec endpoints de santé et de consultation des bureaux.
- PostgreSQL sous Docker Compose, migrations Alembic et seed synthétique idempotent.
- Tests automatisés, contrôles Ruff et instructions PowerShell/WSL.

Preuves : [rapport de vérification phase 1](testing/phase-1.md) et
[décision de socle](decisions/0001-socle-local.md).

### Phase 2 — Modèle métier et API

**Statut : terminée et testée.**

- Modèle relationnel des scrutins, candidats, bureaux, affectations, rapports et résultats.
- PV rattaché à un scrutin et un bureau, révisions traçables et historique conservé.
- Règles de cohérence des suffrages, participation et candidats autorisés.
- API versionnée pour le cycle de saisie et de soumission.
- Contraintes SQL, migration et données de démonstration synthétiques.

Preuves : [modèle relationnel phase 2](database/phase-2.md),
[API phase 2](api/phase-2.md) et [rapport phase 2](testing/phase-2.md).

### Phase 3 — Authentification et autorisation

**Statut : terminée et testée.**

- Connexion des agents, administrateurs et validateurs avec mots de passe hachés.
- Sessions Bearer, révocation, expiration et limitation des tentatives.
- RBAC appliqué par le backend aux endpoints protégés.
- Parcours citoyen CIN + OTP simulé localement, sans SMS réel.
- Validation/rejet humain, corrections auditables et journal d'audit.

Preuves : [ADR authentification/RBAC](decisions/0003-authentification.md),
[API et permissions phase 3](api/phase-3.md) et [rapport phase 3](testing/phase-3.md).

### Phase 4 — Application web

**Statut : terminée et testée localement.**

- Application React/TypeScript unique avec navigation et routes adaptées aux rôles.
- Interfaces citoyen, agent, administrateur et validateur.
- Création, saisie, soumission, révision, approbation et rejet des PV structurés.
- Administration des scrutins, candidats, bureaux, affectations et comptes.
- Gestion des états de chargement, erreurs réseau, permissions et sessions expirées.
- Image Nginx non privilégiée, proxy API et stack Docker locale complète.
- 18 tests frontend et 98 tests backend réussis lors de la recette de phase 4.

Preuves : [parcours de l'application phase 4](api/phase-4.md) et
[rapport de vérification phase 4](testing/phase-4.md).

## Phases restantes

### Phase 5 — Données et événements AWS

**Statut : en cours.**

Terminé : migration documentaire, adaptateurs local et S3, contrôles PDF/JPEG/PNG,
empreinte SHA-256, endpoints privés, RBAC, audit, interface de dépôt/téléchargement,
tests automatisés et qualification réelle du bucket S3 privé en `eu-north-1`.
AWS-4A ajoute une configuration TLS RDS fermée par défaut, la validation de CA et un
pool SQLAlchemy borné, tout en conservant PostgreSQL 16 local sans TLS.

Voir [l'API documentaire de phase 5](api/phase-5.md) et le
[rapport de vérification intermédiaire](testing/phase-5.md). La préparation AWS-3,
les coûts et les gardes-fous sont détaillés dans le
[plan Terraform, IAM et RDS](infrastructure/aws-3-plan.md).
La configuration backend est décrite dans la
[préparation TLS RDS AWS-4A](infrastructure/aws-4a-backend-rds.md).

Travail prévu :

- Installer et valider Terraform, puis importer le bucket existant dans l'état sans le modifier.
- Faire approuver le budget RDS estimé à 14,48 USD/mois en privé ou 18,13 USD/mois
  avec endpoint public filtré, secret géré inclus.
- Créer, après approbation, le rôle applicatif minimal, le VPC et RDS PostgreSQL 16.
- Monter le bundle CA officiel et qualifier `verify-full` contre la future instance RDS.
- Créer un utilisateur SQL applicatif distinct puis tester Alembic sur une base RDS vide.
- Étendre les téléversements contrôlés aux photographies d'incidents.
- Implémenter Lambda PV, déclenchée par S3, avec traitement idempotent et reprise d'erreur.
- Implémenter Lambda OTP et l'intégration SNS dans une configuration de test approuvée.
- Ajouter les incidents et pièces jointes au modèle, à l'API et à l'interface.
- Tester les événements dupliqués, fichiers invalides, échecs partiels et nouvelles tentatives.

Prérequis : installation Terraform, plan S3 sans changement, budget/alertes, choix de la
connectivité GCP→RDS, IPv4 de sortie GCP fixe si l'endpoint est public, puis approbation
explicite avant tout `terraform apply`. Aucun SMS réel ni ressource payante ne doit être
créé sans accord explicite.

Risques principaux : consommation des crédits AWS, indisponibilité Single-AZ, exposition
réseau accidentelle, secret maître utilisé par l'application, dérive Terraform sur le bucket
existant et impossibilité de relier GCP à un RDS privé avec le compte simplifié actuel.

Critère de sortie : un agent dépose un PV fictif dans S3, Lambda PV traite l'événement une
seule fois logiquement, RDS reflète son état, et le rapport attend toujours une validation
humaine. Le parcours OTP de test passe par Lambda OTP et SNS sans exposer le code.

### Phase 6 — Backend principal GCP

**Responsable proposé : Ayman. Statut : prête à démarrer en préparation hors ligne ; aucun
déploiement GCP effectué.**

État transmis : FastAPI possède une image Docker non privilégiée, une sonde `/health`, des
migrations Alembic et 117 tests backend réussis. Le backend sait utiliser S3 par la chaîne
d'identifiants standard AWS. La connexion PostgreSQL accepte désormais un bundle CA, impose
`verify-full` en environnement cloud/RDS et utilise un pool borné. En revanche, aucun projet,
réseau, registre d'images, service account, secret, VM, MIG, load balancer ou NAT GCP n'a été
créé ; aucun chemin GCP→RDS n'est donc disponible.

Travail qu'Ayman peut réaliser immédiatement avec Codex, sans accès cloud :

1. Créer un module reproductible sous `infra/gcp/` pour préparer l'API Compute Engine :
   Artifact Registry, service account minimal, Secret Manager, modèle d'instance, Managed
   Instance Group, autoscaling, health check et HTTPS Load Balancer. Les valeurs de projet,
   région, domaine, image et tailles restent des variables ; `terraform fmt` et
   `terraform validate` doivent réussir, mais aucun `apply` ne doit être exécuté.
2. Préparer le démarrage de l'image FastAPI et une étape Alembic explicite et unique. Plusieurs
   instances du MIG ne doivent pas lancer des migrations concurrentes. Conserver l'utilisateur
   non privilégié et ne pas embarquer de `.env`, mot de passe ou certificat secret.
3. Prévoir le montage en lecture seule du bundle CA AWS et l'injection des secrets depuis
   Secret Manager. Documenter les variables RDS existantes et calculer la limite du pool avec
   `workers × (pool_size + max_overflow)` avant d'augmenter le nombre de workers.
4. Concevoir le réseau avec sortie stable. La cible préférée reste RDS privé avec un chemin
   réseau inter-cloud approuvé. Le repli pédagogique est un RDS public non ouvert au monde,
   autorisant uniquement l'IPv4 fixe Cloud NAT en `/32`, toujours en TLS `verify-full`.
5. Préparer l'identité inter-cloud pour S3 avec des jetons temporaires et le rôle AWS minimal
   planifié ; ne pas ajouter de clés AWS durables dans GCP ou dans le dépôt.
6. Ajouter les tests et scripts de vérification hors ligne : construction de l'image, démarrage
   sans privilèges, échec sans secret/CA, sonde de santé, validation Terraform et documentation
   de rollback/nettoyage. Ajouter `docs/testing/phase-6.md` avec uniquement les résultats
   réellement observés.

Dépendances à demander au propriétaire avant un déploiement : identifiant et région du projet
GCP, compte de facturation, rôles autorisés, budget, domaine/DNS, choix de connectivité, endpoint
RDS, utilisateur SQL applicatif, secret, bundle CA et rôle AWS fédéré pour S3. Toute création de
ressource facturable, modification IAM ou exposition réseau exige une approbation explicite.

Critères de sortie préparatoire : plans GCP relus et validés hors ligne, image reproductible,
variables/secrets documentés, migrations non concurrentes et tests locaux toujours verts.
Critère de sortie final : l'API déployée sur GCP passe `/health`, réalise les parcours métier
contre RDS avec TLS vérifié, accède à S3 avec des identifiants temporaires, n'expose aucun secret
et produit des preuves de supervision. La phase ne doit pas être marquée terminée avant ce test
réel.

### Phase 7 — Déploiement Azure

**Responsable proposé : Ayman. Statut : prête à démarrer en préparation hors ligne ; aucun
déploiement Azure effectué.**

État transmis : le portail React/TypeScript unique couvre citoyen, agent, administrateur et
validateur. Sa production est une image Nginx non privilégiée avec `/healthz`. Le navigateur
appelle actuellement `/api/v1` sur la même origine et Nginx transmet `/api/` au service Docker
local `api:8000`. Cette image est adaptée au principe d'un seul App Service, mais son upstream
est encore statique ; aucune souscription, ressource, identité ou URL Azure n'est configurée.

Travail qu'Ayman peut réaliser immédiatement avec Codex, sans accès cloud :

1. Rendre l'upstream Nginx configurable au démarrage, par exemple avec une variable
   `API_UPSTREAM`, sans inscrire l'URL GCP dans le bundle React. Conserver les appels navigateur
   sur la même origine, `/api/v1`, afin de limiter CORS et de garder la CSP `connect-src 'self'`.
   Si un appel direct navigateur→GCP est finalement retenu, ajouter côté FastAPI une allowlist
   CORS exacte et testée ; ne jamais utiliser `*` avec des données ou sessions authentifiées.
2. Ajouter des tests de conteneur pour `/healthz`, le fallback React, les en-têtes de sécurité,
   le proxy `/api/` et le comportement lorsque l'API est indisponible. Préserver les tests
   frontend existants et le workflow Docker Compose local.
3. Créer sous `infra/azure/` une préparation Terraform ou équivalente pour un seul Linux Web
   App conteneurisé, son App Service Plan, HTTPS-only, identité gérée, journaux, paramètres non
   secrets et référence sécurisée à l'image. Exécuter seulement formatage/validation/plan
   hors ligne autorisé ; aucun déploiement sans accord.
4. Documenter construction, publication de l'image, configuration, rollback et suppression.
   Ne pas créer un second portail/back-office : les rôles restent dans la même application et
   l'autorité d'accès demeure FastAPI.
5. Préparer `docs/testing/phase-7.md` et une matrice de recette pour les quatre profils, les
   téléchargements/téléversements de documents, les sessions expirées, erreurs API et routes
   React rechargées directement. Ne déclarer que les essais réellement exécutés.

Dépendances à demander au propriétaire avant un déploiement : souscription et tenant Azure,
resource group, région, budget, registre d'images choisi, domaine/DNS, identité autorisée à lire
l'image et URL HTTPS stable de l'API GCP. Le déploiement réel de la phase 7 dépend donc de la
phase 6, mais sa préparation et ses tests de conteneur peuvent avancer en parallèle.

Critères de sortie préparatoire : image frontend configurable et testée, infrastructure Azure
validée sans application, paramètres et procédure documentés, tests locaux toujours verts.
Critère de sortie final : l'unique App Service Azure sert tous les profils en HTTPS, relaie
correctement `/api/` vers GCP, passe la recette par rôle et ne contient aucun secret. La phase
ne doit pas être marquée terminée avant cette vérification réelle.

### Phase 8 — Analytique et publication

**Statut : à faire.**

- Concevoir les tables analytiques BigQuery sans données personnelles.
- Implémenter une synchronisation batch PostgreSQL/RDS vers BigQuery.
- Publier uniquement la dernière révision approuvée et éligible.
- Rendre les traitements rejouables et tracer les lots de publication.
- Créer puis vérifier le tableau de bord public Looker Studio.

Critère de sortie : une approbation déclenche ou alimente un lot contrôlé, puis seuls les
résultats publiés deviennent visibles dans Looker Studio avec une fraîcheur documentée.

### Phase 9 — Sécurité, secours et résilience

**Statut : à faire.**

- Placer Cloudflare devant l'application Azure : HTTPS, WAF, DDoS et CDN approprié.
- Configurer un point d'entrée GCP Load Balancing pris en charge.
- Déployer une API de secours compatible sur Amazon EC2.
- Étudier puis implémenter un basculement GCP vers EC2 techniquement supporté.
- Synchroniser les versions/configurations et tester des pannes contrôlées.
- Mettre en place logs, métriques, alertes, sauvegardes et procédures de restauration.

Critère de sortie : les protections et scénarios de secours sont démontrés avec leurs
limites documentées ; aucun basculement automatique n'est revendiqué sans test réel.

### Phase 10 — Recette finale et documentation

**Statut : à faire.**

- Exécuter les tests unitaires, d'intégration, de sécurité et de bout en bout.
- Vérifier l'intégrité des données, le RBAC, les coûts et les interconnexions cloud.
- Tester un PV approuvé, un PV rejeté et un événement S3 dupliqué.
- Documenter déploiement, exploitation, reprise, nettoyage et limites connues.
- Capturer des preuves vérifiables et préparer la démonstration académique.

Critère de sortie : le scénario central fonctionne de l'agent jusqu'au tableau de bord
public, sans exposer de résultat non approuvé ni de donnée privée.

## Scénario d'acceptation final

1. Un agent s'authentifie et choisit un bureau qui lui est affecté.
2. Il saisit des résultats fictifs et dépose le PV justificatif.
3. S3 conserve le fichier privé et Lambda PV traite l'événement de façon idempotente.
4. RDS conserve les résultats, encore non publiés.
5. Un validateur consulte le document et approuve ou rejette le rapport.
6. La synchronisation sélectionne uniquement une révision approuvée et l'envoie à BigQuery.
7. Looker Studio affiche les résultats publiés au public, sans information privée.

Le test final doit aussi couvrir un rejet, une correction auditable et la réception répétée
du même événement S3.

## Règles de mise à jour de cette feuille de route

- Une phase passe à **terminée** seulement lorsque ses critères sont implémentés et testés.
- Une intégration cloud reste **planifiée** jusqu'à son déploiement et sa vérification réels.
- Chaque fin de phase doit ajouter un rapport dans `docs/testing/` avec les commandes et
  résultats effectivement observés.
- Les décisions qui changent l'architecture doivent être consignées dans `docs/decisions/`.
- Les ressources payantes, SMS réels et déploiements cloud nécessitent une autorisation
  explicite avant leur création.
