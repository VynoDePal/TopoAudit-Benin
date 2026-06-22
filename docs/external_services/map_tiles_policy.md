# Politique d'utilisation des tuiles cartographiques

## Usage prévu
Affichage du fond de carte (plan + satellite) pour visualiser le tracé des parcelles.
Deux sources : OpenStreetMap (plan) et Esri World Imagery (satellite — voir
[esri_world_imagery.md](esri_world_imagery.md)). Visualisation uniquement.

## Endpoints / fournisseurs
- OSM (plan) : `https://tile.openstreetmap.org/{z}/{x}/{y}.png`.
- Esri (satellite) : voir doc dédiée.
- Aucune API publique propriétaire ; ce sont des serveurs de tuiles raster XYZ.

## Variables d'environnement
| Variable | Rôle |
|---|---|
| `NEXT_PUBLIC_PLAN_TILE_URL` | Gabarit XYZ du fond « plan » (optionnel ; défaut OSM) |
| `NEXT_PUBLIC_SATELLITE_TILE_URL` | Gabarit XYZ du fond « satellite » (optionnel ; défaut Esri) |

## Limites & politique
- **OSM Tile Usage Policy** : pas d'usage massif/commercial sur les serveurs publics ;
  fixer un `User-Agent`/`Referer` clair ; prévoir un fournisseur de tuiles dédié
  (MapTiler, Stadia, self-host) avant toute mise en production.
- Mettre en cache raisonnablement ; ne pas marteler les serveurs (bulk download interdit).
- Attribution obligatoire pour chaque source (OSM : « © OpenStreetMap contributors »).

## Risques légaux / conformité
- Respecter les conditions de chaque fournisseur (OSM, Esri) ; le non-respect peut
  entraîner un blocage d'IP.
- Les fonds de carte sont **illustratifs** : aucune valeur juridique ni de bornage.
