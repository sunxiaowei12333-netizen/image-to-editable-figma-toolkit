"""Regression fixtures for resource routing, delivery prompt freeze, and warm reuse."""

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from generation_contract import validate_delivery_prompt_contract
from preflight_resource_plan import run


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base_manifest(reference: Path, asset: dict) -> dict:
    return {
        "schemaVersion": 3,
        "executionProfile": "cold-start",
        "deliveryPromptPlanVersion": 1,
        "generationPolicy": {
            "scope": "per-visual-atom",
            "defaultHighQualityCallsPerAtom": 1,
            "pageWideCap": None,
        },
        "reference": {"path": str(reference), "sha256": digest(reference)},
        "assets": [asset],
    }


def native_asset(name: str = "simple-card") -> dict:
    return {
        "id": name,
        "kind": "ui-container",
        "compositionId": name,
        "editableInternals": True,
        "complexitySignals": [],
        "expectedFigmaType": "FRAME",
        "sourceMethod": "native-rebuild",
        "nativeRebuildEvidence": {
            "primitiveGeometryOnly": True,
            "noMaterialTexture": True,
            "noIrregularOrnament": True,
            "noPreciseMaterialLighting": True,
            "inspectionNote": "Flat rounded card with no visual material or ornament.",
        },
        "fallbacks": [],
    }


def generated_asset() -> dict:
    return {
        "id": "ornate-frame",
        "kind": "complex-frame",
        "compositionId": "ornate-frame",
        "editableInternals": False,
        "complexitySignals": ["material_edges", "precise_highlight_shadow"],
        "expectedFigmaType": "IMAGE",
        "sourceMethod": "reference-guided-edit",
        "generationReason": "The complete ornate material frame cannot be rebuilt with primitives.",
        "targetVisibleBounds": {"x": 10, "y": 20, "width": 400, "height": 100},
        "alphaRequired": True,
        "keyPlan": {"hex": "#FF00FF", "conflictCheck": "Absent from the frame and highlights."},
        "geometryPolicy": {"lockAxis": "width", "maxSizeDeltaPx": 4, "reason": "Preserve the reference width."},
        "generationSpec": {
            "description": "Reconstruct only the complete ornate material frame.",
            "invariants": ["Continuous irregular edge and original material lighting"],
            "exclusions": ["All UI text and adjacent content"],
            "canvasSize": [1024, 320],
        },
        "fallbacks": [{"method": "targeted-image-edit", "figmaType": "IMAGE"}],
    }


class ResourceRoutingTests(unittest.TestCase):
    def write_manifest(self, root: Path, name: str, value: dict) -> Path:
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_delivery_prompt_is_frozen_without_experiment_measurement(self):
        manifest = {"deliveryPromptPlanVersion": 1, "assets": [generated_asset()]}
        first_errors = []
        second_errors = []
        first = validate_delivery_prompt_contract(manifest, first_errors, required=True)
        second = validate_delivery_prompt_contract(manifest, second_errors, required=True)
        self.assertEqual(first_errors, [])
        self.assertEqual(second_errors, [])
        self.assertEqual(first[0]["promptSha256"], second[0]["promptSha256"])
        self.assertNotIn("measurementEvidence", first[0])

    def test_delivery_plan_cli_runs_one_preflight_and_writes_frozen_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.png"
            reference.write_bytes(b"fixture")
            manifest_path = self.write_manifest(
                root,
                "resource-manifest.json",
                base_manifest(reference, generated_asset()),
            )
            output_path = root / "delivery-generation-plan.json"
            script = Path(__file__).resolve().parents[1] / "scripts" / "generation_contract.py"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "delivery-plan",
                    str(manifest_path),
                    "--out",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            plan = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(plan["mode"], "delivery")
            self.assertEqual(len(plan["assets"]), 1)
            self.assertNotIn("measurementEvidence", plan["assets"][0])

    def test_delivery_requires_lightweight_prompt_plan_version(self):
        errors = []
        validate_delivery_prompt_contract({"assets": [generated_asset()]}, errors, required=True)
        self.assertRegex(errors[0], "deliveryPromptPlanVersion")

    def test_native_rebuild_requires_affirmative_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.png"
            reference.write_bytes(b"fixture")
            asset = native_asset()
            asset.pop("nativeRebuildEvidence")
            path = self.write_manifest(root, "resource-manifest.json", base_manifest(reference, asset))
            result = run(path, mode="delivery")
            self.assertFalse(result["ok"])
            self.assertTrue(any("nativeRebuildEvidence" in error for error in result["errors"]))

    def test_wooden_tablet_and_ornate_frame_cannot_be_downgraded_to_native(self):
        fixtures = (
            ("wooden-tablet", "material-object", ["material_edges", "texture_or_noise"]),
            ("ornate-frame", "complex-frame", ["irregular_parts", "precise_highlight_shadow"]),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.png"
            reference.write_bytes(b"fixture")
            for name, kind, signals in fixtures:
                with self.subTest(name=name):
                    asset = native_asset(name)
                    asset.update(kind=kind, complexitySignals=signals, expectedFigmaType="FRAME")
                    path = self.write_manifest(
                        root, f"{name}.json", base_manifest(reference, asset)
                    )
                    result = run(path, mode="delivery")
                    self.assertFalse(result["ok"])
                    combined = "\n".join(result["errors"])
                    self.assertIn("must remain IMAGE", combined)
                    self.assertIn("cannot use native-rebuild", combined)

    def test_exact_reference_baseline_rejects_route_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.png"
            reference.write_bytes(b"fixture")
            asset = {
                "id": "back-icon",
                "kind": "ui-icon",
                "compositionId": "back-icon",
                "editableInternals": True,
                "complexitySignals": [],
                "expectedFigmaType": "INSTANCE",
                "sourceMethod": "library-asset",
                "fallbacks": [],
            }
            baseline = base_manifest(reference, asset)
            candidate = copy.deepcopy(baseline)
            candidate["assets"][0]["sourceMethod"] = "provided-original"
            baseline_path = self.write_manifest(root, "baseline.json", baseline)
            candidate_path = self.write_manifest(root, "candidate.json", candidate)
            result = run(candidate_path, mode="delivery", baseline_manifest_path=baseline_path)
            self.assertFalse(result["ok"])
            self.assertIn("back-icon.sourceMethod", "\n".join(result["errors"]))

    def test_warm_cache_requires_explicit_approved_byte_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.png"
            reference.write_bytes(b"reference")
            cached = root / "approved.png"
            cached.write_bytes(b"approved asset")
            baseline = root / "baseline.json"
            baseline.write_text("{}", encoding="utf-8")
            approval = root / "approval-fingerprint.json"
            approval.write_text('{"approved": true}', encoding="utf-8")
            asset = {
                "id": "photo",
                "kind": "photo",
                "compositionId": "photo",
                "editableInternals": False,
                "complexitySignals": [],
                "expectedFigmaType": "IMAGE",
                "sourceMethod": "approved-cache",
                "cacheEvidence": {
                    "sourceReferenceSha256": digest(reference),
                    "sourceAssetSha256": digest(cached),
                    "baselineManifestPath": str(baseline),
                    "baselineManifestSha256": digest(baseline),
                    "approvalFingerprintPath": str(approval),
                    "approvalFingerprintSha256": digest(approval),
                    "currentCopyPath": str(cached),
                    "currentCopySha256": digest(cached),
                    "currentAlphaRevalidated": True,
                    "currentResolutionRevalidated": True,
                },
                "fallbacks": [{"method": "use-approved-copy", "figmaType": "IMAGE"}],
            }
            manifest = base_manifest(reference, asset)
            manifest["executionProfile"] = "warm-reuse"
            path = self.write_manifest(root, "resource-manifest.json", manifest)
            self.assertTrue(run(path, mode="delivery")["ok"])


if __name__ == "__main__":
    unittest.main()
