# Politique d'utilisation des tuiles cartographiques

## Usage prévu
Affichage d'un **fond de carte satellite unique — Esri World Imagery** (voir
[esri_world_imagery.md](esri_world_imagery.md)) pour visualiser le tracé des parcelles
géoréférencées. La superposition OpenStreetMap a été retirée du prototype (carte hybride
peu lisible). Visualisation uniquement.

## Endpoints / fournisseurs
- Esri World Imagery (satellite) : tuiles raster XYZ — voir la doc dédiée.
- Aucune API publique propriétaire ; ce sont des serveurs de tuiles raster XYZ.

## Variables d'environnement
| Variable | Rôle |
|---|---|
| `NEXT_PUBLIC_SATELLITE_TILE_URL` | Gabarit XYZ du fond satellite (optionnel ; défaut Esri World Imagery) |

> `NEXT_PUBLIC_PLAN_TILE_URL` (ancien fond OSM) n'est plus utilisé depuis le passage à un
> fond satellite unique.

## Limites & politique
- Fond satellite **indicatif** : aucune valeur juridique ni de bornage.
- Mettre en cache raisonnablement ; ne pas marteler les serveurs (bulk download interdit).
- Attribution obligatoire (« Tiles © Esri, Maxar, Earthstar Geographics »).
- Prévoir un fournisseur de tuiles dédié (Esri sous licence, MapTiler, self-host) avant
  toute mise en production / usage commercial.

## Risques légaux / conformité
- Respecter les conditions d'Esri (voir esri_world_imagery.md) ; le non-respect peut
  entraîner un blocage d'IP.
- L'imagerie satellite est **illustrative** : ce n'est PAS une référence cadastrale ni une
  preuve foncière.
