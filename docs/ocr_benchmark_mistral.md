# Benchmark OCR réel — Mistral OCR 4

Exécution réelle de `apps/api/scripts/evaluate_real_ocr.py --provider mistral` sur le jeu
de **5 levées réelles** (`datasets/ocr_real/manifest_real.json` + `images/`, **gitignorés**
— seules les métriques agrégées sont publiées, jamais les scans ni les coordonnées).

- Date : 2026-06-24
- Modèle : `mistral-ocr-latest` (provider `mistral`)
- Commande : `python scripts/evaluate_real_ocr.py --dataset datasets/ocr_real/manifest_real.json --provider mistral --delay 4`

## Résultats agrégés

| Métrique | Valeur |
| --- | --- |
| Scans tentés | 5 |
| Scans réussis | **5** |
| `api_failure_rate` | **0,00** |
| `avg_seconds_per_scan` | **3,39 s** |
| `point_recall` | 0,80 |
| `coordinate_mae` | 0,001 m |
| `surface_accuracy` | 0,80 |
| `parcel_count_accuracy` | 0,80 |
| `crs_detection_accuracy` | 0,80 |

## Détail par cas (qualité, sans données sensibles)

| Cas | API | point_recall | coordinate_mae | surface | crs |
| --- | --- | --- | --- | --- | --- |
| leve103 | OK | 1,0 | 0,0 m | 1,0 | EPSG_32631 ✓ |
| leve106 | OK | **0,0** | — | **0,0** | **UNKNOWN_CRS** ✗ |
| leve150 | OK | 1,0 | 0,004 m | 1,0 | EPSG_32631 ✓ |
| leve151 | OK | 1,0 | 0,0 m | 1,0 | EPSG_32631 ✓ |
| leve163 | OK | 1,0 | 0,0 m | 1,0 | EPSG_32631 ✓ |

## Lecture

- **Fiabilité API : 100 %** (5/5, aucun échec) — contraste fort avec Gemini (4/5 en 502).
- **Latence ~9× inférieure** à Gemini (3,4 s vs 30,8 s/scan).
- **4/5 cas parfaits** : recall 1,0, MAE ≤ 0,004 m, surface exacte, CRS détecté.
- **1 échec parsing (leve106)** : Mistral a répondu mais le parser n'a pas extrait de
  bornes exploitables (CRS `UNKNOWN_CRS`, recall 0). Confirme que la **validation humaine
  reste obligatoire** — l'OCR n'est jamais décisionnel.
- Mistral fournit des **scores de confiance par mot** → confiance OCR par borne possible
  (distincte de la validation humaine).
- **Coût** (à vérifier avant prod) : ~4 $/1000 pages (API), ~2 $/1000 pages (Batch),
  ~5 $/1000 pages (Document AI structuré).

Comparaison complète : voir [ocr_provider_comparison.md](ocr_provider_comparison.md).
