# Phase 9.1 — Audit de sécurité

Date : 24 novembre 2026. Branche : `feat/phase-9-security`.
Révision auditée : `b9b6bdfcea58021f0d957fd49689508249000ba3`.

## Portée et méthode

Cet audit initial couvre le code FastAPI et React, le contrôle d'accès, les sessions,
les secrets, les pièces justificatives, les dépendances, les Dockerfiles et le déploiement
Docker Compose local. Il ne constitue ni un test d'intrusion externe, ni une qualification
des services cloud, ni une preuve de résilience multi-cloud.

L'audit a combiné la lecture de l'architecture et des contrats RBAC, l'inspection des routes,
modèles, tests et images, les linters, les audits de dépendances et une recherche de secrets.
Aucune ressource cloud n'a été créée. Aucun `terraform apply` n'a été exécuté. Les fichiers
`infra/aws/` et le plan AWS-4B n'ont pas été modifiés.

## Découpage de la phase 9

| Sous-phase | Objet | État après cet audit | Dépendances principales |
|---|---|---|---|
| 9.1 | Audit de sécurité | Audit initial documenté ; revalidation PostgreSQL/Docker requise | Environnement local avec moteur Docker actif |
| 9.2 | Protection Cloudflare | Non commencée | Domaine, endpoint Azure, compte et plan Cloudflare approuvés |
| 9.3 | Réseau et IAM multi-cloud | Non commencée | Responsables AWS, GCP et Azure ; topologie et identités approuvées |
| 9.4 | Backend de secours AWS EC2 | Non commencée | Image stable, RDS privé joignable, budget et IAM approuvés |
| 9.5 | Failover GCP vers AWS | Non commencée | 9.2 à 9.4 et mécanisme officiellement pris en charge |
| 9.6 | Monitoring, sauvegardes et restauration | Non commencée | Services déployés, objectifs RPO/RTO et destinations d'alerte |
| 9.7 | Tests de résilience et documentation | Non commencée | Environnements réels et procédures 9.2 à 9.6 |

La flèche GCP vers EC2 reste une intention d'architecture. Cet audit ne revendique aucun
basculement automatique.

## Contrôles existants confirmés par inspection

### Authentification, sessions et RBAC

- Les mots de passe utilisent Argon2id avec un coût explicite. Les schémas Pydantic utilisent
  `SecretStr` pour éviter leur représentation accidentelle.
- Les jetons de session contiennent 256 bits aléatoires. Seule leur empreinte SHA-256 est
  conservée en base. Les jetons passent par `Authorization: Bearer`, pas par cookie ni URL.
- Le backend relit l'activation et le rôle à chaque requête. Un compte multirôle échoue fermé.
- Les changements de mot de passe, de rôle ou d'activation révoquent les sessions concernées.
- La matrice serveur sépare ADMIN, AGENT, VALIDATOR et CITIZEN. L'interface ne constitue pas
  une autorité de sécurité.
- Les tests existants couvrent le contournement par ancienne clé, l'usurpation d'acteur,
  la portée des agents, la décision réservée au validateur, l'absence d'auto-validation et
  le refus d'un compte multirôle. Ils ont été collectés, mais leur exécution complète a été
  bloquée sur ce poste faute de PostgreSQL actif.

### Limitation, erreurs et audit

- Les limites de connexion et d'OTP sont atomiques et partagées dans PostgreSQL.
- Uvicorn ignore les en-têtes proxy et Nginx efface `X-Forwarded-For` en local. Un client ne
  peut donc pas choisir directement l'adresse utilisée par les limites locales.
- Les erreurs SQL et de validation deviennent des messages génériques. SQLAlchemy masque les
  paramètres de requête.
- Le journal d'audit ne stocke ni corps HTTP ni jeton. Sa lecture est réservée à ADMIN.

### Secrets, stockage et exposition locale

- `.env`, `.local`, les états Terraform et les clés usuelles sont ignorés par Git et par le
  contexte Docker. La recherche n'a trouvé aucun secret exploitable versionné ; les valeurs
  trouvées dans les tests sont explicitement fictives.
- Le mot de passe PostgreSQL factice de `.env.example` est rejeté par la configuration.
- RDS ou `APP_ENV=cloud` imposent `verify-full` et un bundle CA valide.
- S3 utilise la chaîne d'identité standard du SDK ; aucune clé AWS statique n'est intégrée.
- Les ports locaux PostgreSQL, API et web sont liés à `127.0.0.1`.
- Les objets privés ont des clés générées par le serveur. Les traversées de chemin sont
  refusées et les téléchargements repassent par le RBAC.

### Frontend et conteneurs

- React conserve le jeton uniquement en mémoire, avec `credentials: omit` et `no-store`.
- Nginx applique une CSP restrictive, `nosniff`, `no-referrer`, masque sa version et interdit
  l'intégration en frame via `frame-ancestors 'none'`.
- Les images API et web utilisent des utilisateurs non privilégiés. Le service web possède
  un système de fichiers en lecture seule et un `/tmp` séparé.
- Compose lie les ports à la boucle locale, attend les sondes de santé et sépare migration,
  initialisation du volume et exécution de l'API.

## Registre des risques

| ID | Niveau | Constat | Recommandation | Traitement prévu |
|---|---|---|---|---|
| SEC-01 | Élevé | Les dépôts PDF/JPEG/PNG vérifient seulement le type déclaré, la taille et les premiers octets. Un polyglotte ou un PDF actif peut franchir ce contrôle ; aucun antimalware n'est présent. | Valider la structure, refuser le contenu actif, placer les objets en quarantaine et scanner avant mise à disposition. | Correctif local après validation ; scanner à coordonner avec AWS |
| SEC-02 | Élevé | `HealthRead.environment` accepte seulement `local` et `test`, alors que la configuration accepte `cloud`. La sonde peut échouer lors d'un futur déploiement cloud malgré une base saine. | Ajouter `cloud` au contrat et un test de sonde avant les phases 6 et 9. | Backend/GCP |
| SEC-03 | Élevé | Cloudflare, WAF, TLS public, DDoS, filtrage d'origine et failover ne sont pas déployés. | Ne pas exposer le système avant 9.2–9.5 et une recette réelle. | Bloqué par Azure/GCP/Cloudflare |
| SEC-04 | Élevé | Le secret PostgreSQL local passe par l'environnement Compose. Ce mécanisme serait visible aux opérateurs du moteur s'il était réutilisé en cloud. | Conserver `.env` uniquement en local ; injecter des secrets gérés et des identités de workload minimales. | Coordination AWS/GCP/Azure en 9.3 |
| SEC-05 | Élevé | RDS est planifié Single-AZ avec une rétention courte et aucune restauration n'a été exécutée. Les deux backends dépendraient de la même base. | Définir RPO/RTO, faire approuver coût et topologie, puis prouver une restauration isolée. | AWS et 9.6 |
| SEC-06 | Moyen | Les tags d'images de base sont mutables et aucun scan d'image, SBOM ou signature n'est automatisé. | Épingler des digests validés, scanner les deux images, générer une SBOM et définir leur mise à jour. | Local/CI puis registres cloud |
| SEC-07 | Moyen | Aucun workflow CI de `pip-audit`, `npm audit`, analyse statique ou scan de conteneur n'existe. | Ajouter des contrôles reproductibles et bloquants, avec procédure d'exception datée. | Local/CI après validation |
| SEC-08 | Moyen | L'API n'ajoute globalement que `Cache-Control: no-store`. Les autres en-têtes sont servis par Nginx ; HSTS dépendra du futur bord TLS. | Définir les responsabilités entre application, Azure et Cloudflare, puis tester le chemin public final. | Local puis 9.2 |
| SEC-09 | Moyen | La politique de proxy de confiance n'est pas définie. Sans adaptation, les limites verront le proxy ; une confiance trop large permettrait l'usurpation d'IP. | Définir précisément les proxys et plages de confiance, puis tester l'adresse effective. | 9.2–9.3 |
| SEC-10 | Moyen | Cinq échecs sur un identifiant suffisent à le bloquer 15 minutes ; un tiers peut provoquer un déni de service ciblé. Les succès sont aussi comptés. | Revoir les seuils, distinguer les succès et ajouter backoff/alerte sans affaiblir l'anti-bruteforce. | Local et 9.2 |
| SEC-11 | Moyen | Les sessions, compteurs et défis OTP expirés n'ont pas de tâche d'entretien. Les SMS fictifs restent sur disque. | Définir une rétention et une purge idempotente, avec métrique d'échec. | Local puis 9.6 |
| SEC-12 | Moyen | Les audits ne sont ni immuables, ni exportés, ni associés à une politique de rétention et d'alerte. | Centraliser sans corps ni secrets, restreindre l'écriture et surveiller les actions sensibles. | 9.6 |
| SEC-13 | Moyen | Le personnel n'a pas de MFA et aucune récupération de compte n'est définie. | Exiger une MFA adaptée pour ADMIN/VALIDATOR et une récupération à double contrôle. | Identité/provider avant exposition |
| SEC-14 | Moyen | L'API et la migration ne déclarent pas `read_only`, `no-new-privileges`, suppression de capacités ou limite de processus dans Compose. | Tester ces restrictions sans casser Alembic, le stockage privé et le simulateur OTP. | Local après validation |
| SEC-15 | Faible | `/health` révèle l'environnement et la migration. `/docs` et OpenAPI sont publics sur l'API locale. | Séparer liveness/readiness, réduire la réponse publique et décider l'exposition de la documentation. | Backend/GCP |
| SEC-16 | Faible | Bandit signale `urlopen` et les `assert` du smoke test. L'URL est limitée à `127.0.0.1`, donc B310 n'est pas exploitable ici ; les `assert` disparaissent avec `python -O`. | Remplacer les assertions par des échecs explicites ou documenter une exclusion ciblée. | Local |
| SEC-17 | Faible | `README.md` annonce la migration `0003` alors que le code attend `0004_private_documents`. | Corriger la documentation pour éviter un diagnostic erroné. | Documentation locale |

## Résultats réellement observés

| Vérification | Résultat |
|---|---|
| `ruff check .` et `ruff format --check .` dans `backend/` | Réussite ; 39 fichiers conformes |
| Pytest configuration/RDS sans connexion | **16 tests réussis**, 1 avertissement de dépendance |
| Collecte Pytest complète | **117 tests collectés** |
| Suite backend complète | Bloquée avant le premier test : PostgreSQL indisponible sur `127.0.0.1:5433` |
| `npm test` | **19 tests réussis** |
| `npm run build` | Réussite ; build Vite produit |
| `npm audit --audit-level=high` | **0 vulnérabilité connue** |
| `pip-audit -r backend/requirements.lock --strict` | **0 vulnérabilité connue** |
| Bandit sur `backend/app` et `scripts` | 0 élevé, 1 moyen, 14 faibles ; B310 concerne le smoke test local décrit dans SEC-16 |
| Recherche de secrets versionnés | Aucun secret exploitable observé ; valeurs de test et placeholders seulement |
| `docker compose config --quiet` | Réussite avec un mot de passe temporaire fourni au processus |
| Build et scan des images | Bloqués : client Docker présent, moteur Linux indisponible |

Les audits de dépendances décrivent l'état des bases consultées le 24 novembre 2026 ; ils ne
garantissent pas l'absence de vulnérabilité inconnue. La suite complète avait historiquement
117 tests réussis selon `docs/testing/phase-5.md`, mais ce résultat historique n'est pas
présenté comme une nouvelle exécution.

## Décision de passage

La sous-phase 9.1 constitue un **audit initial documenté**, pas une homologation. Avant sa
clôture définitive, il faut :

1. exécuter les 117 tests avec PostgreSQL 16 et le moteur Docker actifs ;
2. construire et scanner les deux images ;
3. valider le classement et l'ordre de correction de SEC-01 à SEC-17 ;
4. appliquer les correctifs locaux approuvés dans un lot séparé avec leurs tests ;
5. désigner les responsables AWS, GCP et Azure pour les risques dépendants des fournisseurs.

La prochaine sous-phase reste 9.2, mais aucun travail 9.2 ne doit commencer avant validation
explicite de ce rapport.
