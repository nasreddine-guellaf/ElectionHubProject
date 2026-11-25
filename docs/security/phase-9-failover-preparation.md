# Préparation locale du failover OCI vers AWS

État : configuration préparée, aucun backend cloud ni mécanisme de basculement réel testé.

## Sondes de santé du backend

Le backend existant expose `GET /health`. Il contrôle PostgreSQL, la révision Alembic et
la lecture des tables métier avant de répondre `200`; une dépendance indisponible produit
`503`. Le contrat accepte les environnements `local`, `test` et `cloud`.

Valeurs de départ proposées pour les sondes actives OCI Load Balancer et le monitoring AWS :

| Paramètre | Valeur initiale |
|---|---|
| Chemin et méthode | `GET /health` |
| Code attendu | `200` |
| Intervalle | 30 secondes |
| Timeout | 5 secondes |
| Seuil d'échec | 3 échecs consécutifs |
| Protocole | HTTPS sur les origines publiques ; HTTP seulement sur réseau local isolé |

Ces paramètres sont des valeurs de préparation. Ils ne sont configurés dans aucun compte
cloud et doivent être ajustés selon les limites de services, la latence et l'objectif de
récupération retenus par les responsables OCI/AWS.

Les sondes actives OCI ou AWS déterminent l'état connu par ces services de monitoring ou de
load balancing ; elles ne transmettent pas de signal de santé à ce Nginx. Le fichier de
configuration Nginx s'appuie sur l'échec passif des requêtes réelles (`max_fails`,
`fail_timeout` et `proxy_next_upstream`). Il n'existe donc pas de lien direct entre l'état de
la sonde OCI et le choix du backend AWS dans Nginx.

## Journaux d'accès Nginx

Nginx écrit un enregistrement JSON par requête vers stdout avec l'heure ISO 8601, la méthode,
le statut client, l'adresse du backend, son statut et son temps de réponse. L'adresse upstream
correspond à `API_PRIMARY` ou `API_BACKUP` et permet d'identifier l'origine sélectionnée.
Quand une requête est retentée, Nginx peut fournir plusieurs valeurs séparées par des virgules
dans les champs upstream.

Le format n'inclut ni URI, ni query string, ni en-têtes, ni corps de requête. Il ne journalise
donc ni mots de passe, sessions Bearer, jetons OTP, données personnelles ni contenu des PV.
Les logs des origines doivent appliquer une règle de minimisation équivalente. En cloud, le
collecteur devra limiter les accès, définir la rétention et éviter l'export de données sensibles.

## Fonctionnement prévu

Le conteneur Nginx du frontend utilise `API_PRIMARY` pour le backend OCI et `API_BACKUP`
pour l'API AWS de secours. La seconde adresse est déclarée `backup` : elle ne reçoit pas
de trafic normal et n'est sélectionnée que lorsqu'une tentative vers le primaire échoue
selon les conditions Nginx configurées.

En local, les valeurs par défaut restent `api:8000` pour les deux adresses, avec HTTP.
Pour un futur environnement, définir les noms DNS privés/stables ou les endpoints approuvés :

```dotenv
API_SCHEME=https
API_PRIMARY=api-oci.example.invalid:443
API_BACKUP=api-aws.example.invalid:443
API_TLS_NAME=api.example.invalid
```

`API_TLS_NAME` est le nom TLS commun présenté par les deux origines. Les deux services
doivent présenter un certificat valide pour ce nom et accepter un en-tête `Host` compatible.
Les noms d'exemple `.invalid` sont réservés et ne résolvent pas. Aucun domaine n'est requis
pour les essais locaux.

## Requêtes d'écriture

La configuration ne contient jamais l'option Nginx `non_idempotent`. Ainsi, si Nginx a déjà
transmis un POST/PUT/PATCH/DELETE au backend et ne reçoit pas sa réponse, il ne le renvoie
pas vers le backend de secours. Cela évite qu'une création de dossier ou une soumission soit
répétée après un résultat incertain. Si la connexion primaire échoue avant que la requête
ait été envoyée, Nginx peut néanmoins essayer le backup ; le backend n'a alors pas reçu la
mutation. Ce comportement doit être confirmé sur la version d'image finalement retenue.

Un client peut recevoir une erreur au lieu d'un succès lors d'une panne pendant une mutation.
La reprise doit alors être décidée par l'utilisateur ou par une API munie d'une vraie clé
d'idempotence persistée. Ne pas ajouter de retry frontend automatique.

## Préparation des tests

Les futurs tests de conteneur devront créer deux APIs locales temporaires, sans base métier :

1. Primaire saine : vérifier qu'une requête atteint uniquement OCI (primaire simulé).
2. Primaire hors service avant connexion : vérifier le routage vers AWS (backup simulé).
3. Primaire reçoit une mutation puis coupe la réponse : vérifier qu'AWS ne reçoit aucun second
   POST/PUT/PATCH/DELETE.
4. Primaire retourne 502/503 sur un GET : vérifier la tentative du backup et le nombre de
   tentatives borné à deux.
5. Les deux origines indisponibles : vérifier une erreur 502/504, sans boucle ni cache.
6. TLS : faire échouer le nom/SAN de certificat et confirmer l'échec fermé.
7. Contrôler que `/api/*` n'est jamais mis en cache et que les en-têtes de sécurité restent
   présents sur les réponses du frontend.

Le failover automatique n'est pas déclaré fonctionnel avant l'exécution et l'enregistrement
de ces tests avec la même version Nginx que celle déployée.

## Configuration à l'origine

Le routage du frontend n'établit pas à lui seul l'équivalence des deux backends. Avant tout
test réel, les responsables OCI/GCP et AWS doivent confirmer :

- accès privé ou filtré aux deux APIs depuis l'environnement Azure ;
- TLS, certificats, SNI et noms d'hôte des deux origines ;
- version et migrations compatibles, mêmes secrets applicatifs et mêmes paramètres ;
- base transactionnelle commune ou stratégie de synchronisation écrite et mesurée ;
- comportement de session, OTP, stockage documentaire et limites de requêtes ;
- budget de la capacité standby, responsabilités d'astreinte et retour au primaire.

Une sauvegarde AWS séparée ne peut pas accepter correctement des écritures si elle ne partage
pas l'état PostgreSQL courant ou si sa réplication n'est pas démontrée. Nginx ne réplique pas
les données et ne garantit pas la cohérence après basculement.

## Commandes locales

Valider le YAML sans démarrer de conteneur :

```powershell
$env:POSTGRES_PASSWORD = 'temporary-local-validation-password'
docker compose config --quiet
```

Quand le moteur Docker est disponible, construire le frontend et valider la syntaxe générée :

```powershell
docker compose build web
docker compose run --rm --no-deps web nginx -t
```

Remplacer les valeurs d'environnement par deux services HTTP temporaires et lancer les sept
cas de test ci-dessus avant d'utiliser des endpoints réels.
