# Benchmark OCR réel — Gemma 4 / Gemini

Exécution réelle de `apps/api/scripts/evaluate_real_ocr.py --provider gemini` sur le jeu de
**5 levées réelles** (`datasets/ocr_real/manifest_real.json` + `images/`, **gitignorés** —
seules les métriques agrégées sont publiées, jamais les scans ni les coordonnées).

- Date : 2026-06-24
- Modèle : `gemma-4-31b-it` (provider `gemini`)
- Commande : `python scripts/evaluate_real_ocr.py --dataset datasets/ocr_real/manifest_real.json --provider gemini --delay 8`

## Résultats agrégés

| Métrique | Valeur |
| --- | --- |
| Scans tentés | 5 |
| Scans réussis | **1** |
| `api_failure_rate` | **0,80** (4 échecs `502 Gemini OCR request failed`) |
| `avg_seconds_per_scan` | 30,79 s (sur le scan réussi) |
| `point_recall` | 1,0 *(n=1)* |
| `coordinate_mae` | 0,0 m *(n=1)* |
| `surface_accuracy` | 1,0 *(n=1)* |
| `parcel_count_accuracy` | 1,0 *(n=1)* |
| `crs_detection_accuracy` | 1,0 *(n=1)* |

## Détail par cas (qualité, sans données sensibles)

| Cas | API | point_recall | coordinate_mae | surface | crs |
| --- | --- | --- | --- | --- | --- |
| leve163 | OK | 1,0 | 0,0 m | 1,0 | EPSG_32631 ✓ |
| leve103 | ❌ 502 | — | — | — | — |
| leve106 | ❌ 502 | — | — | — | — |
| leve150 | ❌ 502 | — | — | — | — |
| leve151 | ❌ 502 | — | — | — | — |

## Lecture

- **Quand Gemini répond, l'extraction est exacte** (leve163 : recall 1,0, MAE 0,0 m, CRS
  correct).
- **MAIS 4/5 appels échouent en `502`** : il s'agit très probablement d'une limite de
  **quota / rate-limit de la clé free-tier** (cf. mémoire projet : 429/502 après quelques
  scans). Un compte payant améliorerait `api_failure_rate`.
- **Latence ~10× supérieure** à Mistral (30,8 s vs 3,4 s/scan).
- Gemini **ne fournit pas de confiance OCR par borne** → bornes « À valider », score
  d'extraction `needs_human_validation`.

⚠️ Échantillon réussi = **1 cas** → les scores de précision Gemini ne sont **pas
représentatifs** ici (limités par les 502). Comparaison : voir
[ocr_provider_comparison.md](ocr_provider_comparison.md).
