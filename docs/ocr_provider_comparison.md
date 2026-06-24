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

## Conclusion (à valider par benchmark complémentaire)

- **Provider par défaut : Gemma 4 / Gemini.** Recommandé pour les **plans topographiques
  scannés** : prompt spécialisé, plus fiable sur les **coordonnées visibles** (constat
  terrain sur plans béninois réels). C'est le défaut frontend (ordre Gemma → Mistral →
  Mock via `GET /api/ocr/providers`) et serveur (`OCR_PROVIDER=gemini`).
- **Mistral OCR 4 : disponible, rapide, expérimental.** Plus rapide (~9×) et peut fournir
  une confiance par borne, mais peut **mal structurer les tables de coordonnées** sur
  certains plans (cf. leve106). Un bandeau le rappelle quand Mistral est utilisé.
- **Le choix définitif reste à valider** par un benchmark sur **scans réels** avec une
  **clé Gemini non limitée** : les `502` Gemini ci-dessus viennent du **quota free-tier**
  (artefact de la clé, pas du modèle), donc `api_failure_rate` n'est pas comparable en
  l'état. Aucune affirmation « Mistral meilleur » ne doit être tirée de ces chiffres.

## Limites

- **Échantillon réel = 5 scans** (gitignorés). Indicatif, non statistique.
- **Gemini pénalisé par le quota free-tier** (`502`) : `api_failure_rate` reflète la clé,
  pas le modèle. À refaire avec un compte payant pour une comparaison équitable — c'est la
  raison pour laquelle le défaut reste **Gemma/Gemini** malgré le `api_failure_rate` brut.
- **Mistral n'est pas infaillible** : leve106 a échoué le parsing (CRS non détecté, 0
  borne). L'OCR n'est **jamais décisionnel** — la **validation humaine de chaque borne
  reste obligatoire** (colonne « Validé »), confiance OCR machine distincte de
  `human_validated`.
- **Coûts Mistral** à confirmer avant mise en production (tarifs susceptibles d'évoluer).
