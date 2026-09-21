#!/usr/bin/env python3
"""Build lab prompts from one geometry source; assess returned files without regenerating."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

GENERATED = {"reference-guided-edit", "new-generation", "localized-repair"}
EDGES = {"left", "right", "top", "bottom"}
SPEC_FIELDS = {"description", "invariants", "exclusions", "canvasSize", "subjectTouchEdges"}
DEFAULT_FOREGROUND_GEOMETRY_TOLERANCE_PX = 4
LAB_GENERATION_CONTRACT_VERSION = 2
DELIVERY_PROMPT_PLAN_VERSION = 1
STRUCTURED_REVIEW_POLICY_VERSION = 2
ASSESSMENT_POLICY_VERSION = 3
VISUAL_REVIEW_STATUSES = {"pending", "passed", "warning", "failed"}
WARNING_REASONS = {
    "minor-visual-difference",
    "geometry-within-default-tolerance",
    "geometry-outside-default-tolerance",
}
FAILURE_REASONS = {
    "visible-at-target-size",
    "structural-defect",
    "alpha-defect",
    "wrong-text",
    "missing-or-extra-subject",
}
EVIDENCE_SCALES = {"target-100%", "alpha-risk-200%"}
# Geometry belongs in structured fields, never in handwritten prompt fragments.
DIMENSION_TEXT = re.compile(r"\d\s*(?:%|％|px\b|pixels?\b|像素|[×xX:]\s*\d|比\s*\d)", re.I)


def bounds(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label}: bounds object required")
    result = {}
    for coordinate in ("x", "y"):
        current = value.get(coordinate)
        if isinstance(current, bool) or not isinstance(current, (int, float)) or not math.isfinite(current):
            raise ValueError(f"{label}.{coordinate}: finite coordinate required")
        result[coordinate] = current
    for dimension in ("width", "height"):
        result[dimension] = number(value.get(dimension), f"{label}.{dimension}")
    return result


def verified_measurement(asset, target, required=False):
    """Freeze a two-pass reference measurement before any generation call."""
    evidence = asset.get("measurementEvidence")
    if evidence is None:
        if required:
            raise ValueError(f"{asset.get('id', 'asset')}.measurementEvidence required by contract v2")
        return None
    expected = {"method", "evidencePath", "firstBounds", "secondBounds"}
    if not isinstance(evidence, dict) or set(evidence) != expected:
        raise ValueError("measurementEvidence requires method, evidencePath, firstBounds and secondBounds")
    if evidence["method"] != "two-pass-reference-crop":
        raise ValueError("measurementEvidence.method must be two-pass-reference-crop")
    first = bounds(evidence["firstBounds"], "measurementEvidence.firstBounds")
    second = bounds(evidence["secondBounds"], "measurementEvidence.secondBounds")
    if first != second:
        raise ValueError("measurementEvidence passes disagree; resolve the reference boundary before generation")
    if first != target:
        raise ValueError("measurementEvidence does not match targetVisibleBounds")
    evidence_path = Path(text(evidence["evidencePath"], "measurementEvidence.evidencePath")).resolve(strict=True)
    from PIL import Image
    with Image.open(evidence_path) as source:
        normalized = source.convert("RGBA")
        pixel_payload = f"{normalized.width}x{normalized.height}\0".encode() + normalized.tobytes()
    return {
        "status": "verified",
        "method": evidence["method"],
        "evidencePath": str(evidence_path),
        "evidenceSha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "evidencePixelSha256": hashlib.sha256(pixel_payload).hexdigest(),
        "firstBounds": first,
        "secondBounds": second,
    }


def number(value, label, positive=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label}: finite number required")
    if (positive and value <= 0) or (not positive and value < 0):
        raise ValueError(f"{label}: {'positive' if positive else 'nonnegative'} number required")
    return value


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: nonempty text required")
    return value.strip()


def build_asset(asset, require_measurement=False):
    asset_id = text(asset.get("id"), "id")
    text(asset.get("generationReason"), f"{asset_id}.generationReason")
    if asset.get("expectedFigmaType") != "IMAGE":
        raise ValueError(f"{asset_id}: generated assets must target IMAGE")
    spec = asset.get("generationSpec")
    if not isinstance(spec, dict) or set(spec) - SPEC_FIELDS:
        raise ValueError(f"{asset_id}.generationSpec: missing object or unknown fields")
    description = text(spec.get("description"), "description")
    fragments = [description]
    for name in ("invariants", "exclusions"):
        values = spec.get(name)
        if not isinstance(values, list) or not values:
            raise ValueError(f"{asset_id}.{name}: nonempty array required")
        fragments.extend(text(v, name) for v in values)
    if any(DIMENSION_TEXT.search(v) for v in fragments):
        raise ValueError(f"{asset_id}: move pixel dimensions, ratios and percentages into structured geometry")
    target_bounds = bounds(asset.get("targetVisibleBounds"), f"{asset_id}.targetVisibleBounds")
    measurement = verified_measurement(asset, target_bounds, required=require_measurement)
    w, h = target_bounds["width"], target_bounds["height"]
    alpha = asset.get("alphaRequired")
    if not isinstance(alpha, bool):
        raise ValueError(f"{asset_id}.alphaRequired must be boolean")
    edges = spec.get("subjectTouchEdges", [])
    if not isinstance(edges, list) or any(e not in EDGES for e in edges) or len(set(edges)) != len(edges):
        raise ValueError(f"{asset_id}: invalid subjectTouchEdges")
    if not alpha and edges:
        raise ValueError(f"{asset_id}: opaque full-bleed images do not use subjectTouchEdges")
    policy = asset.get("geometryPolicy")
    if not isinstance(policy, dict) or set(policy) != {"lockAxis", "maxSizeDeltaPx", "reason"}:
        raise ValueError(f"{asset_id}: geometryPolicy requires lockAxis, maxSizeDeltaPx, reason")
    if policy["lockAxis"] not in {"width", "height"}:
        raise ValueError(f"{asset_id}: invalid lockAxis")
    tolerance = number(policy["maxSizeDeltaPx"], "maxSizeDeltaPx", positive=False)
    if alpha and tolerance < DEFAULT_FOREGROUND_GEOMETRY_TOLERANCE_PX:
        raise ValueError(
            f"{asset_id}: transparent foreground maxSizeDeltaPx cannot be below "
            f"{DEFAULT_FOREGROUND_GEOMETRY_TOLERANCE_PX}; use target-size visual review for stricter concerns"
        )
    text(policy["reason"], "geometryPolicy.reason")
    # The requested canvas may vary; the subject aspect always comes from targetVisibleBounds.
    margins = {edge: (0 if edge in edges or not alpha else 32) for edge in EDGES}
    default_canvas = [math.ceil(2*w) + margins["left"] + margins["right"],
                      math.ceil(2*h) + margins["top"] + margins["bottom"]]
    canvas = spec.get("canvasSize", default_canvas)
    if not isinstance(canvas, list) or len(canvas) != 2:
        raise ValueError(f"{asset_id}.canvasSize must contain two integers")
    for value in canvas:
        number(value, "canvasSize")
        if not isinstance(value, int):
            raise ValueError(f"{asset_id}.canvasSize must contain integers")
    available_w = canvas[0] - margins["left"] - margins["right"]
    available_h = canvas[1] - margins["top"] - margins["bottom"]
    scale = min(available_w/w, available_h/h)
    if scale < 1.5:
        raise ValueError(f"{asset_id}: requested subject effective scale {scale:.3f} < 1.5")
    sw, sh = w*scale, h*scale
    # Opposite touch edges require the subject to span that dimension.
    for axis, start, end, available, size in ((0, "left", "right", available_w, sw), (1, "top", "bottom", available_h, sh)):
        if start in edges and end in edges and not math.isclose(size, available):
            raise ValueError(f"{asset_id}: opposing {start}/{end} touch edges conflict with aspect ratio")
    x = 0 if "left" in edges else canvas[0]-sw if "right" in edges else (canvas[0]-sw)/2
    y = 0 if "top" in edges else canvas[1]-sh if "bottom" in edges else (canvas[1]-sh)/2
    if not alpha and abs(canvas[0]/canvas[1] - w/h)/(w/h) > .005:
        raise ValueError(f"{asset_id}: opaque canvas must match target aspect (within rounding tolerance)")
    prompt = ["Use the supplied reference as the exact subject, geometry, palette and material reference. Preserve identity and proportions; do not redesign. This is a faithful editable reconstruction.",
              description, "Preserve: " + "; ".join(spec["invariants"]) + ".",
              "Exclude: " + "; ".join(spec["exclusions"]) + ".",
              f"Requested output canvas: {canvas[0]} x {canvas[1]} pixels."]
    if alpha:
        key = asset.get("keyPlan")
        if not isinstance(key, dict) or not re.fullmatch(r"#[0-9a-fA-F]{6}", str(key.get("hex", ""))):
            raise ValueError(f"{asset_id}: keyPlan.hex required")
        text(key.get("conflictCheck"), "keyPlan.conflictCheck")
        rgb = [int(key["hex"][i:i+2], 16) for i in (1, 3, 5)]
        if max(rgb) < 192 or max(rgb)-min(rgb) < 128:
            raise ValueError(f"{asset_id}: key must be a high-saturation bright color, never white or gray")
        prompt.extend([
            f"Output fully opaque RGB with a perfectly flat single saturated {key['hex']} background. Do NOT output transparency, remove the background, or paint any checkerboard. No key color in the subject, reflected light, highlights or fringe.",
            f"Visible subject bounding box: x={x:.2f}, y={y:.2f}, width={sw:.2f}, height={sh:.2f} pixels. This is the only subject size specification; do not stretch or redesign to fill the canvas.",
            "Keep continuous key-color margins on all non-touching edges. Preserve white fur, pale highlights and all real opaque interior regions. Never fade clothing, torso or cut edges into transparency.",
            "Declared subject touch/crop edges: " + (", ".join(edges) if edges else "none; entire silhouette stays inside the canvas") + "."
        ])
    else:
        prompt.append("Output opaque RGB, full bleed; no alpha, no checkerboard, no added border. Preserve the reference framing.")
    rendered = "\n".join(prompt)
    result = {"assetId": asset_id, "referenceBounds": target_bounds, "alphaRequired": alpha,
            "assessmentPolicyVersion": ASSESSMENT_POLICY_VERSION,
            "geometryPolicy": dict(policy), "requestedCanvas": canvas,
            "requestedSubjectBounds": {"x": x, "y": y, "width": sw, "height": sh},
            "requestedEffectiveScale": scale, "subjectTouchEdges": edges,
            "prompt": rendered, "promptSha256": hashlib.sha256(rendered.encode()).hexdigest()}
    if measurement:
        result["measurementEvidence"] = measurement
    return result


def validate_contract(manifest, errors, required=False):
    version = manifest.get("labGenerationContractVersion")
    if version is None and not required:
        return []  # Historical records are never silently migrated.
    if isinstance(version, bool) or version not in {1, LAB_GENERATION_CONTRACT_VERSION}:
        errors.append("labGenerationContractVersion must be 1 (historical) or 2")
        return []
    if required and version != LAB_GENERATION_CONTRACT_VERSION:
        errors.append("new lab rounds require labGenerationContractVersion 2 with measurement evidence")
        return []
    plans = []
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        errors.append("assets must be an array")
        return []
    for asset in assets:
        if isinstance(asset, dict) and asset.get("sourceMethod") in GENERATED:
            try:
                plans.append(build_asset(asset, require_measurement=version >= LAB_GENERATION_CONTRACT_VERSION))
            except (ValueError, TypeError) as exc:
                errors.append(str(exc))
    return plans


def validate_delivery_prompt_contract(manifest, errors, required=True):
    """Freeze delivery prompts without adding the experiment-only two-pass measurement."""
    version = manifest.get("deliveryPromptPlanVersion")
    if version is None and not required:
        return []
    if isinstance(version, bool) or version != DELIVERY_PROMPT_PLAN_VERSION:
        errors.append(f"deliveryPromptPlanVersion must be {DELIVERY_PROMPT_PLAN_VERSION}")
        return []
    plans = []
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        errors.append("assets must be an array")
        return []
    for asset in assets:
        if isinstance(asset, dict) and asset.get("sourceMethod") in GENERATED:
            try:
                plans.append(build_asset(asset, require_measurement=False))
            except (ValueError, TypeError) as exc:
                errors.append(str(exc))
    return plans


STABLE_ASSET_FIELDS = (
    "assetId", "referenceBounds", "alphaRequired", "geometryPolicy", "requestedCanvas",
    "requestedSubjectBounds", "requestedEffectiveScale", "subjectTouchEdges", "promptSha256",
)


def stable_plan_projection(plan):
    """Return metadata-only generation inputs; generated pixels are deliberately excluded."""
    references = plan.get("references")
    if references is None:
        references = [plan.get("reference")]
    reference_hashes = []
    for item in references:
        if not isinstance(item, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
            raise ValueError("generation plan references must contain lowercase SHA-256 values")
        reference_hashes.append(item["sha256"])
    assets = []
    for item in sorted(plan.get("assets", []), key=lambda value: value.get("assetId", "")):
        projected = {field: item.get(field) for field in STABLE_ASSET_FIELDS}
        measurement = item.get("measurementEvidence")
        projected["measurementEvidence"] = None if measurement is None else {
            key: measurement.get(key) for key in ("status", "method", "evidencePixelSha256", "firstBounds", "secondBounds")
        }
        assets.append(projected)
    return {"referenceSha256": reference_hashes, "assets": assets}


def compare_plans(baseline, candidate):
    before = stable_plan_projection(baseline)
    after = stable_plan_projection(candidate)
    differences = []
    if before["referenceSha256"] != after["referenceSha256"]:
        differences.append("referenceSha256")
    before_assets = {item["assetId"]: item for item in before["assets"]}
    after_assets = {item["assetId"]: item for item in after["assets"]}
    if set(before_assets) != set(after_assets):
        differences.append("assetIds")
    for asset_id in sorted(set(before_assets) & set(after_assets)):
        for field in (*STABLE_ASSET_FIELDS[1:], "measurementEvidence"):
            if before_assets[asset_id].get(field) != after_assets[asset_id].get(field):
                differences.append(f"{asset_id}.{field}")
    return {"ok": not differences, "differences": differences,
            "baseline": before, "candidate": after}


def geometry_result(plan, visible_size):
    w, h = (number(v, "visibleSize") for v in visible_size)
    target = plan["referenceBounds"]
    tw, th = target["width"], target["height"]
    if plan["geometryPolicy"]["lockAxis"] == "width":
        display = [tw, tw*h/w]
        delta = display[1]-th
    else:
        display = [th*w/h, th]
        delta = display[0]-tw
    configured_tolerance = plan["geometryPolicy"]["maxSizeDeltaPx"]
    effective_tolerance = configured_tolerance
    if plan.get("alphaRequired"):
        # Historical plans may contain an over-tight foreground tolerance. Keep their
        # original value for audit, but never let an invisible sub-4px difference block layout.
        effective_tolerance = max(configured_tolerance, DEFAULT_FOREGROUND_GEOMETRY_TOLERANCE_PX)
    within_configured = abs(delta) <= configured_tolerance
    within_effective = abs(delta) <= effective_tolerance
    return {"visibleSize": [w, h], "displaySize": display, "sizeDeltaPx": delta,
            "effectiveScale": min(w/display[0], h/display[1]),
            "configuredTolerancePx": configured_tolerance,
            "effectiveTolerancePx": effective_tolerance,
            "geometryWarning": bool(within_effective and not within_configured),
            "geometryStatus": "within-plan" if within_effective else "outside-plan"}


def inspect_image(path):
    from PIL import Image
    path = Path(path).resolve(strict=True)
    with Image.open(path) as source:
        rgba = source.convert("RGBA")
        alpha = rgba.getchannel("A")
        bbox = alpha.getbbox()
        if not bbox:
            raise ValueError(f"{path}: fully transparent image")
        return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "hasNonopaquePixels": alpha.getextrema()[0] < 255,
                "visibleSize": [bbox[2]-bbox[0], bbox[3]-bbox[1]]}


def assess(plan, observation):
    if observation.get("promptSha256") != plan["promptSha256"]:
        raise ValueError("promptSha256 does not match the frozen generation plan")
    raw = inspect_image(observation["rawPath"])
    final = inspect_image(observation["finalPath"])
    route = "unexpected-alpha" if raw["hasNonopaquePixels"] else "opaque-return"
    # Opaque pixels alone do not prove a correct key; require the extractor's audit.
    if plan["alphaRequired"] and route == "opaque-return":
        audit_path = observation.get("extractionReport")
        route = "key-extraction-unverified"
        if audit_path:
            # Keep the report as evidence; its visual/acceptance interpretation remains a review step.
            audit = json.loads(Path(audit_path).read_text())
            valid_audit = (audit.get("status") != "rejected"
                           and Path(audit.get("input", "")).resolve() == Path(raw["path"])
                           and Path(audit.get("output", "")).resolve() == Path(final["path"])
                           and audit.get("parameters", {}).get("generated_key_input") is True
                           and audit.get("output_alpha", {}).get("has_nonopaque_pixels") is True
                           and audit.get("output_alpha", {}).get("has_visible_pixels") is True)
            route = "key-extraction-recorded" if valid_audit else "key-extraction-unverified"
    review = observation.get("visualReview", {"status": "pending"})
    status = review.get("status")
    if status not in VISUAL_REVIEW_STATUSES:
        raise ValueError("visualReview.status must be pending, passed, warning or failed")
    if status != "pending":
        text(review.get("note"), "visualReview.note")
        Path(review["evidencePath"]).resolve(strict=True)
    if plan.get("assessmentPolicyVersion", 1) >= STRUCTURED_REVIEW_POLICY_VERSION and status in {"warning", "failed"}:
        evidence_scale = review.get("evidenceScale")
        if evidence_scale not in EVIDENCE_SCALES:
            raise ValueError("warning/failed visual review requires evidenceScale target-100% or alpha-risk-200%")
        reason_code = review.get("reasonCode")
        allowed_reasons = WARNING_REASONS if status == "warning" else FAILURE_REASONS
        if reason_code not in allowed_reasons:
            raise ValueError(f"visualReview.reasonCode must be one of {sorted(allowed_reasons)} for {status}")
        if status == "warning" and evidence_scale != "target-100%":
            raise ValueError("non-blocking visual warnings must be judged at target-100%")
        if status == "failed" and evidence_scale == "alpha-risk-200%" and reason_code not in {"alpha-defect", "structural-defect"}:
            raise ValueError("200% evidence can only block an alpha or structural defect")
    geom = geometry_result(plan, final["visibleSize"])
    alpha_ok = final["hasNonopaquePixels"] == plan["alphaRequired"]
    geometry_warning_accepted = (
        plan.get("assessmentPolicyVersion", 1) >= ASSESSMENT_POLICY_VERSION
        and plan.get("alphaRequired") is True
        and plan.get("measurementEvidence", {}).get("status") == "verified"
        and geom["geometryStatus"] == "outside-plan"
        and status == "warning"
        and review.get("evidenceScale") == "target-100%"
        and review.get("reasonCode") == "geometry-outside-default-tolerance"
    )
    geometry_ok = geom["geometryStatus"] == "within-plan" or geometry_warning_accepted
    # A recorded extractor report is NOT machine approval; final review must cover it too.
    eligible = (route != "key-extraction-unverified" and status in {"passed", "warning"} and alpha_ok and geometry_ok
                and geom["effectiveScale"] >= 1.5)
    return {"assetId": plan["assetId"], "raw": raw, "final": final,
            "routeStatus": route, "visualStatus": status, "visualReview": review,
            "alphaStructureMatches": alpha_ok, **geom,
            "geometryDisposition": ("warning-accepted-at-target" if geometry_warning_accepted
                                    else "within-plan" if geom["geometryStatus"] == "within-plan" else "blocked"),
            "resourceEligibleForLayout": eligible,
            "controlledRouteSample": eligible and status == "passed" and geom["geometryStatus"] == "within-plan"
                                     and route in {"opaque-return", "key-extraction-recorded"},
            "pageAcceptance": ("pending HTML composition and user review; non-blocking visual or geometry warning recorded"
                               if status == "warning" or geom["geometryWarning"] or geometry_warning_accepted
                               else "pending HTML composition, anchors and visual review")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("manifest", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--mode",
        choices=("rule-regression", "fresh-generation-stability"),
        default="fresh-generation-stability",
    )
    p.add_argument("--baseline-manifest", type=Path)
    d = sub.add_parser("delivery-plan")
    d.add_argument("manifest", type=Path)
    d.add_argument("--out", type=Path, required=True)
    d.add_argument("--baseline-manifest", type=Path)
    a = sub.add_parser("assess")
    a.add_argument("plan", type=Path)
    a.add_argument("observation", type=Path)
    c = sub.add_parser("compare")
    c.add_argument("baseline", type=Path)
    c.add_argument("candidate", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            from preflight_resource_plan import run
            result = run(
                args.manifest,
                mode=args.mode,
                baseline_manifest_path=args.baseline_manifest,
            )
            if not result["ok"]:
                raise ValueError("; ".join(result["errors"]))
            manifest = json.loads(args.manifest.read_text())
            errors = []
            plans = validate_contract(manifest, errors, required=True)
            output = {"version": 2, "mode": args.mode, "manifestSha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
                      "reference": manifest.get("reference"), "references": manifest.get("references"), "assets": plans}
            # Freeze before any image call; never silently replace a plan from an executed round.
            with args.out.open("x") as file:
                json.dump(output, file, ensure_ascii=False, indent=2)
            print(json.dumps({"ok": True, "assets": len(plans), "out": str(args.out)}, ensure_ascii=False))
        elif args.command == "delivery-plan":
            from preflight_resource_plan import run
            result = run(
                args.manifest,
                mode="delivery",
                baseline_manifest_path=args.baseline_manifest,
            )
            if not result["ok"]:
                raise ValueError("; ".join(result["errors"]))
            manifest = json.loads(args.manifest.read_text())
            errors = []
            plans = validate_delivery_prompt_contract(manifest, errors, required=True)
            if errors:
                raise ValueError("; ".join(errors))
            output = {
                "version": DELIVERY_PROMPT_PLAN_VERSION,
                "mode": "delivery",
                "manifestSha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
                "reference": manifest.get("reference"),
                "references": manifest.get("references"),
                "assets": plans,
            }
            with args.out.open("x") as file:
                json.dump(output, file, ensure_ascii=False, indent=2)
            print(json.dumps({"ok": True, "assets": len(plans), "out": str(args.out)}, ensure_ascii=False))
        elif args.command == "assess":
            plan = json.loads(args.plan.read_text())
            observation = json.loads(args.observation.read_text())
            asset = next(a for a in plan["assets"] if a["assetId"] == observation["assetId"])
            print(json.dumps(assess(asset, observation), ensure_ascii=False, indent=2))
        else:
            result = compare_plans(json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if not result["ok"]:
                return 1
    except (ValueError, KeyError, TypeError, OSError, StopIteration) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
