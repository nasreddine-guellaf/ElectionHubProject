# Rapport de vérification — Phase 2

Date : **18 novembre 2026**. Environnement Windows, Python 3.11.9,
PostgreSQL 16.16 dans Docker Desktop Linux. Aucun déploiement cloud.

## Vérification préalable du socle

Les modèles, migrations, configuration, routes, tests et état Git ont été inspectés avant
modification. `pytest -q` : **24 succès**, 1 avertissement, 1,83 s.
`ruff check .` : succès. `alembic check` : aucune différence détectée.
Le dépôt contenait les fichiers de phase 1 sans commit ; aucun commit n'a été créé ici.

La conception a été écrite dans l'ADR 0002 avant l'ajout des modèles métier.
La migration 0001 a été conservée ; la migration 0002 est additive.

## IMPLÉMENTÉ

- Scrutins, candidats/listes, participations, inscription des bureaux avec effectifs par scrutin.
- Références utilisateurs et rôles déclaratifs ; affectations d'agents.
- Dossier PV unique par scrutin/bureau, révisions numérotées et résultats par candidat.
- Snapshots des règles et effectifs, historique d'événements et table de décisions futures.
- Création DRAFT, saisie cohérente, soumission SUBMITTED et correction traçable.
- Verrous transactionnels, version d'édition attendue et contraintes de doublons.
- API locale désactivée par défaut, clé explicite et acteur configuré côté serveur.
- Seed synthétique idempotent, documentation API/base/architecture et scripts locaux.

## TESTÉ — commandes et résultats réels

Les commandes backend ont utilisé `..\.venv\Scripts\python.exe` depuis `backend/`.
Les commandes Compose et scripts ont été lancés depuis la racine.

| Commande / contrôle | Résultat |
|---|---|
| `python -m pytest -q` après tests initiaux du domaine | 59 succès, 1 avertissement, 13,08 s |
| `python -m pytest -q` avec contrôles SQL et historique complétés | **70 succès**, 1 avertissement, **15,62 s** |
| `python -m ruff check .` | Tous les contrôles passent |
| `python -m ruff format --check .` | 21 fichiers conformes |
| `python -m alembic upgrade head` | Migration 0002 appliquée à la base de démonstration, code 0 |
| `python -m alembic check` | Aucune différence de schéma |
| `python -m app.seed_domain` deux fois sur l'hôte | Succès, dossiers existants conservés |
| `docker compose config --quiet` | Configuration valide |
| `docker compose --progress plain up -d --build --wait` | Images reconstruites ; base et API saines, migration terminée avec code 0 |
| `docker compose exec api alembic check` | Aucune différence depuis l'image Linux |
| `docker compose exec api python -m app.seed_domain` | Succès, toujours 2 dossiers |
| `python scripts/smoke_phase2.py` | Uvicorn réel : santé, refus sans clé, lecture PV, CRUD scrutin et nettoyage réussis |
| HTTP GET port 8000 `/health` | 200, migration `0002_election_domain`, environnement local |
| HTTP GET port 8000 `/api/v1/polling-stations` | 200, 3 bureaux conservés |
| HTTP GET port 8000 `/api/v1/reports` sans activation | **503**, API métier bien désactivée par défaut |
| HTTP GET port 8000 `/openapi.json` | Version 0.2.0, 22 chemins documentés |
| SQL direct après seed | 1 révision DRAFT, 1 SUBMITTED ; aucun résultat approuvé/publié |
| SQL direct après tests | 0 schéma `test_%` restant |
| Ruff scripts et compilation Python | Succès ; 3 scripts formatés |
| Activation/désactivation sur un `.env` fictif dans `.local/` | Clé générée puis retirée, configuration existante conservée |
| `git check-ignore .env .venv .local` | Tous exclus de Git |

Le test HTTP crée puis supprime uniquement son scrutin synthétique temporaire. Son
serveur et sa clé sont éphémères ; il n'active pas les routes du conteneur permanent.
Les conteneurs PostgreSQL et API restent démarrés sur localhost, ports 5433 et 8000.

## Cas automatisés

Les 70 tests comprennent les 24 régressions initiales, adaptées uniquement à la version
de migration attendue et à la simulation d'une table indisponible désormais référencée.
Les nouveaux scénarios couvrent :

- CRUD scrutin, dates incorrectes, suppression référencée, pagination et UUID invalide.
- Participation des candidats, inscription des bureaux, références manquantes et affectations.
- Protection par défaut, clé absente/incorrecte, acteur inactif, identité forgée dans le corps,
  refus d'un autre auteur même affecté et présence du paramètre de clé dans OpenAPI.
- Création, saisie, soumission, nouvelle révision et conservation intégrale de la version précédente.
- Entiers stricts, négatifs, dépassement INTEGER, totaux incohérents et participation excessive.
- Candidats dupliqués, manquants ou étrangers au scrutin ; FK composite testée directement en SQL.
- Règle d'égalité des bulletins configurable et figée après premier dossier.
- États interdits, double soumission, édition périmée, double correction, absence de route d'approbation.
- Révision après rejet et conservation de la décision ; motif obligatoire de rejet en base.
- Doublons dossier, deux brouillons concurrents et contraintes CHECK directement dans PostgreSQL.
- Ordre de l'historique même lorsque les timestamps d'une transaction sont identiques.
- Deux transactions concurrentes de création : **un succès, un conflit 409**.
- Deux transactions concurrentes de saisie : **un succès, un conflit 409**, sans écrasement.
- Migration descendante/ascendante conservant un bureau de phase 1 et concordance des métadonnées.
- Seed répété sans nouvel événement, sans réinitialisation et sans approbation automatique.

## Corrections et limitations

Les premiers contrôles Ruff ont identifié des imports et lignes trop longues, corrigés
avant le contrôle final. La relecture a aussi conduit à ordonner l'historique par révision
et version d'édition, car `now()` est identique au sein d'une transaction PostgreSQL.
Les migrations générées ont été relues et mises en forme avant application locale.

Un avertissement Starlette concernant la dépréciation du client `httpx` de test subsiste,
comme en phase 1. Il n'est pas masqué et ne provoque aucun échec.
Les commandes WSL natives restent documentées mais non exécutées ; l'image Linux est testée.

L'application protège le workflow via ses services transactionnels. Les comptes PostgreSQL
locaux restent des comptes de développement : un accès SQL privilégié peut modifier des
statuts ou des compteurs hors API. La somme des résultats multi-lignes est contrôlée par
le service, pas par un trigger SQL. Les autorisations de production restent à concevoir.

Les rôles sont déclaratifs, pas des autorisations authentifiées. Aucun document PDF/image
n'est encore déposé ; la soumission phase 2 porte uniquement sur les données structurées.
Les référentiels et affectations d'un scrutin sont volontairement figés après son premier
dossier. Les corrections d'un PV approuvé/publié restent interdites.

## PLANIFIÉ — phase 3 recommandée

Implémenter les comptes authentifiés et le hachage de mots de passe, définir les droits
administrateur/agent/validateur, appliquer les portées côté API et remplacer le mécanisme
de clé locale. Introduire les décisions humaines autorisées avec traçabilité et tests de
séparation des rôles. Préparer le workflow citoyen CIN fictive/OTP sans SMS réel.

Les dépôts S3, Lambda PV/OTP, SNS, RDS distant, Azure, GCP, BigQuery, Looker Studio,
Cloudflare et la bascule EC2 restent planifiés dans leurs phases respectives.
