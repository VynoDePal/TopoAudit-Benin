import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

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


class OcrResult(BaseModel):
    provider: str = Field(examples=["mock"])
    text: str
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


def extract_text_from_document(storage_path: str, content_type: str | None) -> tuple[str, str]:
    if not _azure_is_configured():
        return MOCK_OCR_TEXT, "mock"

    return _extract_text_with_azure(storage_path, content_type), "azure"


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
