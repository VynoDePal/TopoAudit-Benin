# Esri World Imagery (fond satellite)

## Usage prévu
Fond de carte satellite (imagerie aérienne) pour la **visualisation** du tracé de la
parcelle à l'étape Rapport (bascule « Satellite »). Aucune valeur de preuve foncière :
purement illustratif.

## Endpoints
- Tuiles raster XYZ : `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`
- Pas de clé requise pour l'usage tuile public de base, MAIS soumis aux conditions Esri.
- Service de métadonnées : `.../World_Imagery/MapServer?f=json`.

## Variables d'environnement
| Variable | Rôle |
|---|---|
| `NEXT_PUBLIC_SATELLITE_TILE_URL` | URL de gabarit XYZ (optionnel ; défaut Esri World Imagery) |

Aucune clé secrète. Si une couche premium/ArcGIS Online authentifiée est utilisée, une
clé API serait requise (non utilisée dans le prototype).

## Limites
- **Conditions d'utilisation Esri** : usage non commercial / volume limité sans licence ;
  une démo/POC est généralement tolérée, une mise en production nécessite une licence ArcGIS.
- Attribution obligatoire : « Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community ».
- Pas de garantie d'actualité/précision de l'imagerie — **ne pas** s'en servir comme
  référence de bornage.

## Risques légaux / conformité
- Vérifier la licence Esri avant tout usage commercial.
- Ne jamais présenter l'imagerie comme une preuve cadastrale ou un relevé officiel.
