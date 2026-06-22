"""Tests offline du benchmark parser OCR (P0 hardening V2, P0.4)."""

from scripts import evaluate_parser


def test_evaluate_parser_offline_meets_thresholds():
    result = evaluate_parser.evaluate_dataset()
    assert result["case_count"] == 3
    assert result["point_recall"] == 1.0
    assert result["parcel_count_accuracy"] == 1.0
    assert result["crs_detection_accuracy"] == 1.0
    assert result["surface_accuracy"] is not None and result["surface_accuracy"] > 0.99
    assert result["coordinate_mae"] is not None and result["coordinate_mae"] < 0.01


def test_evaluate_parser_detects_local_only_case():
    result = evaluate_parser.evaluate_dataset()
    local_case = next(c for c in result["cases"] if c["case_id"] == "synthetic_old_local_plan")
    assert local_case["detected_crs"] == "LOCAL_ONLY"
    assert local_case["crs_detection_accuracy"] == 1.0


def test_evaluate_parser_main_passes_thresholds():
    assert evaluate_parser.main(["--min-point-recall", "0.9", "--min-crs-accuracy", "1.0"]) == 0


def test_evaluate_parser_main_fails_impossible_threshold():
    assert evaluate_parser.main(["--min-point-recall", "1.01"]) == 1
