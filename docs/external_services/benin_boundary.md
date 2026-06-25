# Frontière du Bénin — source du contrôle territorial

Le contrôle territorial Bénin ([territory_check.md](../territory_check.md)) s'appuie sur un
polygone de frontière nationale.

## Source

- **Natural Earth — Admin 0 Countries (1:50m)**, entité `BEN` (Bénin).
- Fichier : `apps/api/app/data/benin_boundary.geojson` (FeatureCollection, 1 feature,
  ~147 sommets, EPSG:4326).
- Domaine public (Natural Earth est libre de droits).

## Usage

- **Prototype / contrôle territorial GROSSIER** : vérifier qu'un tracé géoréférencé tombe
  bien dans le Bénin (et non dans un pays voisin ou dans l'océan).
- **NON référence cadastrale.** La frontière 1:50m est simplifiée (précision ~quelques
  centaines de mètres à la côte/aux limites). Elle ne sert qu'à un contrôle de cohérence,
  jamais à délimiter une parcelle.

## Pour la production

Utiliser une **frontière officielle ou institutionnelle** (IGN Bénin / ANDF / source
gouvernementale) à la résolution adéquate. Remplacer `benin_boundary.geojson` par la
source officielle (même format GeoJSON EPSG:4326, propriété `geometry` Polygon/MultiPolygon)
suffit — `load_benin_boundary()` la chargera sans changement de code.

## Rafraîchir le fichier (prototype)

```bash
curl -s https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
f=next(x for x in d['features'] if x['properties'].get('ADM0_A3')=='BEN' or str(x['properties'].get('SOVEREIGNT')).upper()=='BENIN'); \
print(json.dumps({'type':'FeatureCollection','features':[{'type':'Feature','properties':{'name':'Benin','iso_a3':'BEN','source':'Natural Earth Admin 0 (1:50m)'},'geometry':f['geometry']}]}))" \
  > apps/api/app/data/benin_boundary.geojson
```
