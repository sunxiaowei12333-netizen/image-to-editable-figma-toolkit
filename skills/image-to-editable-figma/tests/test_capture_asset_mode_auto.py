import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
BUILDER = SKILL_ROOT / "scripts" / "build_offline_capture.mjs"


class CaptureAssetModeAutoTests(unittest.TestCase):
    def run_builder(self, directory: Path, asset_size: int, asset_mode: str = "auto"):
        asset = directory / "asset.png"
        with asset.open("wb") as handle:
            handle.truncate(asset_size)
        source = directory / "source.html"
        source.write_text(
            """<!doctype html><html><head><title>Fixture</title></head>"
            "<body><main id=\"canvas\"><img src=\"asset.png\"></main></body></html>""",
            encoding="utf-8",
        )
        output = directory / "capture.html"
        completed = subprocess.run(
            [
                "node",
                str(BUILDER),
                str(source),
                "--width",
                "320",
                "--height",
                "200",
                "--output",
                str(output),
                "--asset-mode",
                asset_mode,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout), output.read_text(encoding="utf-8")

    def test_auto_uses_inline_for_small_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, html = self.run_builder(Path(tmp), 1024)
        self.assertEqual(result["requestedAssetMode"], "auto")
        self.assertEqual(result["assetMode"], "inline")
        self.assertFalse(result["inlinePayloadRisk"])
        self.assertIn("data:image/png;base64,", html)

    def test_auto_skips_inline_output_for_large_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, html = self.run_builder(Path(tmp), 16 * 1024 * 1024)
        self.assertEqual(result["assetMode"], "external")
        self.assertTrue(result["inlinePayloadRisk"])
        self.assertEqual(result["recommendedAssetMode"], "external")
        self.assertIn('data-capture-asset-mode="external"', html)
        self.assertIn('src="asset.png"', html)
        self.assertNotIn("data:image/png;base64,", html)

    def test_explicit_external_remains_recommended(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, html = self.run_builder(Path(tmp), 1024, asset_mode="external")
        self.assertEqual(result["requestedAssetMode"], "external")
        self.assertEqual(result["assetMode"], "external")
        self.assertEqual(result["recommendedAssetMode"], "external")
        self.assertIn('src="asset.png"', html)


if __name__ == "__main__":
    unittest.main()
