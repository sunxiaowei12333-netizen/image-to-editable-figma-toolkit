"""Regressions for observed icon failures and unbound visual acceptance."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.preflight_html import CaptureHTMLParser
from scripts.delivery_record import validate_record
from test_delivery_record import complete_record

ROOT = Path(__file__).resolve().parents[1]


class DeliveryFixTests(unittest.TestCase):
    def fixture(self, directory):
        icons = directory / "node_modules/@hugeicons/core-free-icons/dist/esm"
        icons.mkdir(parents=True)
        (icons / "package.json").write_text('{"type":"module"}')
        (icons / "Idea01Icon.js").write_text('export default [["circle", {cx:12, cy:12, r:4}]];')
        return icons

    def test_existing_package_with_wrong_export_fails_before_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.fixture(directory)
            result = subprocess.run([
                "node", str(ROOT / "scripts/bootstrap.mjs"), "--ensure-hugeicons",
                "--source-dir", tmp, "--icons", "Bulb",
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("package exists", result.stderr)
            self.assertIn("exports are missing: Bulb", result.stderr)
            self.assertNotIn("running one-time", result.stderr)

    def test_valid_export_builds_auto_and_keeps_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.fixture(directory)
            source = directory / "source.html"
            source.write_text('<html><head></head><body><main id="canvas"><span data-icon-library="Hugeicons" data-icon-name="Idea01Icon"></span></main></body></html>')
            result = subprocess.run([
                "node", str(ROOT / "scripts/build_offline_capture.mjs"), str(source),
                "--width", "320", "--height", "200", "--asset-mode", "auto",
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["hugeicons"], ["Idea01Icon"])
            html = (directory / "source-capture.html").read_text()
            self.assertEqual(html.count("<circle "), 1)
            self.assertIn('data-icon-library="Hugeicons"', html)

    def test_aliases_cannot_hide_an_unverified_icon(self):
        parser = CaptureHTMLParser()
        parser.feed('<svg class="f-glyph" data-library-origin="Hugeicons" data-icon-key="Bulb"></svg>')
        self.assertTrue(parser.icon_errors)
        self.assertIn("aliases cannot bypass", parser.icon_errors[0])

    def test_v2_visual_pass_requires_reference_and_unchanged_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "final.png"
            evidence.write_bytes(b"final fixture")
            reference = Path(tmp) / "reference.png"
            reference.write_bytes(b"reference fixture")
            record = complete_record(evidence)
            record["recordVersion"] = 2
            record["visualReview"] = {"status": "passed", "note": "Comparison performed", "evidencePath": str(evidence)}
            self.assertFalse(validate_record(record)["ok"])
            record["visualReview"].update({
                "referencePath": str(reference),
                "referenceSha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
                "evidenceSha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            })
            self.assertTrue(validate_record(record)["ok"])
            evidence.write_bytes(b"changed after review")
            self.assertFalse(validate_record(record)["ok"])

    def test_review_cli_refuses_unbound_pass_and_preserves_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "timing.json"
            evidence = Path(tmp) / "final.png"
            evidence.write_bytes(b"fixture")
            command = ["python3", str(ROOT / "scripts/delivery_record.py")]
            subprocess.run(command + ["init", str(record)], check=True, capture_output=True)
            result = subprocess.run(command + ["review", str(record), "--status", "passed", "--evidence", str(evidence), "--note", "passed"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(json.loads(record.read_text())["visualReview"]["status"], "pending")
            result = subprocess.run(command + ["review", str(record), "--status", "failed", "--reference", str(evidence), "--evidence", str(evidence), "--note", "Material mismatch"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(json.loads(record.read_text())["visualReview"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
