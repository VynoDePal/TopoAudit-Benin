# TopoAudit Bénin

Prototype SaaS local pour auditer de façon préliminaire des plans topographiques scannés au Bénin : upload d'un plan, extraction OCR, validation humaine des coordonnées, calcul géométrique, score de risque et génération d'un rapport PDF.

> Le produit ne fournit pas de verdict juridique. Il aide à repérer des incohérences techniques et doit toujours être complété par une validation humaine/métier.

## Démarrage démo en moins de 15 minutes

### Prérequis

- Docker Desktop ou Docker Engine avec le plugin `docker compose`.
- Ports libres : `3000` pour le frontend, `8000` pour l'API, `5432` pour PostgreSQL/PostGIS.
- Optionnel pour développer hors Docker : Python 3.11+ et Node.js 20+.

### 1. Configurer l'environnement

```bash
cp .env.example .env
```

La configuration par défaut lance une démo locale sans clé externe obligatoire. `docker-compose.yml` sélectionne `OCR_PROVIDER=gemini`, mais si `GEMINI_API_KEY` est vide en environnement local, l'API utilise le fournisseur OCR mock pour que la démo reste exécutable immédiatement.

Pour tester Gemini réellement, renseigner au minimum dans `.env` :

```env
GEMINI_API_KEY=...votre-cle...
GEMINI_MODEL=gemma-4-31b-it
```

Le **moteur OCR est sélectionnable à l'étape Import** : **Gemma 4 / Gemini**,
**Mistral OCR 4**, ou **Mock OCR** (local). Le choix est envoyé au backend
(`?provider=`). Pour Mistral, renseigner dans `.env` (voir
[docs/external_services/mistral_ocr_4.md](docs/external_services/mistral_ocr_4.md)) —
**ne jamais committer/logger `MISTRAL_API_KEY`** :

```env
MISTRAL_API_KEY=...votre-cle...
MISTRAL_OCR_MODEL=mistral-ocr-latest
```

`GET /api/ocr/providers` liste les providers et leur état (jamais les clés). Mistral peut
fournir une **confiance OCR machine par borne** (scores par mot) ; Gemini/Gemma reste
sans confiance par borne (« À valider »). La **validation humaine reste obligatoire** et
distincte de la confiance OCR.

### 2. Lancer toute la stack

```bash
docker compose up --build
```

Attendre que les trois services soient prêts :

- `db` : PostgreSQL/PostGIS healthy ;
- `api` : Uvicorn écoute sur `0.0.0.0:8000` ;
- `web` : Next.js écoute sur `0.0.0.0:3000`.

### 3. Ouvrir la démo

- Application web : <http://localhost:3000>
- API Swagger : <http://localhost:8000/api/docs>
- ReDoc : <http://localhost:8000/api/redoc>
- OpenAPI JSON : <http://localhost:8000/api/openapi.json>
- Healthcheck : <http://localhost:8000/api/health>

### 4. Parcours de démonstration recommandé

1. Ouvrir <http://localhost:3000>.
2. Étape **Intake** : garder les valeurs de démonstration ou choisir un PDF/PNG/JPG/JPEG de plan topographique.
3. Cliquer sur le bouton OCR / analyse du plan.
   - Sans fichier : le frontend passe en mode démo avec les parcelles exemples.
   - Avec fichier et sans clé Gemini : l'API locale utilise le mock OCR.
   - Avec fichier et clé Gemini : l'API appelle Gemini puis parse les bornes et surfaces détectées.
4. Étape **Validation** : vérifier/corriger les bornes et la surface déclarée, puis **confirmer le CRS détecté** (ou choisir `UNKNOWN_CRS` / `LOCAL_ONLY` si le plan n'est pas géoréférencé) avant de confirmer les parcelles. Aucun CRS n'est supposé `EPSG:32631` par défaut.
5. Étape **Audit** : lancer le calcul d'audit. Le backend calcule les scores à partir des surfaces, géométries et données OCR persistées.
6. Étape **Rapport** : générer et télécharger le PDF d'audit préliminaire.

La démo complète doit tenir en moins de 15 minutes avec la configuration locale par défaut.

## Architecture

```text
apps/web  ── Next.js / React / TypeScript / MapLibre
    │ REST JSON
    ▼
apps/api  ── FastAPI / SQLAlchemy / Shapely / pyproj / WeasyPrint
    │
    ▼
PostgreSQL + PostGIS via docker-compose.yml
```

Services Compose :

| Service | Rôle | URL/port local |
| --- | --- | --- |
| `db` | PostgreSQL 16 + PostGIS | `localhost:5432` |
| `api` | Backend FastAPI | <http://localhost:8000> |
| `web` | Frontend Next.js | <http://localhost:3000> |

## Fonctionnalités principales

- Création de projet et upload de document.
- Validation des fichiers uploadés : PDF, PNG, JPG/JPEG, taille maximum `MAX_UPLOAD_MB`.
- OCR via **mock, Gemma 4 / Gemini, Mistral OCR 4** ou Azure Document Intelligence — **provider sélectionnable à l'import** (`?provider=`), `GET /api/ocr/providers` pour l'état.
- Extraction de parcelles, surfaces déclarées et bornes depuis le texte OCR (tableaux **Markdown** supportés pour Mistral).
- Validation humaine des coordonnées avant audit.
- Conversion CRS `EPSG:32631` vers `EPSG:4326`.
- Validation géométrique avec Shapely : surface, périmètre, distances, auto-intersections, orientation.
- Score de risque dynamique selon la qualité des données et les écarts de surface.
- Rapport PDF généré côté API.
- Carte (MapLibre) avec **fond satellite Esri World Imagery uniquement** (`NEXT_PUBLIC_SATELLITE_TILE_URL`) pour les CRS transformables ; vue locale sans fond pour les CRS non géoréférencés. Fond **indicatif, non référence cadastrale**.
- Documentation OpenAPI synchronisée dans `docs/openapi.json`.

## Variables d'environnement utiles

Voir `.env.example` pour la liste complète.

| Variable | Défaut | Usage |
| --- | --- | --- |
| `APP_ENV` | `local` | Environnement applicatif. |
| `DATABASE_URL` | Compose DB | Connexion SQLAlchemy/PostgreSQL. |
| `FRONTEND_URL` | `http://localhost:3000` | Origine CORS autorisée. |
| `LOCAL_STORAGE_PATH` | `/data/uploads` | Stockage local des uploads dans le conteneur API. |
| `MAX_UPLOAD_MB` | `25` | Taille maximum des fichiers importés. |
| `OCR_PROVIDER` | `mock` dans `.env.example`, `gemini` dans Compose | Fournisseur OCR par défaut : `mock`, `gemini`, `mistral`, `azure` (surchargeable à l'import via `?provider=`). |
| `MISTRAL_API_KEY` | _(vide)_ | Clé Mistral OCR 4. **Jamais loggée/committée.** Voir `docs/external_services/mistral_ocr_4.md`. |
| `MISTRAL_OCR_MODEL` | `mistral-ocr-latest` | Modèle Mistral OCR. |
| `GEMINI_API_KEY` | vide | Active réellement Gemini si renseignée. |
| `GEMINI_API_ENDPOINT` | Google Generative Language API | Endpoint Gemini. |
| `GEMINI_MODEL` | `gemma-4-31b-it` | Modèle Gemini obligatoire pour le prototype durci. |
| `OCR_RATE_LIMIT_PER_MINUTE` | `10` | Limite OCR en mémoire par client. |

## Commandes de développement

### Backend seul

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --reload --port 8000
```

Si vous lancez l'API hors Docker avec PostgreSQL local, adaptez `DATABASE_URL` dans votre environnement.

### Frontend seul

```bash
cd apps/web
npm install
npm run dev
```

Par défaut, le frontend appelle `http://localhost:8000/api`. Pour changer l'API :

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api npm run dev
```

### Tests et contrôles qualité

Depuis la racine :

```bash
pytest -q
cd apps/web
npm test
npm run build
```

Commandes complémentaires :

```bash
# Régénérer l'artefact OpenAPI versionné
PYTHONPATH=apps/api python apps/api/scripts/generate_openapi.py

# Lancer uniquement les tests API
pytest -q apps/api/tests

# Lint frontend si nécessaire
cd apps/web && npm run lint
```

## Documentation technique

- Spécification prototype : [`docs/PROJECT_SPEC.md`](docs/PROJECT_SPEC.md)
- Spécification de durcissement : [`SPEC.md`](SPEC.md)
- OpenAPI versionné : [`docs/openapi.json`](docs/openapi.json)
- Service externe Gemini Vision OCR : [`docs/external_services/gemini_vision_ocr.md`](docs/external_services/gemini_vision_ocr.md)

## Endpoints API fréquents

| Méthode | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/health` | État API + DB. |
| `POST` | `/api/projects` | Créer un projet. |
| `POST` | `/api/projects/{project_id}/documents` | Uploader un plan. |
| `GET` | `/api/projects/{project_id}/parcels` | Lire les parcelles extraites. |
| `PUT` | `/api/projects/{project_id}/parcels` | Sauvegarder les corrections humaines. |
| `POST` | `/api/projects/{project_id}/validate` | Marquer le projet validé. |
| `POST` | `/api/projects/{project_id}/audit` | Calculer l'audit préliminaire. |
| `POST` | `/api/projects/{project_id}/audit/report.pdf` | Générer le PDF. |
| `POST` | `/api/geometry/validate-polygon` | Valider/calculer une géométrie. |
| `POST` | `/api/crs/transform` | Transformer des coordonnées vers `EPSG:4326`. |

## Dépannage rapide

### Le frontend ne joint pas l'API

Vérifier que l'API répond :

```bash
curl http://localhost:8000/api/health
```

Puis vérifier `NEXT_PUBLIC_API_BASE_URL` côté web. En Compose, il vaut `http://localhost:8000/api` pour les appels navigateur.

### Le port 5432, 8000 ou 3000 est déjà utilisé

Arrêter le service local concurrent ou modifier le mapping de ports dans `docker-compose.yml`.

### L'OCR retourne des données mock

C'est normal en local si `GEMINI_API_KEY` ou les credentials Azure sont absents. Pour un appel Gemini réel, définir `GEMINI_API_KEY` et relancer :

```bash
docker compose up --build
```

### Réinitialiser la base et les uploads de démo

```bash
docker compose down -v
docker compose up --build
```

Cette commande supprime les volumes Compose `postgres_data` et `api_uploads`.

## Garde-fous produit et sécurité

- Ne jamais hardcoder de clé API ou secret dans le code.
- Ne jamais logger les clés OCR ni les en-têtes d'authentification.
- Ne pas utiliser le prototype pour certifier une conformité juridique ou une propriété foncière.
- Ne pas scraper Cadastre.bj ; seules des données importées par l'utilisateur ou des accès officiels documentés sont autorisés.
- Les documents fonciers peuvent contenir des données sensibles : utiliser la démo locale avec des fichiers de test ou des documents autorisés.
