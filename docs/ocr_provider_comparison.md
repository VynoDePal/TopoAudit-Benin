# Comparaison des providers OCR — Gemma 4 / Gemini vs Mistral OCR 4

Comparaison **réelle** sur les **mêmes 5 levées réelles** (gitignorées ; seules les
métriques agrégées sont publiées). Détails : [ocr_benchmark_gemini.md](ocr_benchmark_gemini.md)
et [ocr_benchmark_mistral.md](ocr_benchmark_mistral.md).

- Date : 2026-06-24
- Jeu : `datasets/ocr_real/manifest_real.json` (5 cas, vérité terrain) — `images/` non committées.
- Reproduire :
  ```bash
  python scripts/evaluate_real_ocr.py --dataset datasets/ocr_real/manifest_real.json --provider gemini  --delay 8
  python scripts/evaluate_real_ocr.py --dataset datasets/ocr_real/manifest_real.json --provider mistral --delay 4
  ```

## Tableau comparatif

| Métrique | Gemma 4 / Gemini | Mistral OCR 4 |
| --- | --- | --- |
| Scans réussis | **1 / 5** | **5 / 5** |
| `api_failure_rate` | 0,80 (4× `502`) | **0,00** |
| `avg_seconds_per_scan` | 30,79 s | **3,39 s** |
| `point_recall` | 1,0 *(n=1)* | 0,80 *(n=5)* |
| `coordinate_mae` | 0,0 m *(n=1)* | 0,001 m *(n=5)* |
| `surface_accuracy` | 1,0 *(n=1)* | 0,80 *(n=5)* |
| `parcel_count_accuracy` | 1,0 *(n=1)* | 0,80 *(n=5)* |
| `crs_detection_accuracy` | 1,0 *(n=1)* | 0,80 *(n=5)* |
| Confiance OCR par borne | non | **oui** (word scores) |
| Coût indicatif | dépend du compte Google | ~4 $/1000 pages (à vérifier) |

> ⚠️ Les scores de précision Gemini portent sur **1 seul scan réussi** (les 4 autres en
> `502`) → non représentatifs. Mistral est évalué sur les **5 scans**.

## Conclusion

- **Provider recommandé pour la démo : Mistral OCR 4.** Fiabilité 100 % (vs 20 % pour
  Gemini ici), ~9× plus rapide, et confiance OCR par borne. Une démo métier ne peut pas
  se permettre 80 % d'échecs API.
- **Provider recommandé par défaut : Mistral OCR 4 lorsque `MISTRAL_API_KEY` est
  configurée** — c'est déjà le défaut **frontend dynamique** (ordre Mistral → Gemini →
  Mock via `GET /api/ocr/providers`). Sans clé Mistral : Gemini si configuré, sinon mock.
- **Quand préférer Gemini** : si l'on dispose d'un **compte Google payant** (sans le
  quota free-tier responsable des `502`), Gemini est exact sur les cas traités ; il reste
  utile en repli ou pour comparaison. À ré-évaluer avec une clé non limitée.

## Limites

- **Échantillon réel = 5 scans** (gitignorés). Conclusions indicatives, pas statistiques.
- **Gemini pénalisé par le quota free-tier** (`502`) : `api_failure_rate` reflète la clé,
  pas seulement le modèle. À refaire avec un compte payant pour une comparaison équitable.
- **Mistral n'est pas infaillible** : leve106 a échoué le parsing (CRS non détecté, 0
  borne). L'OCR n'est **jamais décisionnel** — la **validation humaine de chaque borne
  reste obligatoire** (colonne « Validé »), et la confiance OCR machine reste distincte de
  `human_validated`.
- **Coûts Mistral** à confirmer avant mise en production (tarifs susceptibles d'évoluer).
