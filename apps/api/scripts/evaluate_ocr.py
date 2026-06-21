"""Evaluate OCR extraction accuracy against a local, network-free dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.uploads import ExtractedParcel, extract_parcels_from_ocr_text


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET_PATH = REPOSITORY_ROOT / "apps" / "api" / "datasets" / "ocr" / "manifest.json"
COORDINATE_TOLERANCE = 0.01


class OcrDatasetError(ValueError):
    """Raised when the OCR evaluation dataset is malformed."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OcrDatasetError(f"Dataset not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OcrDatasetError(f"Dataset is not valid JSON: {exc.msg}") from exc


def _require_mapping(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OcrDatasetError(f"{location} must be an object")
    return value


def _require_string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OcrDatasetError(f"{location} must be a non-empty string")
    return value


def _require_number(value: Any, location: str) -> float:
    if not isinstance(value, int | float):
        raise OcrDatasetError(f"{location} must be a number")
    return float(value)


def _validate_expected_point(value: Any, location: str) -> None:
    point = _require_mapping(value, location)
    _require_string(point.get("label"), f"{location}.label")
    _require_number(point.get("x"), f"{location}.x")
    _require_number(point.get("y"), f"{location}.y")


def _validate_expected_parcel(value: Any, location: str) -> None:
    parcel = _require_mapping(value, location)
    _require_string(parcel.get("label"), f"{location}.label")
    surface = parcel.get("declared_surface_m2")
    if surface is not None and not isinstance(surface, int):
        raise OcrDatasetError(f"{location}.declared_surface_m2 must be an integer or null")
    points = parcel.get("points")
    if not isinstance(points, list) or len(points) < 3:
        raise OcrDatasetError(f"{location}.points must contain at least three points")
    for point_index, point in enumerate(points):
        _validate_expected_point(point, f"{location}.points[{point_index}]")


def validate_dataset(dataset: dict[str, Any]) -> None:
    if dataset.get("version") != 1:
        raise OcrDatasetError("Dataset version must be 1")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise OcrDatasetError("Dataset cases must be a non-empty list")

    seen_ids: set[str] = set()
    for case_index, raw_case in enumerate(cases):
        case = _require_mapping(raw_case, f"cases[{case_index}]")
        case_id = _require_string(case.get("id"), f"cases[{case_index}].id")
        if case_id in seen_ids:
            raise OcrDatasetError(f"Duplicate case id: {case_id}")
        seen_ids.add(case_id)
        _require_string(case.get("ocr_text"), f"cases[{case_index}].ocr_text")
        expected_parcels = case.get("expected_parcels")
        if not isinstance(expected_parcels, list) or not expected_parcels:
            raise OcrDatasetError(f"cases[{case_index}].expected_parcels must be a non-empty list")
        for parcel_index, parcel in enumerate(expected_parcels):
            _validate_expected_parcel(parcel, f"cases[{case_index}].expected_parcels[{parcel_index}]")


def _score_value(expected: Any, actual: Any) -> bool:
    if isinstance(expected, float):
        return isinstance(actual, int | float) and abs(float(actual) - expected) <= COORDINATE_TOLERANCE
    return expected == actual


def _score_case(case: dict[str, Any]) -> dict[str, Any]:
    actual_parcels = extract_parcels_from_ocr_text(case["ocr_text"])
    expected_parcels = case["expected_parcels"]
    matched = 0
    total = 0

    def add_match(expected: Any, actual: Any) -> None:
        nonlocal matched, total
        total += 1
        if _score_value(expected, actual):
            matched += 1

    add_match(len(expected_parcels), len(actual_parcels))
    for parcel_index, expected_parcel in enumerate(expected_parcels):
        actual_parcel: ExtractedParcel | None = None
        if parcel_index < len(actual_parcels):
            actual_parcel = actual_parcels[parcel_index]

        add_match(expected_parcel["label"], actual_parcel.label if actual_parcel else None)
        add_match(expected_parcel.get("declared_surface_m2"), actual_parcel.declared_surface_m2 if actual_parcel else None)

        expected_points = expected_parcel["points"]
        actual_points = actual_parcel.points if actual_parcel else []
        add_match(len(expected_points), len(actual_points))
        for point_index, expected_point in enumerate(expected_points):
            actual_point = actual_points[point_index] if point_index < len(actual_points) else None
            add_match(expected_point["label"], actual_point.label if actual_point else None)
            add_match(float(expected_point["x"]), actual_point.x if actual_point else None)
            add_match(float(expected_point["y"]), actual_point.y if actual_point else None)

    accuracy = matched / total if total else 0.0
    return {
        "id": case["id"],
        "accuracy": round(accuracy, 4),
        "matched_fields": matched,
        "total_fields": total,
        "parsed_parcels": len(actual_parcels),
    }


def evaluate_dataset(dataset_path: Path = DEFAULT_DATASET_PATH) -> dict[str, Any]:
    dataset = _load_json(dataset_path)
    validate_dataset(dataset)
    case_results = [_score_case(case) for case in dataset["cases"]]
    matched = sum(result["matched_fields"] for result in case_results)
    total = sum(result["total_fields"] for result in case_results)
    accuracy = matched / total if total else 0.0
    return {
        "dataset": str(dataset_path),
        "case_count": len(case_results),
        "accuracy": round(accuracy, 4),
        "matched_fields": matched,
        "total_fields": total,
        "cases": case_results,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate OCR extraction accuracy without network calls.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH, help="Path to the OCR dataset manifest")
    parser.add_argument("--min-accuracy", type=float, default=0.0, help="Fail if accuracy is below this threshold")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = evaluate_dataset(args.dataset)
    except OcrDatasetError as exc:
        print(f"OCR dataset error: {exc}", file=sys.stderr)
        return 2

    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent, sort_keys=True))
    return 1 if result["accuracy"] < args.min_accuracy else 0


if __name__ == "__main__":
    raise SystemExit(main())
