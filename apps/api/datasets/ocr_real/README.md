# Benchmark OCR réel — TopoAudit Bénin

Jeu d'évaluation pour mesurer la qualité de l'extraction (OCR → parser → détection CRS)
contre une **vérité terrain**, sur de vrais plans topographiques scannés.

## ⚠️ Politique d'anonymisation (important)

**Ne jamais committer de documents fonciers réels non anonymisés.** Les images de plans
réels contiennent des données personnelles/foncières sensibles. Le dossier `images/` est
**gitignoré** : on y dépose localement les scans pour les évaluations « réelles », mais
ils ne sont jamais versionnés. Le dépôt ne contient que :
- ce README,
- `manifest.json` : cas **synthétiques/anonymisés** (texte OCR + vérité terrain) servant à
  l'évaluation **offline** du parser.

## Format du manifest (`manifest.json`)

Chaque cas :

| Champ | Description |
|---|---|
| `id` | identifiant du cas |
| `file_path` | chemin de l'image (sous `images/`, gitignoré) — pour l'éval OCR réelle |
| `scan_quality` | `clear` \| `blurry` \| `old` \| `synthetic` |
| `ocr_text` | texte OCR de référence (pour l'éval offline du parser) |
| `expected_crs` | statut CRS attendu (`EPSG_32631`, `EPSG_4326`, `LOCAL_ONLY`, …) |
| `expected_parcel_count` | nombre de parcelles attendu |
| `expected_surface_m2` | surface déclarée attendue (m²) |
| `expected_coordinates` | bornes attendues : `[{label, x, y}, …]` |

## Métriques

- **point_recall** — part des bornes attendues retrouvées (tolérance ~2 m).
- **coordinate_mae** — erreur moyenne (m) sur les bornes appariées.
- **surface_accuracy** — `1 − |surface_extraite − attendue| / attendue` (borné [0,1]).
- **parcel_count_accuracy** — exactitude du nombre de parcelles.
- **crs_detection_accuracy** — CRS détecté == CRS attendu.

## Scripts

### `evaluate_parser.py` (offline, sans réseau — CI-friendly)
Évalue le parser + la détection CRS sur les `ocr_text` du manifest. Aucun appel réseau.

```bash
cd apps/api
PYTHONPATH=. python scripts/evaluate_parser.py \
  --dataset datasets/ocr_real/manifest.json \
  --min-point-recall 0.9 --min-crs-accuracy 1.0
```

### `evaluate_real_ocr.py` (optionnel — nécessite une clé Gemini/Azure, JAMAIS en CI)
Lance l'OCR **réel** sur les images de `images/` (présentes localement), puis applique le
parser et compare à la vérité terrain. Requiert `OCR_PROVIDER` + la clé correspondante.
Non exécuté en CI par défaut (sort proprement si aucune clé / aucune image).

```bash
cd apps/api
OCR_PROVIDER=gemini GEMINI_API_KEY=... PYTHONPATH=. python scripts/evaluate_real_ocr.py \
  --dataset datasets/ocr_real/manifest.json
```
