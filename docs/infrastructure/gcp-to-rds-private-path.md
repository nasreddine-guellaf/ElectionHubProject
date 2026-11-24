# Plan — chemin privé GCP → RDS (à relire avant tout déploiement)

Date : 24 novembre 2026. **Proposition uniquement.** Aucun `apply`, aucune ressource créée,
aucune modification de `infra/aws/`. RDS reste privé (`publicly_accessible = false`).

Jalon visé : **une instance API sur GCP répond `/health` 200 contre le RDS privé existant**.
Ensuite seulement, Azure pointe vers l'API GCP.

## 1. Point de départ vérifié dans le dépôt

| Élément | État (lu dans `main`) |
|---|---|
| RDS | PostgreSQL 16.15, privé, `rds.force_ssl=1`, CA `rds-ca-rsa2048-g1`, déployé et vérifié par Nasr |
| VPC AWS | `10.40.0.0/16` ; sous-réseaux base `10.40.10.0/24` et `10.40.11.0/24`, **sans route Internet** |
| Groupe de sécurité RDS | ingress 5432 uniquement depuis le runner (temporaire) et l'API de secours EC2 ; aucun egress |
| API de secours EC2 | sous-réseau `10.40.30.0/24`, joint RDS en TLS : preuve que le chemin privé + `verify-full` fonctionne **dans** le VPC |
| Code GCP / Azure | dans `main` (fusion `ae8f91f`) : `infra/gcp/`, `infra/azure/`, validés hors ligne |
| Secret applicatif | dans AWS Secrets Manager ; l'injection dans GCP Secret Manager est une étape manuelle prévue |
| Site-to-Site VPN AWS | **non disponible** sur le compte simplifié (`docs/infrastructure/aws-3-plan.md`), à reconfirmer |

Plages à ne pas faire chevaucher : AWS `10.40.0.0/16`, GCP `10.20.0.0/24` (sous-réseau API de
`infra/gcp`), tunnel `10.99.0.0/29` (proposé ci-dessous).

## 2. Options étudiées

| # | Option | RDS reste privé | Coût indicatif | Verdict |
|---|---|:---:|---|---|
| A | **Tunnel WireGuard** entre une petite passerelle AWS et une petite passerelle GCP | oui | ≈ 17 USD/mois | **Recommandée** |
| B | AWS Site-to-Site VPN + GCP HA VPN (géré) | oui | ≈ 70+ USD/mois | Bloquée : non disponible sur le compte |
| C | Service HTTPS intermédiaire en AWS qui possède l'accès SQL | oui | calcul + développement | Trop de code et un nouveau contrat |
| D | NLB/TCP public filtré devant RDS | **non** (chemin public vers la base) | ≈ 20 USD/mois | Contredit AWS-4B |
| E | Port-forward SSM depuis GCP | oui | faible | Fragile : exige des identifiants AWS durables ou fédérés sur chaque VM |

## 3. Option recommandée : tunnel WireGuard avec SNAT côté AWS

```text
VM API GCP (10.20.0.x, sans IP publique)
   │ TCP 5432 vers l'adresse privée de RDS (route statique 10.40.10.0/23)
   ▼
Passerelle GCP (e2-micro, IP forwarding) ── UDP 51820, chiffré ──► Cloud NAT (IPv4 fixe existante)
                                                                          │ Internet
                                                                          ▼
                                               Passerelle AWS (t4g.micro, Elastic IP, 10.40.40.0/24)
                                                  │ SNAT : RDS voit l'IP privée de la passerelle
                                                  ▼
                                               RDS privé (10.40.10.0/24, 10.40.11.0/24)
```

Pourquoi ce choix :

- **RDS ne change pas** : toujours privé, aucune route ajoutée aux sous-réseaux base, aucun
  endpoint public.
- **Le SNAT côté AWS évite de toucher aux tables de routage de la base** : RDS voit un client
  du VPC (la passerelle) et la règle de sécurité référence simplement le groupe de la passerelle.
- **WireGuard** est minimal (une UDP), chiffré et authentifié par clés ; une seule règle
  entrante sur AWS, limitée à l'IPv4 fixe de Cloud NAT en `/32`.
- Le Cloud NAT à IPv4 réservée de `infra/gcp` est **réutilisé** : la passerelle GCP n'a pas
  d'IP publique.

## 4. Ce qui change, ressource par ressource

### Côté AWS (à relire par Nasr, **non écrit**)

| Ressource | Détail |
|---|---|
| Sous-réseau passerelle | `10.40.40.0/24`, route `0.0.0.0/0` vers l'IGW existant (comme `10.40.30.0/24`) |
| Instance passerelle | Amazon Linux 2023 ARM `t4g.micro`, IMDSv2, SSM, disque gp3 chiffré 8 GiB, Elastic IP |
| Groupe de sécurité passerelle | voir tableau pare-feu |
| Règle ingress sur le groupe RDS | 5432 depuis le **groupe de la passerelle** uniquement |
| Secret de clé WireGuard | AWS Secrets Manager (ou SSM SecureString) ; jamais dans Terraform ni Git |
| Interrupteur | variable `enable_gcp_gateway` à `false` par défaut, comme `enable_backup_api` |

**Inchangé** : table de routage base, `publicly_accessible`, groupe de sécurité du runner et de l'API de secours.

### Côté GCP (dans ma branche, à écrire après accord)

| Ressource | Détail |
|---|---|
| Passerelle `electionhub-rds-gw` | Debian 12 `e2-micro`, `can_ip_forward = true`, **sans IP publique**, WireGuard + iptables |
| Route statique | destination `10.40.10.0/23` → `next_hop_instance` = passerelle, **uniquement pour les VM étiquetées `electionhub-api`** |
| Pare-feu | voir tableau |
| Secret de clé WireGuard | GCP Secret Manager, lisible seulement par le compte de service de la passerelle |
| Interrupteur | `enable_rds_tunnel = false` par défaut |

## 5. Règles de pare-feu proposées

### AWS

| Direction | Groupe | Protocole / port | Source ou destination | Pourquoi |
|---|---|---|---|---|
| Entrée | passerelle | UDP 51820 | `<IPv4 Cloud NAT GCP>/32` | uniquement le tunnel depuis GCP |
| Sortie | passerelle | TCP 5432 | groupe RDS | atteindre la base |
| Sortie | passerelle | TCP 443 | `0.0.0.0/0` | SSM, paquets, bundle CA (comme le runner) |
| Entrée | **RDS** | TCP 5432 | groupe passerelle | **seule règle ajoutée au groupe RDS** |
| Entrée | passerelle | aucune autre | | pas de SSH, accès par SSM |

Les réponses UDP du tunnel sont autorisées par le suivi de connexion ; GCP envoie un
`PersistentKeepalive` pour garder le flux ouvert.

### GCP

| Direction | Cible | Protocole / port | Source ou destination | Pourquoi |
|---|---|---|---|---|
| Entrée | passerelle | TCP 5432 | VM étiquetées `electionhub-api` | seul trafic applicatif accepté |
| Sortie | passerelle | UDP 51820 | Elastic IP de la passerelle AWS `/32` | tunnel |
| Sortie | passerelle | TCP 443 | Internet via Cloud NAT | paquets, Secret Manager |
| Local (iptables) | passerelle | FORWARD TCP 5432 vers `10.40.10.0/23` | tout le reste refusé | un client compromis ne peut joindre que PostgreSQL |

WireGuard : `AllowedIPs` côté GCP = `10.40.10.0/23` + `10.99.0.0/29` ; côté AWS =
`10.20.0.0/24` + `10.99.0.0/29`.

## 6. Coût estimé (ordre de grandeur, à confirmer avant `apply`)

Les prix AWS reprennent ceux de Nasr (API Price List, Stockholm, `docs/infrastructure/aws-4b-rds-plan.md`).
Les prix GCP sont des **ordres de grandeur de tarif public, non lus dans l'API de facturation** :
les confirmer avec la calculatrice GCP.

| Élément | Calcul | USD/mois |
|---|---|---:|
| AWS `t4g.micro` | 730 h × 0,0086 | ≈ 6,3 |
| AWS IPv4 publique (Elastic IP) | 730 h × 0,005 | 3,65 |
| AWS gp3 8 GiB | | ≈ 0,7 |
| **Passerelle AWS** | | **≈ 10,6** |
| GCP `e2-micro` + disque 10 Go | tarif public, à confirmer | ≈ 6 à 7 |
| Transfert inter-cloud | quelques Mo en démonstration | ≈ 0 |
| **Total du chemin privé** | | **≈ 17** |

Le reste du lot GCP (VM d'API, load balancer, Cloud NAT) coûte **plus** que ce chemin et doit
être chiffré à part : les deux règles de redirection du load balancer (HTTP et HTTPS) et les
VM `e2-small` en sont l'essentiel. Pour une démonstration, supprimer la règle HTTP (redirection)
et fixer `max_replicas = 1` réduit la facture. Vérifier aussi les crédits du compte GCP avant
d'activer la facturation.

## 7. Vérification de `verify-full` depuis GCP

Le client se connecte au **nom d'hôte RDS** (pas à l'adresse IP) pour que le certificat soit
vérifié. Étapes, toutes depuis une VM API GCP, avec le bundle CA monté :

1. **Résolution** : `getent hosts <endpoint-rds>` doit renvoyer une adresse `10.40.10.x` ou
   `10.40.11.x`. Un endpoint RDS non public se résout normalement en adresse privée même hors du
   VPC ; **à confirmer**. Sinon, repli : fixer `hostaddr` (libpq) en gardant `host` pour la
   vérification du certificat, ce qui demande un petit ajout à `config.py`.
2. **Route** : `nc -vz <endpoint-rds> 5432` réussit (donc tunnel, route et SNAT corrects).
3. **TLS vérifié** : `psql "host=<endpoint-rds> sslmode=verify-full sslrootcert=<bundle> ..."`
   puis `SELECT ssl, version FROM pg_stat_ssl WHERE pid = pg_backend_pid();` → `ssl = t`.
4. **Tests négatifs obligatoires** :
   - `sslmode=disable` est refusé (`rds.force_ssl=1`) ;
   - une mauvaise CA échoue ;
   - se connecter par l'adresse IP au lieu du nom échoue à `verify-full` (nom non concordant).
5. **API** : conteneur en `APP_ENV=cloud`, `POSTGRES_SSLMODE=verify-full` →
   `GET /health` renvoie **200**, `environment: "cloud"`, schéma `0005_incidents`.
6. **Pare-feu** : depuis une VM GCP **sans** l'étiquette `electionhub-api`, `nc -vz <endpoint> 5432`
   échoue ; depuis l'extérieur, le port UDP 51820 de la passerelle AWS ignore toute autre IP source.
7. **Panne** : arrêter la passerelle AWS → `/health` passe en 503 (et la sonde de vie reste verte,
   donc pas de recréation en boucle) ; la relancer → retour à 200.

L'API GCP **n'exécute pas Alembic** : la base est déjà migrée par le runner de Nasr ; la sonde
`/health` confirme seulement que la version attendue est présente.

## 8. Secrets

- Clés WireGuard : générées sur chaque passerelle, clé privée stockée dans le gestionnaire de secrets
  de **son** cloud, seule la clé publique est échangée (dans la documentation, pas la privée).
- Mot de passe de `electionhub_app` : Nasr le lit dans AWS Secrets Manager et l'ajoute à
  GCP Secret Manager (`gcloud secrets versions add`) **à la main**, sans qu'il apparaisse dans un
  terminal partagé, Git ou une discussion. Ne jamais utiliser le secret maître RDS.
- Le bundle CA AWS est public ; il va dans le secret `electionhub-rds-ca-bundle` déjà prévu.

## 9. Risques et points ouverts

| Risque | Mesure |
|---|---|
| La passerelle AWS est un point de défaillance unique et expose une UDP à Internet | une seule IP source autorisée, aucune autre entrée, disponibilité acceptée pour une démonstration |
| Instance AWS supplémentaire à maintenir | image minimale, SSM, mise à jour par remplacement |
| L'IPv4 de Cloud NAT change si la ressource est recréée | adresse **réservée** (déjà le cas dans `infra/gcp`) ; mettre à jour la règle AWS si elle est recréée |
| Latence inter-cloud (Stockholm ↔ Finlande) | acceptable pour la démonstration ; à mesurer |
| `conntrack` UDP derrière Cloud NAT | keepalive 25 s ; vérifier par un test de stabilité de 10 minutes |
| Limite de connexions RDS (`db.t4g.micro`) | `max_db_connections` calculé par Terraform (20 par défaut) ; comparer à `SHOW max_connections` |
| Chemin à reprendre si l'on obtient un VPN géré plus tard | l'architecture GCP (route, secrets, sondes) reste valable |

## 10. Décisions demandées à Nasr

1. Valider l'option A (ou en proposer une autre) : RDS reste privé.
2. Accepter l'ajout côté AWS : un sous-réseau `10.40.40.0/24`, une passerelle, une règle sur le groupe
   RDS, derrière `enable_gcp_gateway=false`.
3. Confirmer que Site-to-Site VPN est bien indisponible sur le compte.
4. Valider le coût (≈ 17 USD/mois pour le chemin, hors reste du lot GCP).
5. Prévoir l'injection manuelle du mot de passe applicatif dans GCP Secret Manager.

## 11. Ordre de déploiement proposé (après accord, un `apply` approuvé à la fois)

1. GCP : projet, facturation, API activées (`terraform plan` relu, puis `apply` du socle sans tunnel).
2. AWS : plan de la passerelle relu par Nasr, `apply` séparé.
3. GCP : passerelle + route + pare-feu, tunnel monté ; tests 1 à 3 du §7.
4. Injection du secret, une VM API, tests 4 à 7 du §7.
5. Jalon atteint : `/health` 200. **Alors seulement** : URL HTTPS stable de l'API vers Azure (phase 7).

Retour arrière : supprimer la route GCP et la passerelle, mettre `enable_gcp_gateway=false`
(retire la passerelle et la règle RDS). RDS n'est jamais modifié.

## 12. Ce que je ne peux pas encore confirmer

- Accès GCP : `gcloud` est installé sur ce poste mais **aucun compte n'est connecté**. Identifiant
  de projet et facturation à confirmer après `gcloud auth login` par le propriétaire du compte.
- La résolution DNS privée de l'endpoint RDS depuis l'extérieur du VPC (§7, étape 1).
- Les prix GCP (§6) et le comportement du tunnel UDP à travers Cloud NAT : à mesurer.
