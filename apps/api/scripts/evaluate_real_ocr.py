"""Évalue l'OCR RÉEL (Gemini/Azure) sur des images locales, puis le parser.

OPTIONNEL — nécessite ``OCR_PROVIDER`` + la clé correspondante et des images dans
``datasets/ocr_real/images/`` (gitignorées). N'est JAMAIS exécuté en CI par défaut :
sort proprement (code 0) si aucun provider réel n'est configuré ou si aucune image
n'est disponible.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from app.config import settings
from app.ocr import extract_ocr_from_document
from app.ocr_benchmark import aggregate, evaluate_parser_case

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = REPOSITORY_ROOT / "datasets" / "ocr_real" / "manifest.json"

_CONTENT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".pdf": "application/pdf"}


def _has_real_provider(provider: str) -> bool:
    provider = provider.strip().lower()
    if provider == "gemini":
        return bool(settings.gemini_api_key)
    if provider == "mistral":
        return bool(settings.mistral_api_key)
    if provider == "azure":
        return bool(settings.azure_document_intelligence_endpoint and settings.azure_document_intelligence_key)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Évaluation OCR réelle (Gemini/Mistral/Azure) — hors CI.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--delay", type=float, default=0.0, help="pause (s) entre scans pour éviter le rate-limiting")
    parser.add_argument(
        "--provider",
        default=None,
        choices=["gemini", "mistral", "azure"],
        help="provider OCR à évaluer (défaut : OCR_PROVIDER). Comparer gemini vs mistral.",
    )
    args = parser.parse_args(argv)

    provider_name = (args.provider or settings.ocr_provider).strip().lower()
    if not _has_real_provider(provider_name):
        print(
            f"SKIP : provider OCR réel '{provider_name}' non configuré (clé manquante). "
            "Script optionnel, non exécuté en CI.",
            file=sys.stderr,
        )
        return 0

    dataset_path = Path(args.dataset)
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    dataset_dir = dataset_path.parent

    metrics = []
    errors: list[dict] = []
    durations: list[float] = []
    for case in data.get("cases", []):
        image = dataset_dir / str(case.get("file_path", ""))
        if not image.exists():
            errors.append({"id": case.get("id"), "error": "image absente"})
            continue
        content_type = _CONTENT_TYPES.get(image.suffix.lower(), "image/png")
        started = time.monotonic()
        try:
            result_ocr = extract_ocr_from_document(str(image), content_type, provider_name)
        except Exception as exc:  # noqa: BLE001 — erreur OCR transitoire (quota/5xx) : on continue
            errors.append({"id": case.get("id"), "error": str(exc)[:140]})
            if args.delay:
                time.sleep(args.delay)
            continue
        durations.append(time.monotonic() - started)
        if result_ocr.provider == "mock":
            errors.append({"id": case.get("id"), "error": "provider retombé sur le mock"})
            continue
        metrics.append(evaluate_parser_case({**case, "ocr_text": result_ocr.text}))
        if args.delay:
            time.sleep(args.delay)

    attempted = len(metrics) + len(errors)
    result = aggregate(metrics)
    result["provider"] = provider_name
    result["errors"] = errors
    # Taux d'échec API + temps moyen par scan (métriques de comparaison entre providers).
    result["api_failure_rate"] = round(len(errors) / attempted, 4) if attempted else 0.0
    result["avg_seconds_per_scan"] = round(sum(durations) / len(durations), 2) if durations else None
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
