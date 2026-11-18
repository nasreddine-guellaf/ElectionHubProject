# ADR 0002 — Domaine électoral local et PV révisables

Date : 18 novembre 2026. Périmètre : phase 2 uniquement.
Conception consignée avant l'implémentation ; elle n'ajoute aucun service cloud.

## Relations retenues

- `elections` : scrutin fictif, dates et règle configurable d'égalité des bulletins.
- `polling_stations` : référentiel de phase 1 conservé sans modifier sa migration.
- `election_stations` : inscription d'un bureau à un scrutin, avec nombre d'inscrits
  propre au scrutin. Le compteur historique du bureau reste compatible avec la phase 1.
- `candidates` et `election_candidates` : identité fictive réutilisable et participation
  au scrutin. Les candidats ne représentent pas des choix individuels enregistrés.
- `user_references` et `user_roles` : identités synthétiques et rôles déclaratifs préparant
  la phase 3. Aucun mot de passe, session ou autorisation RBAC n'est implémenté ici.
- `agent_assignments` : référence utilisateur affectée à un couple scrutin/bureau.
- `reports` : dossier unique pour un scrutin et un bureau ; auteur et révision courante.
- `report_revisions` : version numérotée du PV, état, compteurs, auteur, dates, motif de
  correction et version d'édition pour détection des modifications concurrentes.
- `report_results` : total entier par candidat d'une révision ; les clés étrangères
  composites imposent que le candidat et le PV appartiennent au même scrutin.
- `report_events` : historique des créations, modifications, soumissions et révisions.
- `report_validations` : décisions humaines futures, reliées à une révision et à un
  validateur ; motif obligatoire pour un rejet. Aucune API de décision dans cette phase.

**Granularité : un PV métier = une élection + un bureau + un numéro de révision.**
Le dossier est son identité stable. Les résultats d'anciennes révisions ne sont jamais
fusionnés ni comptés comme un autre bureau. Aucun total publié n'est produit en phase 2.

## Cycle de vie et concurrence

Transition accessible maintenant : `DRAFT → SUBMITTED`, après vérification complète.
Les états `PROCESSING`, `PENDING_VALIDATION`, `APPROVED`, `REJECTED`, `PUBLISHED` et
`PROCESSING_FAILED` sont réservés dans le modèle. Aucun endpoint de changement arbitraire
d'état. Les transitions de traitement, décision humaine et publication restent planifiées.

Une correction d'un PV `SUBMITTED`, `REJECTED` ou `PROCESSING_FAILED` crée une nouvelle
révision `DRAFT`, avec copie des compteurs/résultats et motif obligatoire. L'ancienne reste
inchangée. Révision d'un PV approuvé/publié interdite tant que les règles de retrait et
de republication ne sont pas conçues. Un seul brouillon par dossier (index unique partiel).

Chaque mutation verrouille le dossier ; le numéro de révision doit être courant et
`expected_version` doit correspondre à la version d'édition. Une requête obsolète retourne
409, y compris une double soumission ou une double création de révision. Unicité en base
et verrous protègent également les créations concurrentes.

## Règles et configuration

Entiers stricts entre 0 et 2 147 483 647 pour tous les nombres : pas de flottants, booléens
ou négatifs. Tous les candidats du scrutin doivent être représentés exactement une fois
dans une saisie complète. Leur somme égale les voix valides ; voix valides ≤ bulletins
déposés ≤ inscrits. Par défaut, voix valides + blancs + nuls = bulletins déposés.
Seule cette dernière égalité est configurable par scrutin, pour un règlement fictif
différent. Les référentiels d'un scrutin sont figés dès son premier dossier PV pour
préserver l'interprétation historique des révisions. Le snapshot des inscrits et de la
règle est conservé dans chaque révision.

## Protection provisoire

Toutes les nouvelles routes, y compris les historiques, nécessitent `DEV_API_ENABLED=true`,
une clé locale `DEV_API_KEY` d'au moins 32 caractères et un `DEV_ACTOR_ID` configuré côté
serveur. Le client transmet uniquement `X-Development-Key`, jamais une identité ou un rôle
faisant autorité. L'acteur doit être une référence active et être affecté au bureau pour
créer ou modifier ses PV. Ce mécanisme est un outil local de développement, pas du RBAC.
Les ports Compose restent sur localhost. Aucun mode production n'est accepté.

## Erreurs et données

Nouvelles erreurs métier : JSON `{"detail": "message français"}` ; 404 absent, 409 conflit,
422 incohérence, 403 clé incorrecte, 503 développement désactivé ou base indisponible.
Les erreurs de validation ne renvoient ni valeurs saisies ni secrets.
Le contrat des lectures de phase 1 est conservé. Listes paginées, UUID, dates UTC.
Pas de suppression de dossier PV ni de révision ; élections supprimables uniquement si
non référencées. Seeds déterministes et idempotents, sans modifier les objets existants.
