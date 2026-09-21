"""Regressions for contradictory prompts and mixed route/quality/geometry decisions."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generation_contract import build_asset, geometry_result, assess, compare_plans, validate_contract
from preflight_resource_plan import generation_contract_required_for_mode, run


def asset():
    return {"id": "frame", "expectedFigmaType": "IMAGE", "sourceMethod": "reference-guided-edit",
            "generationReason": "Irregular metal border is occluded; no clean source exists",
            "targetVisibleBounds": {"x": 173, "y": 461, "width": 681, "height": 127},
            "alphaRequired": True, "keyPlan": {"hex": "#FF00FF", "conflictCheck": "Not in the metal or its highlights"},
            "geometryPolicy": {"lockAxis": "width", "maxSizeDeltaPx": 4, "reason": "Reference layout tolerance"},
            "generationSpec": {"description": "The ornate metal frame only", "invariants": ["Continuous thin metal rails"],
                               "exclusions": ["UI text"], "canvasSize": [2048, 512]}}


def add_measurement(a, evidence_path):
    target = copy.deepcopy(a["targetVisibleBounds"])
    a["measurementEvidence"] = {
        "method": "two-pass-reference-crop",
        "evidencePath": str(evidence_path),
        "firstBounds": target,
        "secondBounds": copy.deepcopy(target),
    }
    return a


class GenerationContractTests(unittest.TestCase):
    def test_delivery_does_not_require_experiment_contract(self):
        self.assertFalse(generation_contract_required_for_mode("delivery"))
        self.assertTrue(generation_contract_required_for_mode("rule-regression"))
        self.assertTrue(generation_contract_required_for_mode("fresh-generation-stability"))
        with self.assertRaisesRegex(ValueError, "Unsupported test mode"):
            generation_contract_required_for_mode("unknown")

    def test_wide_frame_fits_without_conflicting_percentages(self):
        p = build_asset(asset())
        b = p["requestedSubjectBounds"]
        self.assertAlmostEqual(b["width"]/b["height"], 681/127)
        self.assertGreaterEqual(b["x"], 32)
        self.assertGreaterEqual(b["y"], 32)
        self.assertIn("Do NOT output transparency", p["prompt"])
        self.assertIn("Never fade clothing", p["prompt"])
        self.assertNotIn("%", p["prompt"])

    def test_actual_hint_prompt_contradiction_is_rejected(self):
        a = asset()
        a["generationSpec"]["description"] = "Plaque occupies 17% image height, about 1940 by 172 pixels"
        with self.assertRaisesRegex(ValueError, "structured geometry"):
            build_asset(a)

    def test_duplicate_subject_dimension_field_is_rejected(self):
        a = asset(); a["generationSpec"]["subjectHeight"] = 172
        with self.assertRaises(ValueError): build_asset(a)

    def test_low_resolution_is_rejected(self):
        a = asset(); a["generationSpec"]["canvasSize"] = [1000, 512]
        with self.assertRaisesRegex(ValueError, "< 1.5"): build_asset(a)

    def test_no_key_conflict_evidence_is_rejected(self):
        a = asset(); a["keyPlan"]["conflictCheck"] = ""
        with self.assertRaises(ValueError): build_asset(a)

    def test_transparent_foreground_tolerance_cannot_be_tightened_below_four(self):
        a = asset(); a["geometryPolicy"]["maxSizeDeltaPx"] = 2
        with self.assertRaisesRegex(ValueError, "cannot be below 4"):
            build_asset(a)

    def test_opaque_full_bleed_may_require_exact_geometry(self):
        a = asset(); a["alphaRequired"] = False
        a["targetVisibleBounds"].update(width=1024, height=640)
        a["geometryPolicy"]["maxSizeDeltaPx"] = 0
        a["generationSpec"].pop("canvasSize")
        self.assertEqual(build_asset(a)["geometryPolicy"]["maxSizeDeltaPx"], 0)

    def test_white_key_is_rejected(self):
        a = asset(); a["keyPlan"]["hex"] = "#FFFFFF"
        with self.assertRaises(ValueError): build_asset(a)

    def test_bottom_crop_retains_requested_aspect(self):
        a = asset(); a["targetVisibleBounds"].update(width=164, height=202)
        a["generationSpec"].update(canvasSize=[1024, 1280], subjectTouchEdges=["bottom"])
        p = build_asset(a); b = p["requestedSubjectBounds"]
        self.assertAlmostEqual(b["y"]+b["height"], 1280)
        self.assertAlmostEqual(b["width"]/b["height"], 164/202)

    def test_impossible_opposite_touch_edges_are_rejected(self):
        a = asset(); a["generationSpec"]["subjectTouchEdges"] = ["top", "bottom"]
        with self.assertRaises(ValueError): build_asset(a)

    def test_opaque_scene_has_no_key_and_preserves_aspect(self):
        a = asset(); a["alphaRequired"] = False; a["targetVisibleBounds"].update(width=1024, height=640)
        a["generationSpec"].pop("canvasSize")
        p = build_asset(a)
        self.assertEqual(p["requestedCanvas"], [2048, 1280])
        self.assertNotIn("#FF00FF", p["prompt"])

    def test_invalid_numerics(self):
        for value in [0, -1, True, float("nan"), float("inf")]:
            with self.subTest(value=value):
                a = asset(); a["targetVisibleBounds"]["width"] = value
                with self.assertRaises(ValueError): build_asset(a)

    def test_coordinates_must_be_finite_but_may_be_negative(self):
        for value in ["NOT_A_NUMBER", None, True, float("nan")]:
            a = asset(); a["targetVisibleBounds"]["x"] = value
            with self.assertRaises(ValueError): build_asset(a)
        a = asset(); a["targetVisibleBounds"]["x"] = -10
        self.assertEqual(build_asset(a)["referenceBounds"]["x"], -10)

    def test_historical_version_is_optional_but_new_round_requires_v2(self):
        for required, expected_errors in [(False, False), (True, True)]:
            errors = []; validate_contract({"assets": [asset()]}, errors, required)
            self.assertEqual(bool(errors), expected_errors)
        errors = []
        validate_contract({"labGenerationContractVersion": 1, "assets": [asset()]}, errors, required=True)
        self.assertRegex(errors[0], "require labGenerationContractVersion 2")

    def test_contract_v2_requires_two_pass_measurement_evidence(self):
        errors = []
        validate_contract({"labGenerationContractVersion": 2, "assets": [asset()]}, errors, required=True)
        self.assertRegex(errors[0], "measurementEvidence required")

    def test_measurement_disagreement_blocks_before_generation(self):
        with tempfile.TemporaryDirectory() as d:
            evidence = Path(d)/"reference-crop.png"
            Image.new("RGB", (10, 10), "orange").save(evidence)
            a = add_measurement(asset(), evidence)
            a["measurementEvidence"]["secondBounds"]["width"] += 1
            with self.assertRaisesRegex(ValueError, "passes disagree"):
                build_asset(a, require_measurement=True)

    def test_verified_measurement_is_hashed_into_plan(self):
        with tempfile.TemporaryDirectory() as d:
            evidence = Path(d)/"reference-crop.png"
            Image.new("RGB", (10, 10), "orange").save(evidence)
            p = build_asset(add_measurement(asset(), evidence), require_measurement=True)
            self.assertEqual(p["measurementEvidence"]["status"], "verified")
            self.assertEqual(len(p["measurementEvidence"]["evidenceSha256"]), 64)
            self.assertEqual(len(p["measurementEvidence"]["evidencePixelSha256"]), 64)

    def test_malformed_asset_collection_fails_closed(self):
        errors = []; validate_contract({"labGenerationContractVersion": 1, "assets": None}, errors)
        self.assertTrue(errors)

    def test_old_tablet_pass_and_other_fails_use_same_geometry_rule(self):
        a = asset(); a["targetVisibleBounds"].update(width=778, height=595)
        a["generationSpec"]["canvasSize"] = [2048, 1600]
        r = geometry_result(build_asset(a), [1369, 1039])
        self.assertAlmostEqual(r["sizeDeltaPx"], -4.53834915997)
        self.assertEqual(r["geometryStatus"], "outside-plan")
        r = geometry_result(build_asset(asset()), [2036, 409])
        self.assertAlmostEqual(r["sizeDeltaPx"], 9.80206286837)
        self.assertEqual(r["geometryStatus"], "outside-plan")

    def test_exact_tolerance_boundary(self):
        a = asset(); a["targetVisibleBounds"].update(width=100, height=100)
        p = build_asset(a)
        self.assertEqual(geometry_result(p, [200, 208])["geometryStatus"], "within-plan")
        self.assertEqual(geometry_result(p, [200, 209])["geometryStatus"], "outside-plan")

    def test_metadata_only_plan_comparison_detects_changed_generation_inputs(self):
        p = build_asset(asset())
        baseline = {"reference": {"sha256": "0" * 64}, "assets": [p]}
        candidate = copy.deepcopy(baseline)
        self.assertTrue(compare_plans(baseline, candidate)["ok"])
        candidate["assets"][0]["requestedCanvas"][0] += 1
        result = compare_plans(baseline, candidate)
        self.assertFalse(result["ok"])
        self.assertIn("frame.requestedCanvas", result["differences"])

    def test_plan_comparison_ignores_png_encoding_but_not_pixels(self):
        with tempfile.TemporaryDirectory() as d:
            first = Path(d)/"first.png"; second = Path(d)/"second.png"
            pixels = Image.new("RGB", (10, 10), "orange")
            pixels.save(first, compress_level=0)
            pixels.save(second, compress_level=9)
            before = build_asset(add_measurement(asset(), first), require_measurement=True)
            after = build_asset(add_measurement(asset(), second), require_measurement=True)
            self.assertNotEqual(before["measurementEvidence"]["evidenceSha256"],
                                after["measurementEvidence"]["evidenceSha256"])
            self.assertEqual(before["measurementEvidence"]["evidencePixelSha256"],
                             after["measurementEvidence"]["evidencePixelSha256"])
            baseline = {"reference": {"sha256": "0" * 64}, "assets": [before]}
            candidate = {"reference": {"sha256": "0" * 64}, "assets": [after]}
            self.assertTrue(compare_plans(baseline, candidate)["ok"])

    def test_historical_two_pixel_foreground_tolerance_uses_default_floor(self):
        a = asset(); a["targetVisibleBounds"].update(width=27, height=18)
        p = build_asset(a)
        p["geometryPolicy"]["lockAxis"] = "height"
        p["geometryPolicy"]["maxSizeDeltaPx"] = 2  # historical frozen plan
        r = geometry_result(p, [979, 726])
        self.assertAlmostEqual(r["sizeDeltaPx"], -2.72727272727)
        self.assertEqual(r["configuredTolerancePx"], 2)
        self.assertEqual(r["effectiveTolerancePx"], 4)
        self.assertTrue(r["geometryWarning"])
        self.assertEqual(r["geometryStatus"], "within-plan")

    def test_outside_geometry_can_continue_only_as_explicit_target_size_warning(self):
        with tempfile.TemporaryDirectory() as d:
            evidence = Path(d)/"reference-crop.png"
            Image.new("RGB", (100, 100), "orange").save(evidence)
            a = asset(); a["targetVisibleBounds"].update(width=100, height=100)
            p = build_asset(add_measurement(a, evidence), require_measurement=True)
            image = Image.new("RGBA", (220, 240), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((10, 10, 209, 229), fill=(190, 90, 40, 255))
            raw = Path(d)/"raw.png"; image.save(raw)
            review_path = Path(d)/"review.md"; review_path.write_text("Target-size geometry review")
            base = {"rawPath": str(raw), "finalPath": str(raw), "promptSha256": p["promptSha256"]}
            accepted = assess(p, {**base, "visualReview": {
                "status": "warning", "note": "Not visible at target size", "evidencePath": str(review_path),
                "evidenceScale": "target-100%", "reasonCode": "geometry-outside-default-tolerance"}})
            self.assertEqual(accepted["geometryStatus"], "outside-plan")
            self.assertEqual(accepted["geometryDisposition"], "warning-accepted-at-target")
            self.assertTrue(accepted["resourceEligibleForLayout"])
            blocked = assess(p, {**base, "visualReview": {
                "status": "warning", "note": "Generic warning", "evidencePath": str(review_path),
                "evidenceScale": "target-100%", "reasonCode": "minor-visual-difference"}})
            self.assertEqual(blocked["geometryDisposition"], "blocked")
            self.assertFalse(blocked["resourceEligibleForLayout"])

    def test_target_visible_geometry_difference_remains_a_hard_failure(self):
        with tempfile.TemporaryDirectory() as d:
            evidence = Path(d)/"reference-crop.png"
            Image.new("RGB", (100, 100), "orange").save(evidence)
            a = asset(); a["targetVisibleBounds"].update(width=100, height=100)
            p = build_asset(add_measurement(a, evidence), require_measurement=True)
            image = Image.new("RGBA", (220, 240), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((10, 10, 209, 229), fill=(190, 90, 40, 255))
            raw = Path(d)/"raw.png"; image.save(raw)
            review_path = Path(d)/"review.md"; review_path.write_text("Visible target-size failure")
            result = assess(p, {"rawPath": str(raw), "finalPath": str(raw),
                "promptSha256": p["promptSha256"], "visualReview": {
                    "status": "failed", "note": "Visible distortion", "evidencePath": str(review_path),
                    "evidenceScale": "target-100%", "reasonCode": "visible-at-target-size"}})
            self.assertFalse(result["resourceEligibleForLayout"])

    def test_alpha_route_does_not_predict_visual_quality(self):
        a = asset(); a["targetVisibleBounds"].update(width=100, height=100)
        p = build_asset(a)
        with tempfile.TemporaryDirectory() as d:
            image = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((10, 10, 209, 209), fill=(190, 90, 40, 255))
            raw = Path(d)/"raw.png"; image.save(raw)
            evidence = Path(d)/"review.md"; evidence.write_text("Synthetic test review only")
            obs = {"rawPath": str(raw), "finalPath": str(raw), "promptSha256": p["promptSha256"]}
            reviews = [
                ({"status": "pending", "note": "Fixture evidence", "evidencePath": str(evidence)}, False),
                ({"status": "failed", "note": "Fixture evidence", "evidencePath": str(evidence),
                  "evidenceScale": "target-100%", "reasonCode": "visible-at-target-size"}, False),
                ({"status": "warning", "note": "Fixture evidence", "evidencePath": str(evidence),
                  "evidenceScale": "target-100%", "reasonCode": "minor-visual-difference"}, True),
                ({"status": "passed", "note": "Fixture evidence", "evidencePath": str(evidence)}, True),
            ]
            for review, eligible in reviews:
                obs["visualReview"] = review
                r = assess(p, obs)
                self.assertEqual(r["routeStatus"], "unexpected-alpha")
                self.assertEqual(r["resourceEligibleForLayout"], eligible)
                self.assertFalse(r["controlledRouteSample"])
            obs["promptSha256"] = "wrong"
            with self.assertRaises(ValueError): assess(p, obs)

    def test_warning_and_failure_require_target_scale_evidence(self):
        a = asset(); a["targetVisibleBounds"].update(width=100, height=100)
        p = build_asset(a)
        with tempfile.TemporaryDirectory() as d:
            image = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((10, 10, 209, 209), fill=(190, 90, 40, 255))
            raw = Path(d)/"raw.png"; image.save(raw)
            evidence = Path(d)/"review.md"; evidence.write_text("Synthetic test review only")
            base = {"rawPath": str(raw), "finalPath": str(raw), "promptSha256": p["promptSha256"]}
            for review in [
                {"status": "warning", "note": "Minor", "evidencePath": str(evidence),
                 "reasonCode": "minor-visual-difference"},
                {"status": "failed", "note": "Only visible enlarged", "evidencePath": str(evidence),
                 "evidenceScale": "alpha-risk-200%", "reasonCode": "visible-at-target-size"},
            ]:
                with self.assertRaises(ValueError):
                    assess(p, {**base, "visualReview": review})

    def test_historical_review_without_new_evidence_fields_remains_readable(self):
        a = asset(); a["targetVisibleBounds"].update(width=100, height=100)
        p = build_asset(a); p.pop("assessmentPolicyVersion")
        with tempfile.TemporaryDirectory() as d:
            image = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((10, 10, 209, 209), fill=(190, 90, 40, 255))
            raw = Path(d)/"raw.png"; image.save(raw)
            evidence = Path(d)/"review.md"; evidence.write_text("Historical review")
            obs = {"rawPath": str(raw), "finalPath": str(raw), "promptSha256": p["promptSha256"],
                   "visualReview": {"status": "failed", "note": "Historical evidence", "evidencePath": str(evidence)}}
            self.assertFalse(assess(p, obs)["resourceEligibleForLayout"])

    def test_existing_file_is_not_valid_extraction_evidence(self):
        a = asset(); a["targetVisibleBounds"].update(width=100, height=100)
        p = build_asset(a)
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d)/"raw.png"; Image.new("RGB", (200, 200), "magenta").save(raw)
            final = Path(d)/"final.png"; im = Image.new("RGBA", (220, 220), (0,0,0,0))
            ImageDraw.Draw(im).rectangle((10,10,209,209), fill=(20,20,20,255)); im.save(final)
            report = Path(d)/"report.json"; report.write_text('{}')
            obs = {"rawPath": str(raw), "finalPath": str(final), "promptSha256": p["promptSha256"],
                   "extractionReport": str(report), "visualReview": {"status": "passed", "note": "Fixture", "evidencePath": str(report)}}
            r = assess(p, obs)
            self.assertEqual(r["routeStatus"], "key-extraction-unverified")
            self.assertFalse(r["resourceEligibleForLayout"])


if __name__ == "__main__":
    unittest.main()
