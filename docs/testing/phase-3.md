# Vérifications phase 3 — 21 novembre 2026

## Environnement et résultats

Windows PowerShell, Python 3.11 dans `.venv`, PostgreSQL 16 dans Docker Desktop
(conteneurs Linux). Les tests utilisent des schémas PostgreSQL isolés, supprimés à
leur fin ; les tables de démonstration restent en place.

| Vérification exécutée | Résultat |
|---|---|
| `python -m pytest -q` depuis `backend/` | **94 passed**, 1 avertissement, 60,25 s |
| `ruff check .` et `ruff format --check .` dans `backend/` | Réussite, 30 fichiers formatés |
| Ruff sur `scripts/` | Vérifié après formatage |
| `alembic upgrade head` puis `alembic check` sur la base locale | Migration 0003, aucun écart de modèle |
| Bootstrap exécuté deux fois sur la base locale | Réussite, comptes existants conservés |
| `scripts/smoke_phase3.py` avec Uvicorn et HTTP réels | Connexion des trois rôles, refus d'accès, CRUD temporaire et révocation réussis |
| `docker compose config --quiet` et reconstruction `up -d --build --wait` | Réussite, migration terminée avec code 0, API et base saines |
| HTTP sur l'API Docker `127.0.0.1:8000` | Version 0.3.0, migration 0003, trois rôles et déconnexion vérifiés |
| `pip check` et `alembic check` dans le conteneur API | Dépendances cohérentes, aucun écart de schéma |
| Simulation OTP avec boîte de réception sur disque | Demande, vérification, bureau citoyen, refus des PV, usage unique et logout réussis |
| `configure_otp.py --enable` puis `--disable` sur une copie isolée | Préserve la configuration de base, génère/retire la clé OTP et retire les anciennes clés de développement |

Le parcours HTTP Docker a confirmé la conservation des **3 bureaux et 2 dossiers PV**.
Les tests HTTP temporaires suppriment leur scrutin et révoquent leurs sessions ; les
événements d'audit et compteurs de tentatives sont conservés. Le test de simulation
utilise une configuration temporaire et des fichiers sous `.local/phase3-verification/`.
Il ne modifie pas `.env`. L'API Docker est laissée en fonctionnement avec OTP désactivé.

## Couverture de sécurité et métier

- Connexion par mot de passe Argon2id, empreinte de session en base, expiration,
  logout et révocation après changement de mot de passe, rôle ou activation.
- Identifiants absents/incorrects et comptes inactifs, erreurs uniformes et limites
  d'essais ; absence de contournement par l'ancienne clé de développement.
- Comptes et audit réservés à ADMIN ; agent limité à ses propres dossiers affectés ;
  citoyen exclu des API opérationnelles ; configuration multirôle refusée.
- Revue et décision réservées à VALIDATOR, impossibilité d'auto-validation, motif
  obligatoire de rejet, recontrôle des totaux, conservation de l'historique.
- Deux décisions concurrentes : une réussite et un conflit ; deux utilisations
  concurrentes d'un OTP : une seule session délivrée.
- OTP expiré, essais épuisés, renvoi invalidant l'ancien défi, référence inconnue,
  simulation désactivée et code à usage unique.
- Bootstrap importable en processus autonome, création de comptes absents et
  vérification qu'une nouvelle exécution ne modifie pas les mots de passe existants.
- Régressions phases 1 et 2 : référentiels, contraintes PostgreSQL, résultats,
  révisions, conflits d'édition, migrations et seeds idempotents.

Le démarrage autonome du bootstrap a révélé un import manquant du modèle de bureau.
Il a été corrigé et couvert par un test en sous-processus. Le lancement Uvicorn fourni
désactive les en-têtes de proxy pour que les limites IP utilisent le pair réseau local.

## Limites observées

Un avertissement Starlette signale la dépréciation de l'intégration `httpx` du client
de test ; il n'entraîne aucun échec. La migration vers `httpx2` n'est pas réalisée ici.
Les commandes WSL natives sont documentées mais n'ont pas été exécutées dans une
distribution WSL utilisateur ; l'image Linux Docker a été construite et testée.

Les tests ne constituent pas un audit de sécurité de production ni un test de charge.
TLS, proxys cloud de confiance, récupération de compte et entretien des sessions,
limites et historiques expirés restent à préparer avant exposition distante.
Les fichiers de secrets et boîtes SMS sous `.local/` restent réservés au développeur.

**IMPLÉMENTÉ / TESTÉ :** authentification et permissions locales, revue humaine des
résultats structurés, simulation OTP. **PLANIFIÉ :** frontend React (phase 4), pièces
justificatives et AWS (phase 5), déploiements multi-cloud, analytics et publication.
Aucune ressource cloud n'a été provisionnée et aucun SMS réel n'a été envoyé.
