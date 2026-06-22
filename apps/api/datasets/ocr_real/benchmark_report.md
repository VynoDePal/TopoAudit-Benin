# Rapport de benchmark OCR réel — TopoAudit Bénin

- Scans évalués : **5** (sur 6)  ·  provider : **Gemini (gemma-4-31b-it)**
- crs_detection_accuracy (== EPSG_32631) : **100%**
- surface_accuracy moyenne (déclarée vs calculée) : **99.9%**
- geometry_valid : **100%** (5/5 polygones simples)
- point_recall / coordinate_mae : **non évaluables** (relevé géodésique indépendant requis)

| Scan | CRS | Parcelles | Bornes | Surf. déclarée | Surf. calculée | Écart | Géom. |
|---|---|---|---|---|---|---|---|
| leve103.png | EPSG_32631 | 1 | 4 | 800.0 | 800.4 | 0.1% | OK |
| leve106.png | EPSG_32631 | 1 | 5 | 291.0 | 290.7 | 0.1% | OK |
| leve107.png | — | — | — | — | — | ÉCHEC: Gemini OCR request failed | — |
| leve114.png | EPSG_32631 | 1 | 7 | 677.0 | 676.5 | 0.1% | OK |
| leve120.png | EPSG_32631 | 1 | 4 | 462.0 | 462.3 | 0.1% | OK |
| leve150.png | EPSG_32631 | 1 | 5 | 441.0 | 440.9 | 0.0% | OK |

## Décision
**UTILISABLE pour une démo métier contrôlée** — détection CRS fiable, surfaces cohérentes avec les valeurs déclarées et géométries valides. La validation humaine des bornes reste requise (l'OCR ne fournit pas de confiance par point).

> Limite : la surface déclarée (imprimée sur le plan) sert de vérité terrain ; les coordonnées exactes ne sont pas validées contre un relevé géodésique indépendant.