# Application web locale — Phase 4

ElectionHub utilise une seule application React pour les interfaces citoyen, agent,
administrateur et validateur. La navigation masque les fonctions non pertinentes, tandis
que FastAPI vérifie chaque permission. Aucun rôle ou identifiant utilisateur fourni par
le navigateur n'est considéré comme une autorisation.

## Lancer l'application

```powershell
docker compose up -d --build --wait
```

Ouvrir `http://127.0.0.1:3000`. Les comptes initiaux sont `demo-agent`, `demo-admin` et
`demo-validator`; leurs secrets locaux proviennent de `.local/demo-credentials.json`.
Ils ne sont ni intégrés au bundle ni affichés par l'interface.

Le navigateur appelle uniquement l'origine web sur `/api/v1`. Nginx transmet ces requêtes
à FastAPI, ce qui évite une configuration CORS locale et prépare l'hébergement dans le
même Azure App Service. Les jetons restent dans l'état mémoire de React : un rechargement
demande une nouvelle connexion. Ils ne passent ni par `localStorage`, ni par `sessionStorage`,
ni par l'URL.

## Parcours disponibles

| Profil | Interfaces et actions |
|---|---|
| Public | Annuaire des bureaux fictifs et connexion |
| Citoyen | Demande/vérification OTP locale et consultation de son propre bureau |
| Agent | Tableau de bord, bureaux affectés, création de brouillon, saisie cohérente, soumission, correction d'un rejet et historique |
| Validateur | PV soumis, résultats structurés, démarrage de revue, approbation ou rejet motivé |
| Administrateur | Supervision, référentiels bureaux/scrutins/listes, inscriptions, affectations, comptes, rôles et journal d'audit |

Les formulaires affichent les erreurs réseau et métier sans perdre les données saisies.
Les mutations de PV transmettent `expected_version`; un conflit 409 demande de recharger
au lieu d'écraser une modification concurrente. La cohérence des résultats est contrôlée
dans l'interface pour un retour immédiat, puis entièrement revérifiée par le backend.

Les pages sont adaptées aux écrans desktop et mobiles : menu latéral repliable, tableaux
défilables, formulaires à une colonne et contrôles tactiles. Les titres, labels, états de
chargement, erreurs, focus visible et lien d'accès direct au contenu sont utilisables au clavier.

## Développement

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
npm.cmd test
npm.cmd run build
```

Vite transmet `/api` à `http://127.0.0.1:8000` en développement. Définir temporairement
`API_PROXY_TARGET` avant `npm run dev` permet de viser un autre backend local. Le build
génère `frontend/dist`; le conteneur Nginx le sert sur son port non privilégié 8080.

## Sécurité et limites

- Nginx ajoute CSP, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`
  et interdit l'intégration de la page dans une frame.
- Le conteneur web est non privilégié et monté en lecture seule, avec `/tmp` séparé.
- Les erreurs 401 effacent la session en mémoire et renvoient à la connexion; les 403
  indiquent une permission insuffisante; les 429 indiquent le délai avant nouvel essai.
- L'annuaire public n'expose aucun CIN, téléphone, note interne ou résultat non publié.

La phase 4 traite les résultats structurés. Le téléversement de PV, les incidents avec
photos, S3 et Lambda PV appartiennent à la phase 5 et sont signalés comme futurs dans le
dossier. L'approbation ne publie rien. BigQuery et Looker Studio restent planifiés.
