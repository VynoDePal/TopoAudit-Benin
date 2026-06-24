import base64
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Protocol

import httpx
from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field

from app.config import settings

MOCK_OCR_TEXT = """PLAN TOPOGRAPHIQUE - MOCK OCR
Parcelle A
Surface déclarée: 05a 49ca
Coordonnées détectées:
P1 403825.84 707630.38
P2 403836.57 707626.36
P3 403840.12 707641.10
P4 403829.20 707645.42
""".strip()

# Backoff (secondes) entre tentatives Gemini en cas d'erreur réseau transitoire.
GEMINI_RETRY_BACKOFF_SECONDS = 1.5


class OcrPoint(BaseModel):
    label: str
    x: float
    y: float
    # Confiance OCR machine par borne : None tant que le provider n'en fournit pas
    # (ne JAMAIS forcer 0). Distincte de la validation humaine.
    confidence: float | None = None


class OcrParsedParcel(BaseModel):
    label: str
    declared_surface_m2: float | None = None
    point_count: int = 0
    points: list[OcrPoint] = Field(default_factory=list)


class OcrProviderResult(BaseModel):
    """Résultat interne d'un provider OCR (texte + traçabilité + confiances éventuelles).

    ``word_confidences`` : confiances OCR MACHINE par mot (ex. Mistral), liste de
    ``{"text": str, "confidence": float}`` — JAMAIS la validation humaine. None si le
    provider n'en fournit pas (Gemini/Gemma, mock).
    """

    text: str
    provider: str
    model: str | None = None
    raw_response: dict | None = None
    page_confidence: float | None = None
    word_confidences: list[dict] | None = None


class OcrProviderInfo(BaseModel):
    id: str = Field(examples=["mistral"])
    label: str = Field(examples=["Mistral OCR 4"])
    configured: bool = Field(examples=[True])
    supports_word_confidence: bool = Field(examples=[True])


class OcrResult(BaseModel):
    provider: str = Field(examples=["mock"])
    # Traçabilité du provider : configuré (demandé) vs réel (après fallback éventuel),
    # et drapeau si le résultat vient du mock (pour la démo / le débogage).
    configured_provider: str = Field(examples=["gemini"])
    actual_provider: str = Field(examples=["mock"])
    is_mock_result: bool = Field(default=False, examples=[True])
    # Modèle réellement utilisé par le provider (None pour le mock).
    provider_model: str | None = Field(default=None, examples=["mistral-ocr-latest"])
    extracted_text: str
    parsed_parcels: list[OcrParsedParcel] = Field(default_factory=list)
    # Statut CRS détecté (EPSG_32631, EPSG_4326, LOCAL_ONLY, UNKNOWN_CRS, NEEDS_GEOREFERENCING).
    detected_crs: str = Field(examples=["EPSG_32631"])
    # Statut du score d'extraction au stade OCR (avant validation humaine).
    extraction_score_status: str = Field(examples=["needs_human_validation"])
    document_id: str
    project_id: str


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, *, limit: int, window_seconds: int = 60) -> None:
        if limit <= 0:
            return

        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] >= window_seconds:
            hits.popleft()

        if len(hits) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="OCR rate limit exceeded",
            )

        hits.append(now)

    def reset(self) -> None:
        self._hits.clear()


ocr_rate_limiter = InMemoryRateLimiter()


def enforce_ocr_rate_limit(request: Request) -> None:
    client_host = request.client.host if request.client else "unknown"
    ocr_rate_limiter.check(f"ocr:{client_host}", limit=settings.ocr_rate_limit_per_minute)


def _azure_is_configured() -> bool:
    return bool(settings.azure_document_intelligence_endpoint and settings.azure_document_intelligence_key)


def _azure_analyze_url() -> str:
    endpoint = settings.azure_document_intelligence_endpoint.rstrip("/")
    model_id = settings.azure_document_intelligence_model_id
    api_version = settings.azure_document_intelligence_api_version
    return f"{endpoint}/documentintelligence/documentModels/{model_id}:analyze?api-version={api_version}"


def _gemini_is_configured() -> bool:
    return bool(settings.gemini_api_key)


def _gemini_generate_url() -> str:
    endpoint = settings.gemini_api_endpoint.rstrip("/")
    model = settings.gemini_model
    return f"{endpoint}/models/{model}:generateContent"


def _mistral_is_configured() -> bool:
    return bool(settings.mistral_api_key)


def _mistral_ocr_url() -> str:
    return f"{settings.mistral_api_endpoint.rstrip('/')}/ocr"


class OcrProvider(Protocol):
    name: str

    @property
    def model(self) -> str | None:
        ...

    def is_configured(self) -> bool:
        ...

    def extract_text(self, storage_path: str, content_type: str | None) -> str:
        ...

    def extract(self, storage_path: str, content_type: str | None) -> OcrProviderResult:
        ...


class MockOcrProvider:
    name = "mock"
    model: str | None = None

    def is_configured(self) -> bool:
        return True

    def extract_text(self, storage_path: str, content_type: str | None) -> str:
        return MOCK_OCR_TEXT

    def extract(self, storage_path: str, content_type: str | None) -> OcrProviderResult:
        return OcrProviderResult(text=MOCK_OCR_TEXT, provider=self.name, model=self.model)


class AzureOcrProvider:
    name = "azure"

    @property
    def model(self) -> str | None:
        return settings.azure_document_intelligence_model_id

    def is_configured(self) -> bool:
        return _azure_is_configured()

    def extract_text(self, storage_path: str, content_type: str | None) -> str:
        return _extract_text_with_azure(storage_path, content_type)

    def extract(self, storage_path: str, content_type: str | None) -> OcrProviderResult:
        return OcrProviderResult(
            text=self.extract_text(storage_path, content_type), provider=self.name, model=self.model
        )


class GeminiOcrProvider:
    name = "gemini"

    @property
    def model(self) -> str | None:
        return settings.gemini_model

    def is_configured(self) -> bool:
        return _gemini_is_configured()

    def extract_text(self, storage_path: str, content_type: str | None) -> str:
        return _extract_text_with_gemini(storage_path, content_type)

    def extract(self, storage_path: str, content_type: str | None) -> OcrProviderResult:
        # Gemini/Gemma ne fournit pas de confiance par mot exploitable → word_confidences=None
        # (la confiance par borne restera donc null côté parser : jamais inventée).
        return OcrProviderResult(
            text=self.extract_text(storage_path, content_type), provider=self.name, model=self.model
        )


class MistralOcrProvider:
    name = "mistral"

    @property
    def model(self) -> str | None:
        return settings.mistral_ocr_model

    def is_configured(self) -> bool:
        return _mistral_is_configured()

    def extract(self, storage_path: str, content_type: str | None) -> OcrProviderResult:
        return _extract_with_mistral(storage_path, content_type)

    def extract_text(self, storage_path: str, content_type: str | None) -> str:
        return self.extract(storage_path, content_type).text


OCR_PROVIDER_FACTORIES = {
    "mock": MockOcrProvider,
    "azure": AzureOcrProvider,
    "gemini": GeminiOcrProvider,
    "mistral": MistralOcrProvider,
}

# Métadonnées exposées par GET /api/ocr/providers (jamais les clés API). Azure reste
# utilisable via ?provider=azure mais n'est pas listé dans l'UI (legacy).
_PUBLIC_PROVIDERS: tuple[str, ...] = ("gemini", "mistral", "mock")
_PROVIDER_LABELS = {
    "gemini": "Gemma 4 / Gemini",
    "mistral": "Mistral OCR 4",
    "mock": "Mock OCR",
    "azure": "Azure Document Intelligence",
}
_PROVIDER_SUPPORTS_WORD_CONFIDENCE = {"gemini": False, "mistral": True, "mock": False, "azure": False}


def list_ocr_providers() -> list[OcrProviderInfo]:
    """Liste des providers OCR sélectionnables + leur état (sans jamais exposer de clé)."""
    providers: list[OcrProviderInfo] = []
    for provider_id in _PUBLIC_PROVIDERS:
        factory = OCR_PROVIDER_FACTORIES[provider_id]
        providers.append(
            OcrProviderInfo(
                id=provider_id,
                label=_PROVIDER_LABELS[provider_id],
                configured=factory().is_configured(),
                supports_word_confidence=_PROVIDER_SUPPORTS_WORD_CONFIDENCE[provider_id],
            )
        )
    return providers


def _allows_unconfigured_ocr_fallback() -> bool:
    return settings.app_env.strip().lower() not in {"staging", "production"}


def get_ocr_provider(provider_name: str | None = None) -> OcrProvider:
    configured_provider = (provider_name or settings.ocr_provider).strip().lower()
    provider_factory = OCR_PROVIDER_FACTORIES.get(configured_provider)
    if provider_factory is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported OCR provider")

    provider = provider_factory()
    if provider.is_configured():
        return provider
    # Clé absente : en local on retombe sur le mock (démo) ; en staging/production on
    # refuse (jamais de fallback silencieux). actual_provider="mock" tracera le fallback.
    if _allows_unconfigured_ocr_fallback():
        return MockOcrProvider()

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"OCR provider '{configured_provider}' credentials are not configured",
    )


def extract_text_from_document(storage_path: str, content_type: str | None) -> tuple[str, str]:
    """Compat (anciens tests) : texte + nom du provider, sans confiances."""
    provider = get_ocr_provider()
    return provider.extract_text(storage_path, content_type), provider.name


def extract_ocr_from_document(
    storage_path: str, content_type: str | None, provider_name: str | None = None
) -> OcrProviderResult:
    """Nouveau flux : résultat OCR complet (texte + provider réel + confiances éventuelles).

    ``provider_name`` permet de choisir le provider à l'appel (sinon settings.ocr_provider).
    Le ``.provider`` retourné est le provider RÉEL (``mock`` après fallback local).
    """
    provider = get_ocr_provider(provider_name)
    return provider.extract(storage_path, content_type)


def _extract_text_with_gemini(storage_path: str, content_type: str | None) -> str:
    path = Path(storage_path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found")

    # Prompt durci pour la PRÉCISION : lecture chiffre par chiffre, UNE seule liste finale
    # (ne pas répéter les bornes — sinon un modèle verbeux les liste plusieurs fois et la
    # géométrie est corrompue), dans l'ORDRE de la table = ordre du contour de la parcelle
    # (polygone simple/valide). La dédup d'écho est assurée côté parser (uploads.py).
    prompt = (
        "Tu es un OCR EXPERT de plans topographiques (Bénin). Lis TRÈS attentivement la ou les "
        "tables de coordonnées (colonnes Borne/X/Y ; coordonnées UTM zone 31N à ~2 décimales) en "
        "vérifiant CHAQUE chiffre. Donne UNE SEULE liste finale, dans l'ORDRE EXACT de la table "
        "(= ordre du contour de la parcelle), une borne par ligne au format EXACT `LABEL X Y` "
        "(nombres séparés par un espace, ex. `B1 380557.07 747662.20`). NE RÉPÈTE AUCUNE borne. "
        "Si plusieurs parcelles, précède chaque groupe d'une ligne `Parcelle <n>`. Termine chaque "
        "parcelle par une ligne `SURFACE: <valeur ha/a/ca>`. N'écris RIEN d'autre."
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": content_type or "application/octet-stream",
                            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                        }
                    },
                ],
            }
        ],
        # temperature 0 : lecture déterministe, moins de « créativité » sur les chiffres.
        "generationConfig": {"temperature": 0},
    }
    headers = {"x-goog-api-key": settings.gemini_api_key}

    # Timeout large : gemma-4-31b (modèle « raisonnant », multimodal) met couramment
    # 30-60 s+ sur un scan ; 60 s était trop juste → ReadTimeout intermittent.
    # Retry : le DNS du conteneur (résolveur Docker) et le réseau échouent parfois de
    # façon transitoire (« Temporary failure in name resolution », ReadTimeout) ; on
    # réessaie avec backoff. Une réponse d'erreur HTTP de Gemini (4xx/5xx) est, elle,
    # définitive → pas de retry.
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=180.0) as client:
                response = client.post(_gemini_generate_url(), headers=headers, json=payload)
                response.raise_for_status()
                return _extract_gemini_text(response.json())
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini OCR request failed",
            ) from exc
        except httpx.HTTPError as exc:
            # ConnectError / Timeout / échec DNS → transitoire, on réessaie.
            last_exc = exc
            if attempt < 2:
                time.sleep(GEMINI_RETRY_BACKOFF_SECONDS * (attempt + 1))

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Gemini OCR service unavailable",
    ) from last_exc


def _extract_gemini_text(payload: dict[str, Any]) -> str:
    texts: list[str] = []
    for candidate in payload.get("candidates", []):
        content = candidate.get("content") or {}
        for part in content.get("parts", []):
            text = part.get("text")
            if isinstance(text, str):
                texts.append(text)

    text_content = "\n".join(texts).strip()
    if not text_content:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Gemini OCR response is empty")
    return text_content


def _extract_with_mistral(storage_path: str, content_type: str | None) -> OcrProviderResult:
    path = Path(storage_path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found")

    mime = (content_type or "application/octet-stream").lower()
    data_url = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
    # Règle document.type : PDF → document_url ; image/* → image_url.
    if mime == "application/pdf":
        document = {"type": "document_url", "document_url": data_url}
    else:
        document = {"type": "image_url", "image_url": data_url}

    payload = {
        "model": settings.mistral_ocr_model,
        "document": document,
        "include_image_base64": False,
        "include_blocks": settings.mistral_include_blocks,
        "confidence_scores_granularity": settings.mistral_confidence_granularity,
    }
    headers = {
        "Authorization": f"Bearer {settings.mistral_api_key}",
        "Content-Type": "application/json",
    }

    # Timeout large (OCR documentaire multi-pages) ; erreur HTTP = définitive (pas de retry).
    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(_mistral_ocr_url(), headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Mistral OCR request failed") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Mistral OCR service unavailable") from exc

    return _parse_mistral_response(data)


def _collect_word_confidences(node: Any, out: list[dict]) -> None:
    """Récolte récursivement les confiances OCR machine par mot.

    Robuste à la forme exacte de la réponse Mistral : tout dict portant à la fois un
    champ texte (``text``/``word``/``token``) ET un score (``confidence``/``score``)
    numérique est récolté. JAMAIS de score inventé ; les bool sont ignorés."""
    if isinstance(node, dict):
        text_value = node.get("text") or node.get("word") or node.get("token")
        score = node.get("confidence")
        if score is None:
            score = node.get("score")
        if isinstance(text_value, str) and isinstance(score, (int, float)) and not isinstance(score, bool):
            cleaned = text_value.strip()
            if cleaned:
                out.append({"text": cleaned, "confidence": float(score)})
        for value in node.values():
            _collect_word_confidences(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_word_confidences(value, out)


def _parse_mistral_response(data: dict[str, Any]) -> OcrProviderResult:
    pages = data.get("pages") or []
    texts: list[str] = []
    page_confidences: list[float] = []
    word_confidences: list[dict] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        markdown = page.get("markdown")
        if isinstance(markdown, str):
            texts.append(markdown)
        page_score = page.get("page_confidence")
        if isinstance(page_score, (int, float)) and not isinstance(page_score, bool):
            page_confidences.append(float(page_score))
        _collect_word_confidences(page, word_confidences)

    text_content = "\n".join(texts).strip()
    if not text_content:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Mistral OCR response is empty")

    page_confidence = sum(page_confidences) / len(page_confidences) if page_confidences else None
    return OcrProviderResult(
        text=text_content,
        provider="mistral",
        model=settings.mistral_ocr_model,
        raw_response=data,
        page_confidence=page_confidence,
        word_confidences=word_confidences or None,
    )


def _extract_text_with_azure(storage_path: str, content_type: str | None) -> str:
    path = Path(storage_path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found")

    headers = {
        "Ocp-Apim-Subscription-Key": settings.azure_document_intelligence_key,
        "Content-Type": content_type or "application/octet-stream",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            analyze_response = client.post(_azure_analyze_url(), headers=headers, content=path.read_bytes())
            analyze_response.raise_for_status()
            operation_location = analyze_response.headers.get("operation-location")
            if not operation_location:
                return _extract_content(analyze_response.json())

            result = _poll_azure_result(client, operation_location, headers)
            return _extract_content(result)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Azure OCR request failed",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Azure OCR service unavailable",
        ) from exc


def _poll_azure_result(client: httpx.Client, operation_location: str, headers: dict[str, str]) -> dict[str, Any]:
    poll_headers = {"Ocp-Apim-Subscription-Key": headers["Ocp-Apim-Subscription-Key"]}
    for _ in range(10):
        time.sleep(0.5)
        response = client.get(operation_location, headers=poll_headers)
        response.raise_for_status()
        payload = response.json()
        azure_status = payload.get("status")
        if azure_status == "succeeded":
            return payload
        if azure_status == "failed":
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Azure OCR analysis failed")

    raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Azure OCR analysis timed out")


def _extract_content(payload: dict[str, Any]) -> str:
    analyze_result = payload.get("analyzeResult", payload)
    content = analyze_result.get("content")
    if isinstance(content, str):
        return content

    pages = analyze_result.get("pages") or []
    lines: list[str] = []
    for page in pages:
        for line in page.get("lines", []):
            text = line.get("content")
            if isinstance(text, str):
                lines.append(text)
    return "\n".join(lines)
