# Rapport de benchmark OCR réel — TopoAudit Bénin

Provider : **Gemini (gemma-4-31b-it)** · exécuté **hors CI** via `scripts/evaluate_real_ocr.py` sur des scans anonymisés (`datasets/ocr_real/images/`, non versionnés).

- Scans du manifest : **5**  ·  évalués avec métriques : **4**  ·  erreurs Gemini transitoires : **1**
- point_recall : **100.0%**
- coordinate_mae : **0.00 m**
- surface_accuracy : **100.0%**
- parcel_count_accuracy : **100.0%**
- crs_detection_accuracy : **100.0%**

| Scan | CRS détecté | point_recall | coordinate_mae (m) | surface_acc | parcel_count_acc |
|---|---|---|---|---|---|
| leve106 | EPSG_32631 | 100.0% | 0.00 | 100.0% | 100.0% |
| leve150 | EPSG_32631 | 100.0% | 0.00 | 100.0% | 100.0% |
| leve151 | EPSG_32631 | 100.0% | 0.00 | 100.0% | 100.0% |
| leve163 | EPSG_32631 | 100.0% | 0.00 | 100.0% | 100.0% |

## Erreurs observées
- `leve103` : 502: Gemini OCR request failed

## Conclusion
**PRÊT pour une démo métier contrôlée.** Détection CRS, comptage de parcelles, surfaces déclarées et coordonnées reproductibles d'un passage à l'autre. La validation humaine des bornes reste obligatoire avant tout usage.

### Méthode & limites
- `expected_surface_m2` = **surface déclarée imprimée sur le plan** (vérité terrain) ; `expected_coordinates` = baseline OCR validée → `point_recall`/`coordinate_mae` mesurent la **reproductibilité** de l'OCR, pas un écart à un relevé géodésique indépendant (non disponible).
- Signal d'exactitude géométrique complémentaire (surface DÉCLARÉE vs surface CALCULÉE depuis les coordonnées OCR, mesuré via le flux d'audit) : **écarts 0,0–0,1 %** sur les levées validées.
- Certains scans échouent par intermittence côté Gemini (quota/erreur transitoire) — voir Erreurs observées.