import json

import httpx

from scripts import evaluate_ocr


def test_evaluate_default_ocr_dataset_returns_perfect_accuracy():
    result = evaluate_ocr.evaluate_dataset()

    assert result["case_count"] == 2
    assert result["accuracy"] == 1.0
    assert result["matched_fields"] == result["total_fields"]
    assert {case["id"] for case in result["cases"]} == {"mock_utm_single_parcel", "gemini_style_multi_parcel"}


def test_evaluate_ocr_does_not_call_network(monkeypatch):
    def fail_network_call(*_args, **_kwargs):
        raise AssertionError("evaluate_ocr.py must not perform network calls")

    monkeypatch.setattr(httpx, "Client", fail_network_call)

    assert evaluate_ocr.evaluate_dataset()["accuracy"] == 1.0


def test_evaluate_dataset_rejects_malformed_dataset(tmp_path):
    dataset_path = tmp_path / "manifest.json"
    dataset_path.write_text(json.dumps({"version": 1, "cases": []}), encoding="utf-8")

    try:
        evaluate_ocr.evaluate_dataset(dataset_path)
    except evaluate_ocr.OcrDatasetError as exc:
        assert str(exc) == "Dataset cases must be a non-empty list"
    else:
        raise AssertionError("Malformed OCR dataset should fail validation")


def test_evaluate_ocr_main_reports_accuracy_json(capsys):
    exit_code = evaluate_ocr.main(["--min-accuracy", "1.0"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out)["accuracy"] == 1.0
    assert captured.err == ""


def test_evaluate_ocr_main_fails_below_minimum_accuracy(capsys):
    exit_code = evaluate_ocr.main(["--min-accuracy", "1.01"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert json.loads(captured.out)["accuracy"] == 1.0
    assert captured.err == ""
