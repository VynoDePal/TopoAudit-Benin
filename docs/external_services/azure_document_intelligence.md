# Azure AI Document Intelligence (OCR — fournisseur alternatif)

## Usage prévu
Fournisseur OCR alternatif à Gemini Vision pour extraire le texte (table de bornes,
surface) d'un plan topographique scanné. Sélectionné via `OCR_PROVIDER=azure`. À ce
stade prototype, le provider par défaut est Gemini (`gemma-4-31b-it`) ; Azure est une
option de repli/comparaison, non requise pour la démo.

## Endpoints
- API : Azure AI Document Intelligence (ex-Form Recognizer), REST.
- Analyse : `POST {endpoint}/documentintelligence/documentModels/{modelId}:analyze?api-version={version}`
  puis polling de l'`operation-location` jusqu'à `status: succeeded`.
- Modèle prébuilt utilisé : `prebuilt-layout` (texte + structure), configurable.
- Auth : en-tête `Ocp-Apim-Subscription-Key`.

## Variables d'environnement
| Variable | Rôle |
|---|---|
| `OCR_PROVIDER=azure` | Active ce provider |
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | URL de la ressource Azure |
| `AZURE_DOCUMENT_INTELLIGENCE_KEY` | Clé d'abonnement (secret — jamais commitée/loggée) |
| `AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID` | Modèle (défaut `prebuilt-layout`) |
| `AZURE_DOCUMENT_INTELLIGENCE_API_VERSION` | Version d'API |

En `APP_ENV=staging|production`, si `OCR_PROVIDER=azure` sans credentials → l'API
renvoie **503** (pas de repli silencieux vers le mock).

## Limites
- Service payant, quotas/débit selon le tier (risque de throttling).
- Latence : analyse asynchrone (polling) — quelques secondes par page.
- Qualité dépendante du scan ; pas de notion native de « borne topographique ».
- Les tests n'effectuent **aucun appel réseau réel** (provider mocké).

## Risques légaux / conformité
- Données envoyées à un service cloud Microsoft (résidence des données selon la région
  de la ressource) — vérifier la conformité avant d'y envoyer des documents fonciers réels.
- Respecter les conditions d'utilisation Azure et la réglementation béninoise sur les
  données personnelles/foncières.
