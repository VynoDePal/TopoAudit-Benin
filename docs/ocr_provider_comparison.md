# Comparaison des providers OCR (Gemini/Gemma vs Mistral OCR 4)

Méthodologie et gabarit de comparaison des providers OCR sur des plans topographiques
réels. **Les chiffres ci-dessous ne sont PAS pré-remplis** : ils doivent provenir d'un run
réel (clé du provider + jeu de levées réelles gitignoré dans `datasets/ocr_real/`). Ne
jamais committer de scans/coordonnées réels — uniquement les métriques agrégées.

## Comment produire les rapports

Le script `apps/api/scripts/evaluate_real_ocr.py` accepte `--provider` :

```bash
# Gemini / Gemma 4 (clé GEMINI_API_KEY)
python scripts/evaluate_real_ocr.py --provider gemini --delay 8 > ../../docs/ocr_benchmark_gemini.md.json
# Mistral OCR 4 (clé MISTRAL_API_KEY)
python scripts/evaluate_real_ocr.py --provider mistral --delay 4 > ../../docs/ocr_benchmark_mistral.md.json
```

Le script sort proprement (`SKIP`, code 0) si la clé du provider est absente — il n'est
jamais exécuté en CI. La sortie JSON contient les métriques agrégées + `api_failure_rate`
+ `avg_seconds_per_scan` + la liste des erreurs (sans données sensibles).

## Métriques comparées

| Métrique | Gemini / Gemma 4 | Mistral OCR 4 |
| --- | --- | --- |
| `point_recall` | _à exécuter_ | _à exécuter_ |
| `coordinate_mae` | _à exécuter_ | _à exécuter_ |
| `surface_accuracy` | _à exécuter_ | _à exécuter_ |
| `parcel_count_accuracy` | _à exécuter_ | _à exécuter_ |
| `crs_detection_accuracy` | _à exécuter_ | _à exécuter_ |
| Taux d'échec API (`api_failure_rate`) | _à exécuter_ | _à exécuter_ |
| Temps moyen / scan (`avg_seconds_per_scan`) | _à exécuter_ | _à exécuter_ |
| Coût estimé (si disponible) | n/a | ~4 $/1000 pages (à vérifier) |
| Confiance OCR par borne | non fournie (« À valider ») | scores par mot (si exploitables) |

## Notes

- **Confiance OCR machine** : Mistral peut fournir une confiance par borne (agrégat des
  word scores). Gemini/Gemma n'en fournit pas → confiance « À valider » par borne.
- La confiance OCR n'est **jamais** une décision : la **validation humaine reste
  obligatoire** et distincte (`human_validated`).
- Tarifs/quotas Mistral : voir [mistral_ocr_4.md](external_services/mistral_ocr_4.md) —
  à vérifier avant toute mise en production.
