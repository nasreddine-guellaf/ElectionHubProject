# Feuille de route ElectionHub V2

Dernière mise à jour : 22 novembre 2026.

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
| 5 | Données et événements AWS | ⏭️ Prochaine | RDS, S3, Lambda PV, Lambda OTP et SNS |
| 6 | Backend principal GCP | ⏳ À faire | API sur Compute Engine, Secret Manager et connexion à RDS |
| 7 | Déploiement Azure | ⏳ À faire | Frontend unique sur Azure App Service |
| 8 | Analytique et publication | ⏳ À faire | BigQuery, synchronisation et Looker Studio |
| 9 | Sécurité, secours et résilience | ⏳ À faire | Cloudflare, Load Balancing GCP, EC2 et tests de basculement |
| 10 | Recette finale et documentation | ⏳ À faire | Tests multi-cloud de bout en bout et démonstration académique |

Progression fonctionnelle : **4 phases sur 10 terminées**. Cela ne signifie pas que 40 %
de l'effort total est consommé : les déploiements et interconnexions multi-cloud restantes
comportent davantage de dépendances externes, de sécurité et de validation.

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

**Statut : prochaine phase, non démarrée.**

Travail prévu :

- Préparer le déploiement PostgreSQL sur Amazon RDS et une stratégie de migration sûre.
- Créer un stockage S3 privé et chiffré pour les PV et photographies d'incidents.
- Ajouter au backend un adaptateur de stockage compatible avec un mode local de test.
- Implémenter les téléversements contrôlés : formats, taille, métadonnées et autorisations.
- Implémenter Lambda PV, déclenchée par S3, avec traitement idempotent et reprise d'erreur.
- Implémenter Lambda OTP et l'intégration SNS dans une configuration de test approuvée.
- Ajouter les incidents et pièces jointes au modèle, à l'API et à l'interface.
- Tester les événements dupliqués, fichiers invalides, échecs partiels et nouvelles tentatives.

Prérequis : compte AWS autorisé, région cible, budget/alertes de coût, règles IAM et choix
du numéro SNS de test. Aucun SMS réel ni ressource payante ne doit être créé sans accord
explicite.

Critère de sortie : un agent dépose un PV fictif dans S3, Lambda PV traite l'événement une
seule fois logiquement, RDS reflète son état, et le rapport attend toujours une validation
humaine. Le parcours OTP de test passe par Lambda OTP et SNS sans exposer le code.

### Phase 6 — Backend principal GCP

**Statut : à faire.**

- Déployer FastAPI sur Google Compute Engine.
- Préparer un Managed Instance Group et l'autoscaling lorsque le budget le permet.
- Stocker les secrets dans Google Secret Manager et utiliser une identité de service.
- Établir une connexion TLS et restreinte entre GCP et AWS RDS.
- Configurer la supervision de santé et tester les opérations distantes.

Critère de sortie : l'API GCP réalise les parcours métier contre RDS sans secret dans le
code ni accès réseau inutile.

### Phase 7 — Déploiement Azure

**Statut : à faire.**

- Déployer l'unique application React sur Azure App Service.
- Configurer l'URL de l'API GCP, HTTPS, CORS et les variables d'environnement.
- Vérifier les parcours citoyen, agent, administrateur et validateur depuis Azure.
- Conserver une seule ressource App Service pour le portail et le back-office.

Critère de sortie : le frontend Azure communique avec l'API GCP et applique les parcours
par rôle, tandis que le backend demeure l'autorité d'accès.

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
