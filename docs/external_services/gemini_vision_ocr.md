# Gemini Vision OCR — extraction des plans topographiques

## Rôle du service

Gemini Vision est utilisé comme fournisseur OCR externe pour analyser les plans topographiques scannés ou photographiés. Dans ce dépôt, l'intégration est implémentée par `GeminiOcrProvider` dans `apps/api/app/ocr.py` et peut être sélectionnée avec `OCR_PROVIDER=gemini`.

Objectif métier du prompt envoyé à Gemini : extraire le texte lisible utile à l'audit préliminaire, en priorité :

- coordonnées UTM zone 31N des bornes/parcelles ;
- libellés de points ou bornes (`P1`, `P2`, etc.) ;
- surfaces déclarées en hectares, ares et centiares ;
- tableaux de coordonnées et mentions de système de coordonnées visibles.

La sortie attendue par TopoAudit est du texte brut. La validation humaine reste obligatoire avant tout calcul ou audit.

## Usage autorisé dans le prototype

- Envoyer à Gemini un fichier de document déjà importé par l'utilisateur, via le backend FastAPI.
- Utiliser Gemini uniquement pour l'extraction OCR/texte des plans.
- Conserver le fournisseur `mock` comme fallback lorsque la clé Gemini n'est pas configurée.
- Faire traiter ensuite le texte extrait par les parseurs internes et l'interface de validation humaine.

## Usage interdit

- Ne pas utiliser Gemini pour conclure à une conformité juridique, à une propriété foncière ou à une fraude prouvée.
- Ne pas envoyer de documents sans base légitime/consentement utilisateur.
- Ne pas journaliser la clé API Gemini ni le contenu complet de documents sensibles dans les logs applicatifs.
- Ne pas contourner les limites, politiques de quota ou conditions d'utilisation de Google.
- Ne pas utiliser Gemini comme substitut à la validation par géomètre ou à la validation humaine prévue par le produit.

## Variables d'environnement

```env
OCR_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_API_ENDPOINT=https://generativelanguage.googleapis.com/v1beta
GEMINI_MODEL=gemma-4-31b-it
OCR_RATE_LIMIT_PER_MINUTE=10
```

Notes :

- `GEMINI_API_KEY` est obligatoire pour activer réellement Gemini. Si elle est vide, le backend retombe sur `MockOcrProvider`.
- `GEMINI_API_ENDPOINT` est normalisé sans slash final par le code.
- `GEMINI_MODEL` vaut `gemma-4-31b-it` par défaut.
- `OCR_RATE_LIMIT_PER_MINUTE` protège les endpoints OCR internes par client en mémoire.

## Endpoints Gemini appelés

### Génération multimodale

```http
POST {GEMINI_API_ENDPOINT}/models/{GEMINI_MODEL}:generateContent
```

Valeurs par défaut utilisées par le prototype :

```http
POST https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent
```

Authentification :

```http
x-goog-api-key: ${GEMINI_API_KEY}
```

Timeout applicatif actuel : `60s` côté `httpx.Client`.

## Format de requête envoyé par le backend

Le backend encode le fichier importé en base64 et l'envoie dans `inline_data` avec le type MIME connu du document.

Exemple de payload JSON :

```json
{
  "contents": [
    {
      "role": "user",
      "parts": [
        {
          "text": "Extract all readable land survey OCR text from this document. Focus on UTM zone 31N coordinates, parcel point labels, and declared surfaces. Return plain text only, preserving coordinate tables and surface values."
        },
        {
          "inline_data": {
            "mime_type": "image/png",
            "data": "<document-base64>"
          }
        }
      ]
    }
  ]
}
```

Contraintes applicatives :

- si le type MIME du document est absent, le backend utilise `application/octet-stream` ;
- le fichier doit exister dans le stockage local avant l'appel ; sinon l'API interne retourne `404 Document file not found` ;
- les fichiers sont transmis inline, donc la taille effective doit rester compatible avec les limites Gemini et les contraintes d'upload du prototype.

## Format de réponse attendu

Le code lit les textes présents dans :

```text
candidates[*].content.parts[*].text
```

Exemple minimal :

```json
{
  "candidates": [
    {
      "content": {
        "parts": [
          {
            "text": "Surface déclarée: 05a 49ca\nP1 403825.84 707630.38\nP2 403836.57 707626.36"
          }
        ]
      }
    }
  ]
}
```

Le backend concatène tous les champs `text` trouvés avec des retours à la ligne, puis supprime les espaces en début/fin. Si aucun texte n'est extrait, l'API interne retourne `502 Gemini OCR response is empty`.

## Endpoints internes TopoAudit utilisant Gemini

Gemini n'est pas exposé directement au frontend. Le frontend appelle les endpoints OCR internes :

```http
POST /api/projects/{project_id}/documents/{document_id}/ocr
POST /api/ocr
```

Réponse interne normalisée :

```json
{
  "provider": "gemini",
  "text": "Surface déclarée: 05a 49ca\nP1 403825.84 707630.38",
  "document_id": "document-1",
  "project_id": "project-1"
}
```

Avant l'appel OCR, le backend vérifie que le projet existe et que le document appartient au projet. Après extraction, le projet est marqué comme OCR extrait par le workflow interne.

## Gestion d'erreurs et fallback

| Situation | Comportement TopoAudit |
| --- | --- |
| `OCR_PROVIDER=gemini` mais `GEMINI_API_KEY` vide | fallback automatique vers le provider `mock` |
| provider inconnu | `400 Unsupported OCR provider` |
| fichier absent | `404 Document file not found` |
| erreur HTTP Gemini (`4xx`/`5xx`) | `502 Gemini OCR request failed` |
| erreur réseau/timeout HTTPX | `502 Gemini OCR service unavailable` |
| réponse sans texte exploitable | `502 Gemini OCR response is empty` |
| limite OCR interne dépassée | `429 OCR rate limit exceeded` |

Le fallback mock est volontaire pour permettre les tests et démonstrations locales sans clé externe. En production, surveiller explicitement le champ `provider` de la réponse pour détecter un fallback non souhaité.

## Contraintes de sécurité et confidentialité

- La clé API doit être fournie uniquement par variable d'environnement ou secret manager, jamais hardcodée.
- Ne pas logger les en-têtes HTTP envoyés à Gemini, car ils contiennent `x-goog-api-key`.
- Les documents fonciers peuvent contenir des données personnelles ou patrimoniales ; limiter l'envoi aux documents strictement nécessaires et informer l'utilisateur.
- Prévoir une politique de rétention et de suppression des documents importés.
- Conserver l'exigence produit : l'OCR est une aide à l'extraction, pas une preuve juridique.

## Documentation officielle

- Gemini API — Generate content : <https://ai.google.dev/api/generate-content>
- Gemini API — Vision / image understanding : <https://ai.google.dev/gemini-api/docs/vision>
- Gemini API — Models : <https://ai.google.dev/gemini-api/docs/models>
- Google AI for Developers — API key security : <https://ai.google.dev/gemini-api/docs/api-key>

## Swagger/OpenAPI

Google fournit une documentation REST officielle pour Gemini, mais l'intégration du prototype s'appuie directement sur l'endpoint `generateContent` documenté ci-dessus. La documentation OpenAPI interne TopoAudit doit documenter les endpoints wrapper `/api/projects/{project_id}/documents/{document_id}/ocr` et `/api/ocr`, pas exposer la clé ni l'endpoint Gemini au client.

## Risques légaux, licence et exploitation

- Vérifier les conditions Google applicables au traitement de documents utilisateur et à la région de traitement des données.
- Éviter l'envoi de pièces contenant des données personnelles non nécessaires.
- Prévoir une alternative ou fallback opérationnel en cas d'indisponibilité, quota atteint ou changement de modèle.
- Afficher dans le produit que l'extraction peut contenir des erreurs et doit être validée humainement.
