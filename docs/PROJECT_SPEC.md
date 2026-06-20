# TopoAudit Bénin — Documentation de cadrage prototype SaaS

**Version :** 0.1  
**Date :** 2026-06-20  
**Stack cible :** Next.js/React/TypeScript + Python/FastAPI/PostgreSQL/PostGIS  
**Outil d’orchestration IA prévu :** Collègue MCP — <https://github.com/VynoDePal/Collegue>  
**Pays cible :** Bénin  
**Statut du document :** cahier de cadrage technique pour faire réaliser le prototype par une IA de développement.

---

## 0. Décision stratégique

Le prototype ne doit pas essayer de “prouver juridiquement” qu’un levé est correct ou faux. Le produit doit produire un **audit préliminaire de risque** à partir d’un plan topographique scanné.

Promesse exacte du prototype :

> Importer un plan topographique scanné, extraire les coordonnées des bornes, reconstruire la parcelle, recalculer surface/périmètre/distances, détecter les incohérences, tracer la parcelle sur carte si le système de coordonnées est exploitable, puis générer un rapport d’audit préliminaire.

Promesse interdite au prototype :

> Certifier juridiquement la conformité du levé, remplacer un géomètre-expert, ou déduire automatiquement la vraie limite foncière à partir d’une image satellite.

---

## 1. Contexte métier

### 1.1 Problème

Au Bénin, les acteurs fonciers manipulent des plans topographiques souvent fournis sous forme de documents scannés ou photographiés. Ces documents contiennent généralement :

- un tableau de coordonnées des bornes ;
- une surface déclarée en hectares, ares et centiares ;
- un croquis de la parcelle ;
- une échelle ;
- parfois une mention de système géodésique, par exemple WGS 84 / UTM 31 Nord ;
- parfois un plan de situation ;
- parfois plusieurs parcelles sur un même document.

Le risque business et juridique vient de plusieurs sources : mauvaise lecture des coordonnées, mauvais système de projection, inversion X/Y, surface fausse, parcelle non fermée, coordonnées locales non géoréférencées, document de mauvaise qualité, superposition douteuse avec une référence cadastrale.

### 1.2 Utilisateurs cibles pour le prototype

Priorité initiale :

1. agences immobilières ;
2. promoteurs ;
3. particuliers avant achat ;
4. notaires ou collaborateurs de notaires ;
5. géomètres partenaires pour validation métier.

Ne pas démarrer par l’administration comme client principal. L’administration et l’ANDF sont des partenaires stratégiques long terme, mais le cycle d’accès et de validation est plus lent.

### 1.3 Cas d’usage prototype

Cas d’usage prioritaires :

- vérification avant achat ;
- détection d’erreurs techniques dans un levé ;
- préparation d’un dossier administratif ;
- pré-détection de fraude documentaire ;
- comparaison future avec une référence cadastrale officielle quand elle est disponible.

---

## 2. Périmètre du prototype

### 2.1 Inclus dans le prototype v1

Le prototype doit permettre :

1. upload d’une image JPG/PNG ou d’un PDF scanné ;
2. extraction automatique du tableau de coordonnées ;
3. extraction automatique de la surface déclarée ;
4. détection du système de coordonnées si mention visible ;
5. validation/correction humaine des coordonnées extraites ;
6. reconstruction du polygone ;
7. recalcul de la surface ;
8. recalcul du périmètre ;
9. recalcul des distances entre bornes successives ;
10. comparaison surface déclarée vs surface calculée ;
11. détection des anomalies géométriques ;
12. conversion WGS84/UTM zone 31N vers longitude/latitude ;
13. affichage sur carte si géoréférencement possible ;
14. mode “tracé local uniquement” si le système n’est pas géoréférencé ;
15. score d’extraction ;
16. score de cohérence technique ;
17. génération d’un rapport PDF ;
18. documentation Swagger/OpenAPI des services internes FastAPI ;
19. documentation des services externes utilisés ou prévus.

### 2.2 Exclu du prototype v1

À ne pas développer en v1 :

- certification juridique ;
- conclusion “ce terrain appartient à X” ;
- accès non autorisé ou scraping de Cadastre.bj ;
- IA qui déduit seule la bonne limite foncière depuis l’image satellite ;
- détection automatique fiable de clôtures/bornes depuis imagerie satellite ;
- application mobile ;
- paiement en ligne ;
- workflow complet de dossier foncier ;
- comparaison automatisée avec la base cadastrale nationale sans accès officiel.

---

## 3. Architecture cible

### 3.1 Vue d’ensemble

```text
                ┌────────────────────────────────────┐
                │        Frontend Next.js            │
                │ React + TypeScript + MapLibre      │
                └──────────────────┬─────────────────┘
                                   │ REST JSON
                                   ▼
                ┌────────────────────────────────────┐
                │          Backend FastAPI           │
                │ API + Jobs + OpenAPI/Swagger       │
                └───────┬───────────────┬────────────┘
                        │               │
                        ▼               ▼
          ┌────────────────────┐  ┌──────────────────┐
          │ PostgreSQL/PostGIS │  │ Stockage fichiers │
          │ géométrie + audit  │  │ local/S3/MinIO    │
          └────────────────────┘  └──────────────────┘
                        │
                        ▼
       ┌────────────────────────────────────────────┐
       │ Moteurs backend                            │
       │ - OCR / Document Intelligence adapter      │
       │ - Prétraitement image                      │
       │ - Extraction coordonnées                   │
       │ - Moteur géométrique Shapely/PostGIS       │
       │ - Conversion CRS pyproj                    │
       │ - Scoring                                  │
       │ - Génération rapport PDF                   │
       └────────────────────────────────────────────┘
```

### 3.2 Choix techniques imposés

Frontend :

- Next.js + React + TypeScript ;
- TanStack Query pour les appels API ;
- Zod pour validation côté client ;
- MapLibre GL JS pour la carte ;
- Tailwind CSS ou CSS modules ;
- composant tableau éditable pour validation des coordonnées.

Backend :

- Python 3.11+ ;
- FastAPI ;
- Pydantic v2 ;
- SQLAlchemy 2 ;
- Alembic ;
- PostgreSQL + PostGIS ;
- Shapely ;
- GeoPandas optionnel ;
- pyproj ;
- OpenCV/Pillow pour prétraitement image ;
- WeasyPrint ou ReportLab pour export PDF ;
- stockage local en prototype, MinIO/S3-compatible en option.

OCR :

- v1 recommandée : adapter Azure AI Document Intelligence pour extraction de texte/tableaux ;
- fallback local optionnel : Tesseract ou PaddleOCR ;
- toute extraction doit passer par un écran de validation humaine avant audit final.

---

## 4. Règles produit non négociables

### 4.1 Human-in-the-loop obligatoire

Le système doit toujours afficher les coordonnées extraites dans un tableau éditable avant calcul final.

Raison : les documents scannés peuvent être flous, inclinés, partiellement masqués, ou contenir des formats variables.

### 4.2 Aucun verdict juridique

Les libellés autorisés :

- “risque faible” ;
- “risque modéré” ;
- “risque élevé” ;
- “données insuffisantes” ;
- “incohérence technique détectée” ;
- “audit préliminaire”.

Les libellés interdits :

- “levé juridiquement conforme” ;
- “titre valide” ;
- “preuve de propriété” ;
- “le géomètre a tort” ;
- “fraude prouvée”.

### 4.3 Pas de scraping cadastral

Le prototype ne doit pas automatiser le scraping de Cadastre.bj. La comparaison cadastrale doit fonctionner uniquement avec :

- un extrait cadastral importé par l’utilisateur ;
- des données de référence saisies manuellement ;
- un accès officiel futur ;
- une API officielle future documentée et autorisée.

### 4.4 Satellite = visualisation, pas vérité

La carte satellite sert à visualiser. Elle ne doit pas être traitée comme preuve de limite foncière.

---

## 5. Données d’entrée

### 5.1 Types de fichiers acceptés

Prototype v1 :

- `.jpg` ;
- `.jpeg` ;
- `.png` ;
- `.pdf` scanné d’une ou plusieurs pages.

À ajouter plus tard :

- `.dxf` ;
- `.dwg` ;
- `.kml` ;
- `.kmz` ;
- `.geojson` ;
- `.csv` ;
- `.xlsx`.

### 5.2 Éléments à extraire

Le système doit extraire :

```json
{
  "document_title": "Titre N°...",
  "declared_surface_raw": "05a 49ca",
  "declared_surface_m2": 549,
  "scale": "1/500",
  "geodetic_system_raw": "WGS 84 UTM 31 Nord",
  "detected_crs": "EPSG:32631",
  "points": [
    {"label": "B1", "x": 403825.84, "y": 707630.38, "confidence": 0.94},
    {"label": "B2", "x": 403836.57, "y": 707626.36, "confidence": 0.92}
  ],
  "warnings": []
}
```

### 5.3 Formats variables à gérer

Le parser doit gérer :

- `B1`, `B.1`, `B 1`, `Bnes`, `Bornes` ;
- colonnes `X/Y` ;
- colonnes `Y/X` ;
- virgule ou point décimal ;
- espaces dans les nombres : `1 005.60` ;
- surfaces : `05a 49ca`, `5 a 49 ca`, `29ha 95a 38ca`, `43a 36ca` ;
- plusieurs parcelles dans un même tableau ;
- anciens plans à coordonnées locales.

---

## 6. Normalisation des surfaces

### 6.1 Règle de conversion

- 1 hectare = 10 000 m² ;
- 1 are = 100 m² ;
- 1 centiare = 1 m².

Exemples :

| Surface brute | Surface en m² |
|---|---:|
| `05a 49ca` | 549 |
| `2a 08ca` | 208 |
| `43a 36ca` | 4 336 |
| `29ha 95a 38ca` | 299 538 |

### 6.2 Fonction attendue

```python
def parse_surface_to_m2(raw: str) -> int | None:
    """Convertit une surface foncière francophone en mètres carrés."""
```

Tests minimaux :

```python
def test_parse_surface_to_m2():
    assert parse_surface_to_m2("05a 49ca") == 549
    assert parse_surface_to_m2("2a08ca") == 208
    assert parse_surface_to_m2("43a 36ca") == 4336
    assert parse_surface_to_m2("29ha 95a 38ca") == 299538
```

---

## 7. Système de coordonnées et géoréférencement

### 7.1 CRS prioritaire pour le Bénin

Le prototype doit traiter en priorité :

- `EPSG:32631` : WGS 84 / UTM zone 31N ;
- `EPSG:4326` : WGS 84 longitude/latitude pour l’affichage GeoJSON.

### 7.2 Détection heuristique

Règles de détection proposées :

```text
Si le document contient "WGS", "UTM", "31", "Nord" ou "ITRF" :
    CRS probable = EPSG:32631.

Si X est environ entre 166000 et 834000 et Y positif avec ordre de grandeur compatible Bénin :
    CRS probable = EPSG:32631.

Si les valeurs sont petites, par exemple X≈900, Y≈2000 ou X≈9000 :
    CRS = local_non_georef.

Si la colonne Y contient les valeurs d’easting et X contient les valeurs de northing :
    proposer inversion X/Y à l’utilisateur.
```

### 7.3 Transformation

Le backend doit utiliser `pyproj.Transformer` avec `always_xy=True`.

Pseudo-code :

```python
from pyproj import Transformer

transformer = Transformer.from_crs("EPSG:32631", "EPSG:4326", always_xy=True)
lon, lat = transformer.transform(x, y)
```

### 7.4 Règle GeoJSON

Tout GeoJSON produit par l’API doit être en `EPSG:4326`, ordre `[longitude, latitude]`.

### 7.5 Mode coordonnées locales

Si le document n’est pas géoréférencé, le système doit :

- reconstruire la parcelle dans un repère local ;
- calculer surface, périmètre, distances ;
- afficher un canvas local ;
- ne pas afficher la parcelle sur fond satellite ;
- afficher : “Coordonnées locales : affichage satellite impossible sans point de rattachement.”

---

## 8. Moteur géométrique

### 8.1 Calculs obligatoires

Pour chaque parcelle :

- nombre de bornes ;
- polygone fermé ;
- surface calculée ;
- périmètre calculé ;
- longueur de chaque segment ;
- centroïde ;
- enveloppe/bounding box ;
- orientation du polygone ;
- validité géométrique ;
- détection d’auto-intersection ;
- détection de points dupliqués ;
- écart surface déclarée vs calculée.

### 8.2 Seuils proposés

| Contrôle | Seuil prototype |
|---|---:|
| Écart surface faible | <= 1 % ou <= 2 m² |
| Écart surface modéré | > 1 % et <= 5 % |
| Écart surface élevé | > 5 % |
| Point dupliqué | distance < 0,01 m |
| Polygone non valide | rejet audit final sans correction |
| Nombre minimal de points | 3 |

### 8.3 Ordre des bornes

Par défaut, utiliser l’ordre du tableau : B1 → B2 → B3 → ... → B1.

Si la géométrie est invalide, proposer :

- ordre par angle autour du centroïde ;
- validation manuelle par l’utilisateur ;
- avertissement explicite dans le rapport.

---

## 9. Scoring

Le système doit produire deux scores en v1.

### 9.1 Score d’extraction

Objectif : mesurer la confiance dans la lecture du document.

| Critère | Poids |
|---|---:|
| Tableau de coordonnées détecté | 30 % |
| Confiance moyenne OCR des coordonnées | 30 % |
| Surface détectée | 15 % |
| CRS détecté | 15 % |
| Qualité image | 10 % |

### 9.2 Score de cohérence technique

Objectif : mesurer si le levé est cohérent avec lui-même.

| Critère | Poids |
|---|---:|
| Polygone valide | 25 % |
| Surface calculée proche de la surface déclarée | 30 % |
| Distances cohérentes | 20 % |
| CRS plausible | 15 % |
| Bornes cohérentes | 10 % |

### 9.3 Interprétation

| Score | Niveau |
|---:|---|
| 85–100 | Risque faible |
| 65–84 | Risque modéré |
| 40–64 | Risque élevé |
| 0–39 | Incohérence majeure ou données insuffisantes |

---

## 10. Rapport PDF

Le rapport doit contenir :

1. titre du projet ;
2. date de génération ;
3. fichier analysé ;
4. avertissement : audit préliminaire non juridique ;
5. image originale miniature ;
6. coordonnées extraites et validées ;
7. surface déclarée ;
8. surface calculée ;
9. écart surface ;
10. distances entre bornes ;
11. carte ou tracé local ;
12. scores ;
13. anomalies détectées ;
14. recommandations ;
15. log technique : CRS, transformation, version du moteur.

Exemple de recommandation :

```text
Le document semble géométriquement cohérent. Toutefois, l’audit ne compare pas encore le levé à une référence cadastrale officielle. Vérifier le TF/QIP ou demander un extrait cadastral avant toute transaction.
```

---

## 11. API interne FastAPI

### 11.1 Documentation Swagger obligatoire

FastAPI doit exposer :

- `/api/docs` : Swagger UI ;
- `/api/redoc` : ReDoc ;
- `/api/openapi.json` : schéma OpenAPI généré ;
- `/api/health` : santé du service.

### 11.2 Tags OpenAPI obligatoires

Les routes doivent être regroupées avec les tags :

- `health` ;
- `projects` ;
- `documents` ;
- `ocr` ;
- `extractions` ;
- `geometry` ;
- `maps` ;
- `audits` ;
- `reports` ;
- `external-services`.

### 11.3 Endpoints MVP

#### Health

```http
GET /api/health
```

Réponse :

```json
{
  "status": "ok",
  "version": "0.1.0",
  "environment": "local"
}
```

#### Création projet

```http
POST /api/projects
```

Body :

```json
{
  "name": "Vérification terrain Abomey-Calavi",
  "country": "BJ",
  "commune": "Abomey-Calavi",
  "notes": "Avant achat"
}
```

#### Upload document

```http
POST /api/projects/{project_id}/documents
Content-Type: multipart/form-data
```

Champs :

- `file` ;
- `document_type`: `survey_scan` ;
- `source`: `user_upload`.

#### Lancer extraction OCR

```http
POST /api/documents/{document_id}/analyze
```

Body :

```json
{
  "ocr_provider": "azure_document_intelligence",
  "force": false
}
```

#### Obtenir résultat OCR brut

```http
GET /api/documents/{document_id}/ocr-result
```

#### Valider extraction

```http
POST /api/extractions/{extraction_id}/validate
```

Body :

```json
{
  "declared_surface_raw": "05a 49ca",
  "declared_surface_m2": 549,
  "crs": "EPSG:32631",
  "points": [
    {"label": "B1", "x": 403825.84, "y": 707630.38},
    {"label": "B2", "x": 403836.57, "y": 707626.36},
    {"label": "B3", "x": 403830.47, "y": 707610.52},
    {"label": "B4", "x": 403827.18, "y": 707601.32},
    {"label": "B5", "x": 403799.28, "y": 707612.51}
  ]
}
```

#### Calculer géométrie

```http
POST /api/extractions/{extraction_id}/geometry
```

Réponse :

```json
{
  "parcel_id": "uuid",
  "valid": true,
  "area_m2": 549.1,
  "perimeter_m": 99.48,
  "declared_area_m2": 549,
  "area_delta_m2": 0.1,
  "area_delta_percent": 0.02,
  "segments": [
    {"from": "B1", "to": "B2", "length_m": 11.46}
  ],
  "warnings": []
}
```

#### Obtenir GeoJSON

```http
GET /api/parcels/{parcel_id}/geojson
```

#### Lancer audit

```http
POST /api/projects/{project_id}/audit
```

Réponse :

```json
{
  "audit_id": "uuid",
  "extraction_score": 87,
  "technical_score": 92,
  "risk_level": "low",
  "warnings": [
    "Aucune comparaison cadastrale officielle effectuée."
  ]
}
```

#### Export rapport

```http
GET /api/audits/{audit_id}/report.pdf
```

---

## 12. Schéma OpenAPI minimal à générer

Le backend doit permettre d’exporter le schéma :

```bash
python scripts/export_openapi.py > docs/swagger/topoaudit-openapi.json
```

Le fichier `docs/swagger/topoaudit-openapi.json` doit être versionné dans le dépôt pour que l’IA, le frontend et les testeurs disposent d’un contrat API stable.

Extrait attendu :

```yaml
openapi: 3.1.0
info:
  title: TopoAudit Bénin API
  version: 0.1.0
  description: API d'audit préliminaire de levés topographiques scannés.
servers:
  - url: http://localhost:8000/api
paths:
  /health:
    get:
      tags: [health]
      summary: Healthcheck
  /projects:
    post:
      tags: [projects]
      summary: Créer un projet d'audit
  /projects/{project_id}/documents:
    post:
      tags: [documents]
      summary: Uploader un plan topographique scanné
  /documents/{document_id}/analyze:
    post:
      tags: [ocr]
      summary: Lancer l'analyse OCR du document
  /extractions/{extraction_id}/validate:
    post:
      tags: [extractions]
      summary: Valider ou corriger les coordonnées extraites
  /extractions/{extraction_id}/geometry:
    post:
      tags: [geometry]
      summary: Calculer la géométrie de la parcelle
  /projects/{project_id}/audit:
    post:
      tags: [audits]
      summary: Générer un audit préliminaire
  /audits/{audit_id}/report.pdf:
    get:
      tags: [reports]
      summary: Télécharger le rapport PDF
```

---

## 13. Services externes et documentation Swagger/OpenAPI

### 13.1 Politique générale

Chaque service externe doit avoir un fichier dédié dans :

```text
docs/external_services/
```

Structure obligatoire :

```text
docs/external_services/
  azure_document_intelligence.md
  esri_arcgis_world_imagery.md
  cadastre_bj_andf.md
  google_maps_optional.md
  osm_tile_policy.md
```

Chaque fichier doit contenir :

- rôle du service ;
- usage autorisé dans le prototype ;
- usage interdit ;
- variables d’environnement ;
- endpoints principaux ;
- lien Swagger/OpenAPI si disponible ;
- lien documentation officielle ;
- stratégie de fallback ;
- risques légaux/licence.

### 13.2 Azure AI Document Intelligence — OCR/tableaux

**Statut prototype : recommandé comme fournisseur OCR externe principal.**

Usage :

- analyse des images/PDF scannés ;
- extraction de texte ;
- extraction de tableaux ;
- récupération de coordonnées.

Swagger/OpenAPI officiel :

- HTML GitHub : <https://github.com/Azure/azure-rest-api-specs/blob/main/specification/ai/data-plane/DocumentIntelligence/stable/2024-11-30/DocumentIntelligence.json>
- Raw JSON recommandé : <https://raw.githubusercontent.com/Azure/azure-rest-api-specs/main/specification/ai/data-plane/DocumentIntelligence/stable/2024-11-30/DocumentIntelligence.json>

Documentation REST officielle :

- <https://learn.microsoft.com/en-us/rest/api/aiservices/document-models/analyze-document?view=rest-aiservices-v4.0%20(2024-11-30)>
- <https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/how-to-guides/use-sdk-rest-api?view=doc-intel-4.0.0>

Variables d’environnement :

```env
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=
AZURE_DOCUMENT_INTELLIGENCE_KEY=
AZURE_DOCUMENT_INTELLIGENCE_API_VERSION=2024-11-30
AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID=prebuilt-layout
```

Endpoints wrapper internes à créer :

```http
POST /api/external/ocr/azure/analyze
GET  /api/external/ocr/azure/operations/{operation_id}
```

Règles :

- stocker la réponse brute pour audit technique ;
- ne pas envoyer des documents contenant des informations personnelles non nécessaires sans consentement ;
- prévoir une option de masquage/anonymisation ;
- prévoir un fallback local si la clé Azure est absente.

### 13.3 Esri ArcGIS World Imagery — fond satellite

**Statut prototype : autorisé pour visualisation cartographique, pas pour décision juridique automatique.**

Usage :

- afficher la parcelle extraite sur fond satellite ;
- aider l’utilisateur à visualiser la localisation ;
- ne pas conclure seul sur la conformité.

Documentation officielle :

- ArcGIS REST APIs : <https://developers.arcgis.com/rest/>
- ArcGIS Server Services Directory : <https://developers.arcgis.com/rest/services-reference/enterprise/get-started-with-the-services-directory/>
- Map Service REST : <https://developers.arcgis.com/rest/services-reference/enterprise/map-service/>
- World Imagery overview : <https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9>

Endpoint de service généralement utilisé pour les tuiles :

```text
https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer
```

Swagger/OpenAPI :

- Esri expose surtout une documentation REST et un service directory, pas toujours une spécification OpenAPI standard.
- Créer une documentation interne `docs/external_services/esri_arcgis_world_imagery.md` et documenter notre wrapper si un backend proxy est créé.

Règles :

- ne pas utiliser l’imagerie comme preuve ;
- afficher la date/résolution/source si disponible ;
- ne pas entraîner un modèle IA sur les tuiles sans vérifier les droits ;
- prévoir un fournisseur alternatif.

### 13.4 Cadastre.bj / ANDF — référence foncière

**Statut prototype : source stratégique future, pas d’intégration automatisée non autorisée en v1.**

Rôle :

- comparaison future avec une référence cadastrale ;
- recherche par TF/QIP ou paramètres disponibles officiellement ;
- import d’extraits cadastraux fournis par l’utilisateur.

Documentation officielle consultable :

- Cadastre national : <https://cadastre.bj/>
- ANDF — Cadastre : <https://andf.bj/cadastre/>
- CatIS — Cadastre national du Bénin : <https://catis.xroad.bj/systems/IS00016>

Swagger/OpenAPI :

- aucune documentation OpenAPI publique confirmée dans le cadrage actuel ;
- ne pas reverse-engineer les appels internes du portail ;
- ne pas scraper ;
- créer une interface `CadastreProvider` prête pour un accès officiel futur.

Wrapper interne à créer pour v1 :

```http
POST /api/external/cadastre/import-reference
GET  /api/external/cadastre/references/{reference_id}
POST /api/external/cadastre/compare
```

En v1, ces endpoints ne doivent utiliser que des fichiers ou coordonnées fournis par l’utilisateur.

### 13.5 Google Maps — option de visualisation uniquement

**Statut prototype : optionnel, non recommandé comme source d’analyse IA.**

Usage autorisé :

- affichage carte pour l’utilisateur, selon les conditions Google.

Usage interdit :

- analyse machine des tuiles ;
- détection d’objets ;
- extraction de géodonnées ;
- génération de vérité foncière depuis image.

Documentation :

- Map Tiles API : <https://developers.google.com/maps/documentation/tile>
- Policies : <https://developers.google.com/maps/documentation/tile/policies>

Swagger/OpenAPI :

- ne pas bloquer le prototype sur Google Maps ;
- si utilisé, documenter dans `docs/external_services/google_maps_optional.md`.

### 13.6 OpenStreetMap — option carte/contexte

Usage :

- fond cartographique non satellite ;
- contexte voies/lieux.

Règles :

- ne pas bulk-download les tuiles publiques ;
- ne pas utiliser les serveurs publics OSM pour un SaaS en production à volume élevé ;
- prévoir fournisseur de tuiles commercial ou self-hosting.

Documentation :

- Tile Usage Policy : <https://operations.osmfoundation.org/policies/tiles/>

Swagger/OpenAPI :

- non applicable pour les tuiles publiques ;
- documenter la politique d’usage dans `docs/external_services/osm_tile_policy.md`.

---

## 14. Base de données

### 14.1 Tables principales

```text
users
projects
documents
ocr_jobs
extractions
survey_points
parcels
parcel_segments
audits
audit_findings
reports
external_service_logs
cadastre_references
```

### 14.2 Modèle logique

#### projects

```sql
id UUID PRIMARY KEY
name TEXT NOT NULL
country_code TEXT DEFAULT 'BJ'
commune TEXT NULL
notes TEXT NULL
created_at TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL
```

#### documents

```sql
id UUID PRIMARY KEY
project_id UUID REFERENCES projects(id)
filename TEXT NOT NULL
mime_type TEXT NOT NULL
storage_path TEXT NOT NULL
sha256 TEXT NOT NULL
quality_score NUMERIC NULL
created_at TIMESTAMPTZ NOT NULL
```

#### extractions

```sql
id UUID PRIMARY KEY
document_id UUID REFERENCES documents(id)
provider TEXT NOT NULL
raw_text TEXT NULL
raw_json JSONB NULL
declared_surface_raw TEXT NULL
declared_surface_m2 NUMERIC NULL
crs_detected TEXT NULL
crs_validated TEXT NULL
status TEXT NOT NULL
confidence NUMERIC NULL
created_at TIMESTAMPTZ NOT NULL
validated_at TIMESTAMPTZ NULL
```

#### survey_points

```sql
id UUID PRIMARY KEY
extraction_id UUID REFERENCES extractions(id)
label TEXT NOT NULL
x NUMERIC NOT NULL
y NUMERIC NOT NULL
order_index INT NOT NULL
confidence NUMERIC NULL
source TEXT NOT NULL
```

#### parcels

```sql
id UUID PRIMARY KEY
project_id UUID REFERENCES projects(id)
extraction_id UUID REFERENCES extractions(id)
crs_source TEXT NOT NULL
crs_geojson TEXT DEFAULT 'EPSG:4326'
area_m2 NUMERIC NULL
perimeter_m NUMERIC NULL
centroid GEOMETRY(Point, 4326) NULL
geom GEOMETRY(Polygon, 4326) NULL
local_geom JSONB NULL
valid BOOLEAN NOT NULL
validity_reason TEXT NULL
created_at TIMESTAMPTZ NOT NULL
```

#### audits

```sql
id UUID PRIMARY KEY
project_id UUID REFERENCES projects(id)
parcel_id UUID REFERENCES parcels(id)
extraction_score NUMERIC NOT NULL
technical_score NUMERIC NOT NULL
reference_score NUMERIC NULL
risk_level TEXT NOT NULL
summary TEXT NOT NULL
created_at TIMESTAMPTZ NOT NULL
```

---

## 15. Frontend

### 15.1 Pages

```text
/
/projects
/projects/new
/projects/[id]
/projects/[id]/upload
/projects/[id]/extraction
/projects/[id]/map
/projects/[id]/audit
/projects/[id]/report
```

### 15.2 Composants

```text
UploadDropzone
DocumentPreview
ExtractionStatus
CoordinateTableEditor
SurfaceParserPreview
CRSSelector
GeometrySummaryCard
MapParcelViewer
LocalParcelViewer
AuditScoreCard
FindingsList
ReportDownloadButton
ExternalServiceStatus
```

### 15.3 Parcours utilisateur

1. Créer projet.
2. Uploader plan.
3. Lancer extraction.
4. Vérifier/corriger coordonnées.
5. Sélectionner ou confirmer CRS.
6. Lancer calcul géométrique.
7. Visualiser la parcelle.
8. Lancer audit.
9. Télécharger rapport.

### 15.4 UX obligatoire

Le frontend doit afficher clairement :

- coordonnées extraites ;
- cases modifiables ;
- confiance OCR par ligne ;
- différence surface déclarée/calculée ;
- avertissement si CRS incertain ;
- avertissement si coordonnées locales ;
- bouton “Confirmer les coordonnées” avant audit.

---

## 16. Structure de dépôt recommandée

```text
topoaudit-benin/
  README.md
  docker-compose.yml
  .env.example
  docs/
    PROJECT_SPEC.md
    swagger/
      topoaudit-openapi.json
    external_services/
      azure_document_intelligence.md
      esri_arcgis_world_imagery.md
      cadastre_bj_andf.md
      google_maps_optional.md
      osm_tile_policy.md
    architecture/
      database.md
      scoring.md
      crs.md
      ocr_pipeline.md
  apps/
    api/
      app/
        main.py
        core/
        db/
        models/
        schemas/
        routers/
        services/
          ocr/
          geometry/
          scoring/
          maps/
          reports/
          external/
        workers/
        tests/
      alembic/
      pyproject.toml
      requirements.txt
    web/
      app/
      components/
      lib/
      types/
      package.json
      tsconfig.json
  samples/
    scans/
    annotations/
      ground_truth_examples.json
  scripts/
    export_openapi.py
    seed_demo_data.py
```

---

## 17. Jobs backend

### 17.1 Job OCR

États :

```text
queued -> processing -> needs_review -> validated -> failed
```

### 17.2 Job audit

États :

```text
created -> running -> completed -> failed
```

### 17.3 Logs

Chaque appel externe doit être loggé :

```json
{
  "service": "azure_document_intelligence",
  "operation": "analyze_document",
  "status_code": 202,
  "duration_ms": 1340,
  "document_id": "uuid",
  "created_at": "..."
}
```

Ne jamais logger les clés API.

---

## 18. Pipeline OCR proposé

### 18.1 Étapes

1. Charger image/PDF.
2. Convertir PDF en image si nécessaire.
3. Corriger orientation.
4. Améliorer contraste.
5. Détecter zones candidates : tableau, surface, CRS.
6. Envoyer au provider OCR.
7. Parser texte et tableaux.
8. Normaliser coordonnées.
9. Calculer confiance.
10. Présenter à l’utilisateur pour validation.

### 18.2 Prompt d’extraction si LLM utilisé

Le LLM ne doit pas inventer de données. Il doit retourner `null` si une information est illisible.

Prompt système recommandé :

```text
Tu es un extracteur strict de données de plans topographiques béninois.
Ta mission est d'extraire uniquement les valeurs visibles dans le document.
N'invente jamais une coordonnée, une surface, un CRS ou une borne.
Si une valeur est ambiguë, retourne null et ajoute un warning.
Réponds uniquement en JSON valide conforme au schéma demandé.
```

Schéma JSON attendu :

```json
{
  "declared_surface_raw": "string|null",
  "declared_surface_m2": "number|null",
  "crs_raw": "string|null",
  "crs_detected": "string|null",
  "scale": "string|null",
  "points": [
    {
      "label": "string",
      "x": "number|null",
      "y": "number|null",
      "confidence": "number"
    }
  ],
  "warnings": ["string"]
}
```

---

## 19. Tests obligatoires

### 19.1 Backend

Utiliser `pytest`.

Tests minimaux :

- `test_parse_surface_to_m2.py` ;
- `test_coordinate_parser.py` ;
- `test_crs_detection.py` ;
- `test_geometry_area.py` ;
- `test_geometry_validity.py` ;
- `test_geojson_output.py` ;
- `test_audit_scoring.py` ;
- `test_openapi_schema.py` ;
- `test_external_service_clients_no_secret_logging.py`.

### 19.2 Frontend

Utiliser Vitest ou Jest + Testing Library.

Tests minimaux :

- upload form ;
- coordinate table editing ;
- CRS warning ;
- surface delta display ;
- audit score display ;
- map/local viewer fallback.

### 19.3 Tests d’acceptation

Cas de test :

1. image nette avec WGS84/UTM 31N ;
2. image floue mais tableau lisible ;
3. coordonnées locales non géoréférencées ;
4. surface déclarée différente de la surface calculée ;
5. polygone auto-intersecté ;
6. colonnes X/Y inversées ;
7. plusieurs parcelles sur un même plan.

---

## 20. Qualité, sécurité et conformité

### 20.1 Sécurité

- valider le type MIME ;
- limiter la taille des fichiers ;
- scanner les uploads si possible ;
- ne jamais exposer les documents uploadés en public ;
- isoler le stockage par projet/utilisateur ;
- ne jamais logger les clés API ;
- ne jamais logger les documents complets en clair dans les logs applicatifs ;
- ajouter rate limiting sur les endpoints d’upload et OCR.

### 20.2 Données personnelles

Les documents fonciers peuvent contenir des informations sensibles. Le prototype doit :

- permettre la suppression d’un projet ;
- permettre la suppression des fichiers ;
- stocker les documents dans un dossier non public ;
- afficher un avertissement de confidentialité ;
- prévoir anonymisation pour tests.

### 20.3 Licence et fournisseurs de cartes

- Google Maps ne doit pas être utilisé pour de l’analyse machine des tuiles ;
- OSM public tiles ne doivent pas être bulk-downloadés ;
- Esri imagery doit rester un support de visualisation sauf droits spécifiques ;
- pour la production, prévoir un fournisseur de tuiles commercial ou un accord de service.

---

## 21. Instructions pour l’IA de développement avec Collègue

### 21.1 Objectif pour l’agent

Construire un prototype fonctionnel end-to-end, pas une architecture parfaite.

Livrable attendu :

```text
Une application locale dockerisée permettant : upload image -> extraction -> validation -> calcul géométrique -> carte -> audit -> rapport PDF.
```

### 21.2 Garde-fous

L’agent doit :

- travailler par petites PR ou petits commits ;
- exécuter tests backend et frontend après chaque module ;
- ne pas ajouter de service externe sans fichier de documentation dans `docs/external_services/` ;
- ne pas intégrer de scraping Cadastre.bj ;
- ne pas utiliser Google tiles pour IA/analyse ;
- ne pas hardcoder de clés API ;
- générer et versionner `docs/swagger/topoaudit-openapi.json` ;
- conserver le mode fallback si Azure n’est pas configuré.

### 21.3 Ordre de réalisation imposé

#### Phase 0 — Scaffolding

Créer :

- monorepo ;
- Docker Compose ;
- FastAPI minimal ;
- Next.js minimal ;
- PostgreSQL/PostGIS ;
- `/api/health` ;
- docs initiales.

Critère d’acceptation :

```bash
docker compose up --build
curl http://localhost:8000/api/health
```

#### Phase 1 — Modèles et API projet/document

Créer :

- modèles DB ;
- migrations Alembic ;
- routes projects/documents ;
- upload fichier ;
- stockage local ;
- tests.

Critère : upload fichier fonctionnel et persistant.

#### Phase 2 — OCR adapter

Créer :

- interface `OcrProvider` ;
- provider Azure ;
- provider mock/local fallback ;
- parsing brut ;
- routes OCR ;
- logs service externe ;
- documentation Swagger.

Critère : résultat OCR simulé ou Azure stocké en DB.

#### Phase 3 — Extraction structurée

Créer :

- parser coordonnées ;
- parser surface ;
- détection CRS ;
- endpoint validation ;
- tableau modifiable frontend.

Critère : coordonnées corrigibles avant calcul.

#### Phase 4 — Moteur géométrique

Créer :

- reconstruction polygone ;
- calcul surface/périmètre/distances ;
- validation Shapely ;
- conversion CRS ;
- GeoJSON ;
- tests de surface.

Critère : surface recalculée cohérente sur exemples annotés.

#### Phase 5 — Carte

Créer :

- MapLibre viewer ;
- affichage GeoJSON ;
- affichage bornes ;
- affichage distances ;
- mode local si CRS inconnu.

Critère : parcelle visible sur carte si EPSG:32631, sinon canvas local.

#### Phase 6 — Audit et rapport

Créer :

- scoring ;
- findings ;
- génération PDF ;
- téléchargement rapport.

Critère : rapport PDF généré pour un exemple.

#### Phase 7 — Hardening

Créer :

- tests ;
- lint ;
- sécurité upload ;
- env docs ;
- export OpenAPI ;
- README final.

Critère : `pytest`, `npm test`, `npm run lint` passent.

---

## 22. Commandes attendues

### 22.1 Démarrage local

```bash
cp .env.example .env
docker compose up --build
```

Services :

```text
Frontend: http://localhost:3000
Backend:  http://localhost:8000
Swagger:  http://localhost:8000/api/docs
ReDoc:    http://localhost:8000/api/redoc
OpenAPI:  http://localhost:8000/api/openapi.json
```

### 22.2 Backend seul

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 22.3 Frontend seul

```bash
cd apps/web
npm install
npm run dev
```

### 22.4 Tests

```bash
cd apps/api
pytest -q

cd apps/web
npm test
npm run lint
```

### 22.5 Export Swagger/OpenAPI

```bash
cd apps/api
python scripts/export_openapi.py > ../../docs/swagger/topoaudit-openapi.json
```

---

## 23. Variables d’environnement

```env
# App
APP_ENV=local
APP_NAME=TopoAudit Benin
API_BASE_URL=http://localhost:8000/api
FRONTEND_URL=http://localhost:3000

# Database
DATABASE_URL=postgresql+psycopg://topoaudit:topoaudit@db:5432/topoaudit

# Storage
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=/data/uploads

# OCR
OCR_PROVIDER=mock
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=
AZURE_DOCUMENT_INTELLIGENCE_KEY=
AZURE_DOCUMENT_INTELLIGENCE_API_VERSION=2024-11-30
AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID=prebuilt-layout

# Maps
MAP_PROVIDER=esri_world_imagery
ESRI_WORLD_IMAGERY_URL=https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer
GOOGLE_MAPS_API_KEY=

# Security
MAX_UPLOAD_MB=25
SECRET_KEY=change-me
```

---

## 24. Définition de “Done” du prototype

Le prototype est considéré livré si :

1. un utilisateur peut créer un projet ;
2. un utilisateur peut uploader un scan ;
3. l’API lance une extraction OCR ou mock ;
4. les coordonnées apparaissent dans une table modifiable ;
5. l’utilisateur peut valider les coordonnées ;
6. le moteur calcule surface, périmètre et distances ;
7. le moteur détecte les erreurs majeures ;
8. la parcelle s’affiche sur carte si CRS exploitable ;
9. la parcelle s’affiche en local si CRS non exploitable ;
10. un audit avec score est généré ;
11. un rapport PDF est téléchargeable ;
12. Swagger est disponible ;
13. les docs des services externes existent ;
14. les tests principaux passent.

---

## 25. Backlog priorisé

| Priorité | Item | Impact | Effort |
|---:|---|---:|---:|
| P0 | Scaffolding monorepo Docker | Élevé | Moyen |
| P0 | FastAPI + Swagger + healthcheck | Élevé | Faible |
| P0 | Upload document | Élevé | Moyen |
| P0 | Parser surface ha/a/ca | Élevé | Faible |
| P0 | Saisie/validation coordonnées | Élevé | Moyen |
| P0 | Calcul géométrique | Très élevé | Moyen |
| P0 | Conversion EPSG:32631 -> EPSG:4326 | Très élevé | Faible |
| P0 | Carte MapLibre | Élevé | Moyen |
| P0 | Rapport PDF | Élevé | Moyen |
| P1 | Azure Document Intelligence adapter | Élevé | Moyen |
| P1 | Qualité image | Moyen | Moyen |
| P1 | Extraction automatique tableau avancée | Élevé | Élevé |
| P1 | Comparaison référence importée | Élevé | Moyen |
| P2 | Multi-parcelles | Moyen | Élevé |
| P2 | Auth complète | Moyen | Moyen |
| P2 | Paiement | Faible prototype | Moyen |

---

## 26. Points de vigilance majeurs

1. **OCR imparfait** : l’utilisateur doit corriger avant calcul.
2. **CRS inconnu** : ne pas afficher sur carte satellite sans géoréférencement.
3. **Cadastre non intégré officiellement** : ne pas promettre conformité cadastrale.
4. **Responsabilité juridique** : toujours parler d’audit préliminaire.
5. **Licences cartographiques** : respecter les restrictions Google/OSM/Esri.
6. **Données sensibles** : stockage sécurisé et suppression possible.
7. **Trop de cibles clients** : tester d’abord agences/promoteurs/notaires/particuliers.

---

## 27. Sources techniques et réglementaires à consulter

- FastAPI OpenAPI/Swagger : <https://fastapi.tiangolo.com/reference/openapi/docs/>
- FastAPI features / automatic docs : <https://fastapi.tiangolo.com/features/>
- Collègue MCP : <https://github.com/VynoDePal/Collegue>
- MapLibre GL JS : <https://www.maplibre.org/maplibre-gl-js/docs/>
- PROJ : <https://proj.org/>
- pyproj : <https://pyproj4.github.io/pyproj/stable/>
- EPSG:32631 : <https://epsg.io/32631>
- GeoJSON RFC 7946 : <https://datatracker.ietf.org/doc/html/rfc7946>
- Shapely : <https://shapely.readthedocs.io/>
- PostGIS : <https://postgis.net/docs/>
- Azure Document Intelligence REST : <https://learn.microsoft.com/en-us/rest/api/aiservices/document-models/analyze-document?view=rest-aiservices-v4.0%20(2024-11-30)>
- Azure REST API Specs : <https://github.com/Azure/azure-rest-api-specs>
- Esri ArcGIS REST APIs : <https://developers.arcgis.com/rest/>
- Esri World Imagery : <https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9>
- Google Map Tiles API policies : <https://developers.google.com/maps/documentation/tile/policies>
- OpenStreetMap Tile Usage Policy : <https://operations.osmfoundation.org/policies/tiles/>
- ANDF Cadastre : <https://andf.bj/cadastre/>
- Cadastre national du Bénin : <https://cadastre.bj/>
- CatIS Cadastre national du Bénin : <https://catis.xroad.bj/systems/IS00016>

---

## 28. Prompt maître à donner à l’IA de développement

```text
Tu es l’agent de développement responsable de construire le prototype TopoAudit Bénin.
Lis d’abord docs/PROJECT_SPEC.md en entier.
Objectif : construire un prototype SaaS local dockerisé avec Next.js/React/TypeScript côté frontend et FastAPI/Python/PostgreSQL/PostGIS côté backend.

Livrable final :
- upload d’un plan topographique scanné ;
- OCR ou OCR mock ;
- extraction des coordonnées ;
- validation humaine ;
- calcul géométrique ;
- conversion CRS si possible ;
- affichage carte ou local ;
- scoring ;
- rapport PDF ;
- Swagger/OpenAPI ;
- documentation des services externes.

Contraintes :
- ne jamais scraper Cadastre.bj ;
- ne jamais utiliser Google Maps pour analyse machine ;
- ne jamais promettre une conformité juridique ;
- ne jamais hardcoder de clé API ;
- créer des tests à chaque module ;
- exporter docs/swagger/topoaudit-openapi.json ;
- documenter chaque service externe utilisé dans docs/external_services/.

Procède par phases :
0 scaffolding,
1 projets/documents,
2 OCR adapter,
3 extraction structurée,
4 géométrie,
5 carte,
6 audit/rapport,
7 hardening.

À chaque phase :
- implémente ;
- ajoute tests ;
- lance tests ;
- corrige ;
- mets à jour la documentation ;
- produis un résumé des fichiers modifiés et des risques restants.
```

---

## 29. Décision finale pour v1

La première démo doit montrer un flux simple :

```text
Image de levé scannée
→ upload
→ coordonnées extraites ou mockées
→ correction humaine
→ calcul surface/périmètre/distances
→ carte si EPSG:32631
→ score de risque
→ rapport PDF
```

Tout le reste est secondaire tant que ce flux n’est pas fiable.
