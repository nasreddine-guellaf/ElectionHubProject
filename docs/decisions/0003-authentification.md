# ADR 0003 — Authentification et autorisations, phase 3

Date : 18 novembre 2026. Finalisation : 21 novembre 2026.
Implémentation locale, sans infrastructure cloud.

- La clé `X-Development-Key` est retirée, sans voie de contournement ni secours.
- Mots de passe Argon2id (64 MiB, 3 itérations, parallélisme 1), sel aléatoire fourni
  par la bibliothèque. Aucun mot de passe par défaut ou stocké en clair en base.
- Sessions opaques aléatoires de 256 bits, transmis par `Authorization: Bearer`, jamais
  par URL/cookie. Seul SHA-256 du jeton est enregistré. Expiration absolue, logout,
  révocation de toutes les sessions après changement de mot de passe/rôle/activation.
  Le rôle et l'état actif sont relus côté serveur à chaque requête.
- Un rôle effectif par compte dans ce jalon : ADMIN, AGENT, VALIDATOR ou CITIZEN.
  Les références à plusieurs rôles échouent fermées ; aucune élévation implicite.
- ADMIN : référentiels, affectations, comptes, lecture opérationnelle et audit ; pas
  de création/saisie/soumission ni décision sur les PV. AGENT : lectures de référence,
  ses affectations et ses propres dossiers dans ses bureaux. VALIDATOR : PV courants
  non brouillons, sur tous les scrutins de démonstration ; aucune auto-validation.
  CITIZEN : uniquement son profil fictif et son bureau via une route dédiée.
- Les lectures publiques héritées des bureaux restent un référentiel synthétique sans
  donnée personnelle ni résultat. Les résultats/historiques nécessitent authentification.
- Décision humaine : SUBMITTED → PENDING_VALIDATION par action explicite du validateur,
  puis APPROVED ou REJECTED avec motif pour rejet. Contrôle de cohérence et verrous,
  `expected_version`, conservation des décisions et événements. La validation phase 3
  porte sur les résultats structurés ; documents S3/Lambda restent phase 5. Aucune publication.
- Login limité par identifiant et IP dans PostgreSQL (partagé entre processus), erreurs
  uniformes, vérification Argon2 factice pour un compte absent. Pas de confiance dans
  X-Forwarded-For fourni par le client. Politique proxy à configurer au déploiement.
- OTP citoyen optionnel, désactivé par défaut : CIN strictement `DEMO-CIN-*`, code sécurisé
  à six chiffres, durée 5 minutes, cinq essais maximum, usage unique et invalidation des
  anciens codes. HMAC avec secret local pour l'état temporaire ; livraison dans une boîte
  SMS fictive locale, jamais dans une réponse API ni un journal. Lambda/SNS non intégrés.
- Bootstrap CLI explicite : comptes fictifs liés aux références existantes, secrets
  aléatoires sauvegardés dans `.local/` ignoré par Git, aucun secret affiché. Ne réinitialise
  pas les comptes existants. Créations/modifications ultérieures réservées à ADMIN.
- Le dernier administrateur actif ne peut être désactivé/rétrogradé ; un administrateur
  ne modifie pas son propre rôle/activation. Les modifications sont auditées.

Sources : [OWASP stockage des mots de passe](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[argon2-cffi](https://argon2-cffi.readthedocs.io/en/stable/api.html).

Limites : TLS/domaine/proxy, récupération de mot de passe, MFA personnel, gestion des
secrets cloud et entretien des historiques expirés seront traités avant exposition distante.
Le backend reste limité aux environnements local/test. Aucun frontend dans cette phase.
