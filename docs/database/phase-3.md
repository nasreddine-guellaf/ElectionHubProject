# Extension de sécurité — Phase 3

Migration additive `0003_authentication`, après les deux migrations métier préservées.

| Table | Relation / données | Protection |
|---|---|---|
| `accounts` | Un compte par user_reference, username unique | Mot de passe Argon2id avec sel ; jamais exposé par l'API |
| `auth_sessions` | Empreinte SHA-256 du jeton, utilisateur, dates | Jeton aléatoire brut absent de la base ; expiration et révocation |
| `auth_audit` | Acteur, cible utilisateur facultative, action, ressource, date | Aucun secret ni corps de requête ; lecture ADMIN |
| `auth_rate_limits` | Clé hachée, nombre d'essais, expiration | Upsert atomique, partagé entre instances |
| `citizens` | Référence synthétique, CIN DEMO, bureau, destination mock | Pas de CIN réelle ni téléphone ; route personnelle seulement |
| `otp_challenges` | Défi UUID, utilisateur optionnel, HMAC, essais, dates | 5 essais maximum, consommation atomique sous verrou |

Les tables réutilisent `user_references`, `user_roles`, `agent_assignments` et les bureaux
existants. Les rôles actuels sont relus à chaque requête ; une configuration multirôle
est refusée plutôt que fusionnée implicitement. La gestion des comptes n'efface jamais
une référence déjà utilisée par les résultats ou les audits.

Le CHECK de `report_events.action` est étendu par la migration 0003 avec REVIEW_STARTED,
APPROVED et REJECTED. Les migrations 0001 et 0002 ne sont pas réécrites. Une descente vers
0002 échoue transactionnellement si de tels événements existent, pour ne pas les effacer.
Sans décisions, la descente supprime les tables d'authentification ; elle est donc réservée
aux schémas de test jetables et ne constitue pas une stratégie de retour arrière en production.

Les validations humaines restent dans `report_validations` avec unicité par révision et
motif obligatoire pour rejet. Le dossier et la révision sont verrouillés pour empêcher
deux décisions simultanées ou la décision d'une ancienne version.

Préservation : les seeds métier ne rétablissent pas un ancien rôle lorsqu'un rôle existe
déjà. Le bootstrap crée uniquement les comptes manquants et ne change ni leurs mots de
passe existants ni leur activation. La génération locale de secrets est distincte des
migrations et des données de démonstration versionnées.
