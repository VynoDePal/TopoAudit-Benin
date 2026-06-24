# Mistral OCR 4 — service externe OCR

Mistral OCR 4 est un des **providers OCR sélectionnables** de TopoAudit-Benin (au même
titre que Gemma 4 / Gemini, et le mock local). Il extrait le texte structuré (Markdown,
tableaux) d'un plan topographique scanné et fournit des **scores de confiance par mot**.

## Usage prévu

OCR documentaire des plans topographiques scannés (bornes UTM 31N, surfaces déclarées).
Le résultat alimente le parser de bornes (tableaux Markdown supportés) et, lorsque les
scores de confiance par mot sont exploitables, une **confiance OCR machine par borne**.

> ⚠️ **OCR non décisionnel.** La confiance OCR est une aide à la relecture, jamais une
> décision. La **validation humaine de chaque borne reste obligatoire** avant l'audit.
> La validation humaine (`human_validated`) est un indicateur **séparé** de la confiance.

## Endpoint

```
POST https://api.mistral.ai/v1/ocr
```

- En-têtes : `Authorization: Bearer ${MISTRAL_API_KEY}`, `Content-Type: application/json`.
- Modèle par défaut : `mistral-ocr-latest`.
- Document transmis en base64 (`data:<mime>;base64,<...>`), JAMAIS d'image renvoyée
  (`include_image_base64: false`).

### Règle `document.type`

| `content_type` du document | `document.type` | clé |
| --- | --- | --- |
| `image/*` (png, jpeg) | `image_url` | `image_url` |
| `application/pdf` | `document_url` | `document_url` |

## Variables d'environnement

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `MISTRAL_API_KEY` | _(vide)_ | Clé API. **Jamais loggée ni committée** (ajoutée à la redaction). |
| `MISTRAL_API_ENDPOINT` | `https://api.mistral.ai/v1` | Base de l'API. |
| `MISTRAL_OCR_MODEL` | `mistral-ocr-latest` | Modèle OCR. |
| `MISTRAL_INCLUDE_BLOCKS` | `true` | Renvoyer les blocs typés + bounding boxes. |
| `MISTRAL_CONFIDENCE_GRANULARITY` | `word` | Granularité des scores : `none`, `word`, `page`. |

## Payload (envoyé par l'API TopoAudit)

```json
{
  "model": "mistral-ocr-latest",
  "document": {
    "type": "image_url",
    "image_url": "data:image/png;base64,<base64>"
  },
  "include_image_base64": false,
  "include_blocks": true,
  "confidence_scores_granularity": "word"
}
```

## Exemple cURL

```bash
curl https://api.mistral.ai/v1/ocr \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${MISTRAL_API_KEY}" \
  -d '{
    "model": "mistral-ocr-latest",
    "document": { "type": "image_url", "image_url": "data:image/png;base64,<base64_file>" },
    "include_image_base64": false,
    "include_blocks": true,
    "confidence_scores_granularity": "word"
  }' -o ocr_output.json
```

## Structure de la réponse exploitée

La réponse est un JSON `{"pages": [...]}`. Pour chaque page, TopoAudit lit :

- `pages[*].markdown` : texte (concaténé), **tableaux Markdown inclus** — parsés par
  `extract_parcels_from_ocr_text` (`| Borne | X | Y |`, séparateurs `|---|` ignorés,
  en-têtes non numériques ignorés, labels `B1` / `B.1` supportés).
- scores de confiance par mot (granularité `word`) : tout objet portant un texte
  (`text`/`word`/`token`) **et** un score (`confidence`/`score`) est récolté
  (`word_confidences`).

### Confidence par borne (stratégie prudente)

- La confiance d'une borne = **moyenne** des scores de `label` + `X` + `Y`.
- Si **un seul** token n'est pas associable à un score → confiance `null`
  (**jamais inventée**). Une confiance absente s'affiche « À valider », jamais « 0 % ».
- La confiance reste une **confiance OCR machine** ; elle n'est jamais dérivée de la
  validation humaine.

## Coûts (à vérifier avant production)

Indicatif (susceptible d'évoluer — se référer à la tarification officielle Mistral) :
~4 $ / 1000 pages (API), ~2 $ / 1000 pages en Batch API, ~5 $ / 1000 pages pour la
couche Document AI structurée. **Vérifier les tarifs et quotas à jour avant toute mise
en production.**

## Sécurité

- **Ne JAMAIS logger `MISTRAL_API_KEY`** : la clé est enregistrée dans la redaction des
  secrets (`register_secrets`, `app/config.py`) et n'apparaît jamais dans les logs ni
  dans les réponses de l'API (`GET /api/ocr/providers` ne renvoie aucune clé).
- Stocker la clé en variable d'environnement / gestionnaire de secrets, jamais en clair
  dans le dépôt.

## Limites

- OCR = outil de **compréhension documentaire**, pas un système de décision.
- Risque d'hallucination sur zones illisibles : la validation humaine des bornes est
  obligatoire (cf. colonne « Validé » à l'étape Validation).
- Sélection du provider à l'étape **Import** ; fallback mock autorisé uniquement en
  local (en staging/production, clé absente → `503`, jamais de fallback silencieux).
