"""Tests for automatic timing and single-pass delivery audit records."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from delivery_record import STAGES, validate_record


def complete_record(evidence: Path) -> dict:
    return {
        "recordVersion": 1,
        "testMode": "delivery",
        "executionProfile": "cold-start",
        "startedAt": "2026-09-20T01:00:00+00:00",
        "generationFinishedAt": "2026-09-20T01:01:00+00:00",
        "firstPreviewAt": "2026-09-20T01:04:30+00:00",
        "htmlReadyAt": "2026-09-20T01:05:00+00:00",
        "handoffReadyAt": "2026-09-20T01:06:00+00:00",
        "technicalStatus": {"status": "passed", "note": "All final commands passed."},
        "visualReview": {"status": "pending", "note": ""},
        "pipelineAttempts": [
            {
                "stage": stage,
                "status": "passed",
                "at": "2026-09-20T01:05:00+00:00",
                "evidencePath": str(evidence),
                "reason": "",
            }
            for stage in sorted(STAGES)
        ],
    }


class DeliveryRecordTests(unittest.TestCase):
    def test_technical_pass_does_not_auto_pass_visual_review(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence.json"
            evidence.write_text("{}", encoding="utf-8")
            result = validate_record(complete_record(evidence))
            self.assertTrue(result["ok"])
            self.assertTrue(any("visual review is still pending" in item for item in result["warnings"]))

    def test_root_visual_status_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence.json"
            evidence.write_text("{}", encoding="utf-8")
            record = complete_record(evidence)
            record["visualStatus"] = "passed"
            result = validate_record(record)
            self.assertFalse(result["ok"])
            self.assertIn("visualStatus is forbidden", "\n".join(result["errors"]))

    def test_generation_to_first_preview_must_stay_within_four_minutes(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence.json"
            evidence.write_text("{}", encoding="utf-8")
            record = complete_record(evidence)
            record["firstPreviewAt"] = "2026-09-20T01:05:01+00:00"
            result = validate_record(record)
            self.assertFalse(result["ok"])
            self.assertIn("gate exceeded", "\n".join(result["errors"]))

    def test_final_pipeline_allows_failed_retry_with_reason_but_one_pass_only(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence.json"
            evidence.write_text("{}", encoding="utf-8")
            record = complete_record(evidence)
            record["pipelineAttempts"].insert(
                0,
                {
                    "stage": "html-preflight",
                    "status": "failed",
                    "at": "2026-09-20T01:02:00+00:00",
                    "evidencePath": None,
                    "reason": "Missing required manifest field.",
                },
            )
            self.assertTrue(validate_record(record)["ok"])
            record["pipelineAttempts"].append(
                {
                    "stage": "html-preflight",
                    "status": "passed",
                    "at": "2026-09-20T01:05:30+00:00",
                    "evidencePath": str(evidence),
                    "reason": "",
                }
            )
            result = validate_record(record)
            self.assertFalse(result["ok"])
            self.assertIn("found 2", "\n".join(result["errors"]))


if __name__ == "__main__":
    unittest.main()
