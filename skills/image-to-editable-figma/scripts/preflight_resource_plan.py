#!/usr/bin/env python3
"""Validate resource routing before generating assets or writing HTML."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from preflight_html import (
    BASE_REUSE_EVIDENCE_FIELDS,
    COMPLEXITY_SIGNALS,
    FIGMA_NODE_TYPES,
    IMAGE_REQUIRED_KINDS,
    RESOURCE_SOURCE_METHODS,
    REUSE_SOURCE_METHODS,
    ROUTING_EXCEPTION_TYPES,
    SEPARATION_EVIDENCE_FIELDS,
    SHA256_RE,
    SUPPORTED_RESOURCE_KINDS,
    read_json_object,
    sha256_file,
)


def validate_reference_items(
    manifest: dict[str, object], errors: list[str], warnings: list[str]
) -> None:
    reference = manifest.get("reference")
    references = manifest.get("references")
    if isinstance(reference, dict) and references is None:
        items = [reference]
    elif reference is None and isinstance(references, list) and references:
        items = references
    else:
        errors.append(
            "Resource manifest must contain either one reference object or a non-empty references array"
        )
        return

    seen_hashes: set[str] = set()
    for index, item in enumerate(items):
        label = "reference" if len(items) == 1 else f"references[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        raw_path = item.get("path")
        expected_sha = item.get("sha256")
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(f"{label}.path must be a non-empty absolute path")
            continue
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            errors.append(f"{label}.path must be absolute")
        elif not path.is_file():
            errors.append(f"{label} image not found: {path}")
        elif not isinstance(expected_sha, str) or not SHA256_RE.fullmatch(expected_sha):
            errors.append(f"{label}.sha256 must be 64 lowercase hex characters")
        else:
            if expected_sha in seen_hashes:
                warnings.append(f"{label} repeats an earlier reference SHA-256")
            seen_hashes.add(expected_sha)
            actual_sha = sha256_file(path)
            if actual_sha != expected_sha:
                errors.append(
                    f"{label} SHA-256 mismatch: expected {expected_sha}, got {actual_sha}"
                )


def validate_generation_policy(manifest: dict[str, object], errors: list[str]) -> None:
    policy = manifest.get("generationPolicy")
    if not isinstance(policy, dict):
        errors.append("generationPolicy must be an object")
        return
    if policy.get("scope") != "per-visual-atom":
        errors.append("generationPolicy.scope must be 'per-visual-atom'")
    calls_per_atom = policy.get("defaultHighQualityCallsPerAtom")
    if calls_per_atom != 1 or isinstance(calls_per_atom, bool):
        errors.append("generationPolicy.defaultHighQualityCallsPerAtom must be 1")
    if "pageWideCap" not in policy or policy.get("pageWideCap") is not None:
        errors.append("generationPolicy.pageWideCap must be null")


def validate_reuse_evidence(
    asset: dict[str, object], source_method: object, label: str, errors: list[str]
) -> None:
    if not isinstance(source_method, str) or source_method not in REUSE_SOURCE_METHODS:
        return
    evidence = asset.get("reuseEvidence")
    if not isinstance(evidence, dict):
        errors.append(f"{label}.reuseEvidence must be an object for {source_method}")
        return
    required = set(BASE_REUSE_EVIDENCE_FIELDS)
    if source_method == "reliable-separation":
        required.update(SEPARATION_EVIDENCE_FIELDS)
    for field in sorted(required):
        if evidence.get(field) is not True:
            errors.append(f"{label}.reuseEvidence.{field} must be true for {source_method}")
    note = evidence.get("inspectionNote")
    if not isinstance(note, str) or not note.strip():
        errors.append(
            f"{label}.reuseEvidence.inspectionNote must be a non-empty string for {source_method}"
        )


def validate_assets(manifest: dict[str, object], errors: list[str]) -> dict[str, int]:
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        errors.append("assets must be a non-empty array")
        return {"asset_count": 0, "image_count": 0, "reuse_count": 0}

    seen_ids: set[str] = set()
    image_count = 0
    reuse_count = 0
    for index, asset in enumerate(assets):
        label = f"assets[{index}]"
        if not isinstance(asset, dict):
            errors.append(f"{label} must be an object")
            continue

        resource_id = asset.get("id")
        if not isinstance(resource_id, str) or not resource_id.strip():
            errors.append(f"{label}.id must be a non-empty string")
        elif resource_id in seen_ids:
            errors.append(f"Duplicate resource id: {resource_id}")
        else:
            seen_ids.add(resource_id)
            label = f"Resource {resource_id!r}"

        kind = asset.get("kind")
        if kind not in SUPPORTED_RESOURCE_KINDS:
            errors.append(f"{label}.kind is unsupported: {kind!r}")

        signals = asset.get("complexitySignals")
        if not isinstance(signals, list) or any(not isinstance(value, str) for value in signals):
            errors.append(f"{label}.complexitySignals must be an array of strings")
            signals = []
        else:
            unknown = sorted(set(signals) - COMPLEXITY_SIGNALS)
            if unknown:
                errors.append(f"{label} has unsupported complexity signals: {unknown}")
        if kind == "simple-decoration" and signals:
            errors.append(
                f"{label} cannot be simple-decoration while complexitySignals are present"
            )

        expected_raw = asset.get("expectedFigmaType")
        expected = expected_raw.upper() if isinstance(expected_raw, str) else ""
        if expected not in FIGMA_NODE_TYPES:
            errors.append(f"{label}.expectedFigmaType is invalid: {expected_raw!r}")

        routing_exception = asset.get("routingException")
        valid_exception = False
        if isinstance(routing_exception, dict):
            valid_exception = (
                routing_exception.get("type") in ROUTING_EXCEPTION_TYPES
                and isinstance(routing_exception.get("evidence"), str)
                and bool(routing_exception["evidence"].strip())
            )
        elif routing_exception is not None:
            errors.append(f"{label}.routingException must be an object")
        if kind in IMAGE_REQUIRED_KINDS and expected != "IMAGE" and not valid_exception:
            errors.append(f"{label} kind={kind!r} must remain IMAGE")
        if expected == "IMAGE":
            image_count += 1

        source_method = asset.get("sourceMethod")
        if not isinstance(source_method, str) or source_method not in RESOURCE_SOURCE_METHODS:
            errors.append(
                f"{label}.sourceMethod must be one of {sorted(RESOURCE_SOURCE_METHODS)}, got {source_method!r}"
            )
        if isinstance(source_method, str) and source_method in REUSE_SOURCE_METHODS:
            reuse_count += 1
        validate_reuse_evidence(asset, source_method, label, errors)

        if not isinstance(asset.get("compositionId"), str) or not asset["compositionId"].strip():
            errors.append(f"{label}.compositionId must be a non-empty string")
        if not isinstance(asset.get("editableInternals"), bool):
            errors.append(f"{label}.editableInternals must be boolean")
        fallbacks = asset.get("fallbacks")
        if not isinstance(fallbacks, list):
            errors.append(f"{label}.fallbacks must be an array")
            fallbacks = []
        for fallback_index, fallback in enumerate(fallbacks):
            fallback_label = f"{label}.fallbacks[{fallback_index}]"
            if not isinstance(fallback, dict):
                errors.append(f"{fallback_label} must be an object")
                continue
            fallback_type_raw = fallback.get("figmaType")
            fallback_type = (
                fallback_type_raw.upper() if isinstance(fallback_type_raw, str) else ""
            )
            if not isinstance(fallback.get("method"), str) or not fallback["method"].strip():
                errors.append(f"{fallback_label}.method must be a non-empty string")
            if fallback_type not in FIGMA_NODE_TYPES:
                errors.append(f"{fallback_label}.figmaType is invalid: {fallback_type_raw!r}")
            if expected == "IMAGE" and fallback_type != "IMAGE":
                errors.append(f"{fallback_label} changes an IMAGE resource to {fallback_type}")

    return {
        "asset_count": len(assets),
        "image_count": image_count,
        "reuse_count": reuse_count,
    }


def run(manifest_path: Path) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    manifest = read_json_object(manifest_path, "Resource manifest", errors)
    if manifest is None:
        return {"ok": False, "errors": errors, "warnings": warnings, "metrics": {}}

    if manifest.get("schemaVersion") != 3:
        errors.append("Resource manifest schemaVersion must be 3")
    validate_generation_policy(manifest, errors)
    validate_reference_items(manifest, errors, warnings)
    metrics = validate_assets(manifest, errors)
    metrics["manifest"] = str(manifest_path)
    metrics["schema_version"] = manifest.get("schemaVersion")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "metrics": metrics}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to resource-manifest.json")
    args = parser.parse_args()
    result = run(args.manifest.expanduser().resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
