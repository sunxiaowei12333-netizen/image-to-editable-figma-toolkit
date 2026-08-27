#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from PIL import Image, ImageDraw


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "extract_colorkey_alpha.py"


class ExtractColorKeyAlphaTests(unittest.TestCase):
    def run_extract(
        self,
        input_path: Path,
        output_path: Path,
        key: str,
        *extra_args: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(SCRIPT),
                str(input_path),
                str(output_path),
                "--key",
                key,
                *extra_args,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def make_subject(self, background: tuple[int, int, int]) -> Image.Image:
        image = Image.new("RGB", (96, 96), background)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((22, 18, 74, 82), radius=16, fill=(248, 248, 255))
        draw.ellipse((34, 30, 62, 58), fill=(58, 225, 242))
        draw.rectangle((40, 62, 56, 74), fill=(61, 35, 145))
        return image

    def test_exact_planned_blue_uses_defaults_and_writes_candidate_previews(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_subject((0, 107, 255))
            draw = ImageDraw.Draw(source)
            draw.rectangle((45, 65, 51, 70), fill=(0, 107, 255))
            input_path = root / "blue-input.png"
            output_path = root / "blue-output.png"
            qa_dir = root / "qa"
            source.save(input_path)

            result = self.run_extract(
                input_path,
                output_path,
                "#006BFF",
                "--generated-key-input",
                "--qa-dir",
                str(qa_dir),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output_path.with_suffix(".report.json").read_text())
            self.assertEqual(report["planned_key"], "#006BFF")
            self.assertEqual(report["key"], "#006BFF")
            self.assertEqual(
                report["key_source_audit"]["selection_mode"],
                "adaptive-planned-key-family-v3",
            )
            self.assertEqual(report["parameters"]["seed_tolerance"], 18.0)
            self.assertEqual(report["parameters"]["grow_tolerance"], 72.0)
            self.assertGreater(report["segmentation"]["enclosed_key_candidate_count"], 0)
            self.assertTrue((qa_dir / "enclosed-candidates-marked.png").exists())
            self.assertTrue((qa_dir / "enclosed-candidates-contact-sheet.png").exists())

    def test_uniform_generated_red_drift_uses_adaptive_planned_family(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "red-input.png"
            output_path = root / "red-output.png"
            self.make_subject((246, 16, 15)).save(input_path)

            result = self.run_extract(
                input_path,
                output_path,
                "#FF2D2D",
                "--generated-key-input",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output_path.with_suffix(".report.json").read_text())
            self.assertEqual(report["planned_key"], "#FF2D2D")
            self.assertEqual(report["key"], "#FF2D2D")
            self.assertEqual(
                report["key_source_audit"]["selection_mode"],
                "adaptive-planned-key-family-v3",
            )
            self.assertEqual(report["parameters"]["seed_tolerance"], 18.0)
            self.assertEqual(report["parameters"]["grow_tolerance"], 72.0)

    def test_same_family_generated_gradient_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "gradient-input.png"
            output_path = root / "gradient-output.png"
            image = Image.new("RGB", (96, 96))
            pixels = image.load()
            assert pixels is not None
            for y in range(image.height):
                for x in range(image.width):
                    red = 190 + round(56 * x / (image.width - 1))
                    pixels[x, y] = (red, 8, 10)
            draw = ImageDraw.Draw(image)
            draw.ellipse((28, 24, 68, 78), fill=(248, 248, 255))
            image.save(input_path)

            result = self.run_extract(
                input_path,
                output_path,
                "#FF2D2D",
                "--generated-key-input",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output_path.exists())
            report = json.loads(output_path.with_suffix(".report.json").read_text())
            self.assertEqual(
                report["key_source_audit"]["selection_mode"],
                "adaptive-planned-key-family-v3",
            )

    def test_incompatible_multicolor_generated_border_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "multicolor-input.png"
            output_path = root / "multicolor-output.png"
            image = self.make_subject((255, 0, 255))
            draw = ImageDraw.Draw(image)
            draw.line((0, 0, 95, 0), fill=(0, 180, 255), width=1)
            image.save(input_path)

            result = self.run_extract(
                input_path,
                output_path,
                "#FF00FF",
                "--generated-key-input",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output_path.exists())
            report = json.loads(output_path.with_suffix(".report.json").read_text())
            self.assertEqual(report["status"], "rejected")
            self.assertEqual(report["reason"], "key-background-impure")

    def test_generated_key_residue_touching_boundary_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "residue-input.png"
            output_path = root / "residue-output.png"
            image = self.make_subject((0, 107, 255))
            image.putpixel((0, 48), (118, 118, 118))
            image.save(input_path)

            result = self.run_extract(
                input_path,
                output_path,
                "#006BFF",
                "--generated-key-input",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output_path.exists())
            report = json.loads(output_path.with_suffix(".report.json").read_text())
            self.assertEqual(report["status"], "rejected")
            self.assertEqual(report["reason"], "unapproved-subject-edge-contact")
            self.assertIn(
                "left",
                report["key_source_audit"]["unapproved_subject_touch_edges"],
            )

    def test_declared_subject_crop_edge_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "crop-input.png"
            output_path = root / "crop-output.png"
            image = self.make_subject((255, 0, 255))
            ImageDraw.Draw(image).rectangle((40, 76, 56, 95), fill=(61, 35, 145))
            image.save(input_path)

            result = self.run_extract(
                input_path,
                output_path,
                "#FF00FF",
                "--generated-key-input",
                "--allow-subject-touch-edge",
                "bottom",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output_path.with_suffix(".report.json").read_text())
            self.assertEqual(report["output_alpha"]["allowed_subject_touch_edges"], ["bottom"])
            self.assertTrue(report["output_alpha"]["visible_touches_boundary"])

    def test_generated_key_flag_rejects_custom_tolerance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.png"
            output_path = root / "output.png"
            self.make_subject((0, 107, 255)).save(input_path)

            result = self.run_extract(
                input_path,
                output_path,
                "#006BFF",
                "--generated-key-input",
                "--seed-tolerance",
                "24",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires the default seed/grow tolerances", result.stderr)
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
