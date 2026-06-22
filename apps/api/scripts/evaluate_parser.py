"""Évalue le parser OCR + la détection CRS contre une vérité terrain, SANS réseau.

Offline (CI-friendly) : travaille sur les champs ``ocr_text`` du manifest, applique
extract_parcels_from_ocr_text + detect_crs, et compare aux valeurs attendues.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.ocr_benchmark import aggregate, evaluate_parser_case

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = REPOSITORY_ROOT / "datasets" / "ocr_real" / "manifest.json"


def evaluate_dataset(path: Path | str = DEFAULT_DATASET) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    metrics = [evaluate_parser_case(case) for case in data.get("cases", [])]
    return aggregate(metrics)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Évaluation offline du parser OCR (sans réseau).")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--min-point-recall", type=float, default=0.0)
    parser.add_argument("--min-surface-accuracy", type=float, default=0.0)
    parser.add_argument("--min-parcel-count-accuracy", type=float, default=0.0)
    parser.add_argument("--min-crs-accuracy", type=float, default=0.0)
    args = parser.parse_args(argv)

    result = evaluate_dataset(Path(args.dataset))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))

    thresholds = [
        ("point_recall", args.min_point_recall),
        ("surface_accuracy", args.min_surface_accuracy),
        ("parcel_count_accuracy", args.min_parcel_count_accuracy),
        ("crs_detection_accuracy", args.min_crs_accuracy),
    ]
    for key, minimum in thresholds:
        value = result.get(key)
        if minimum > 0 and (value is None or value < minimum):
            print(f"FAIL: {key}={value} < seuil {minimum}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
