#!/usr/bin/env python3
"""Validate the final audit contract for editable-design-basic-standards."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from audit_scope import validate_scope


METRIC_FIELDS = {
    "typography": (
        "totalSpans",
        "targetDirect",
        "targetInherited",
        "exceptions",
        "verificationPending",
        "linkRegressed",
        "otherStyle",
        "unmapped",
        "unclassified",
        "unresolvedUnlinked",
    ),
    "color": (
        "totalSpans",
        "targetDirect",
        "targetInherited",
        "exceptions",
        "otherStyle",
        "exactUnlinked",
        "unclassified",
        "unresolvedUnlinked",
    ),
}

MUTATION_FIELDS = (
    "createdLocalComponents",
    "createdComponentSets",
    "replacedWithLocalInstances",
)

ASSET_TYPES = {"TEXT_STYLE", "PAINT_STYLE", "COMPONENT", "COMPONENT_SET"}
SOURCE_TYPES = {"target-library", "local-copy"}


def fail(message: str) -> None:
    print(f"INVALID: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_object(parent: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} must be an object")
        return {}
    return value


def require_nonempty_string(value: Any, path: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} must be a non-empty string")
        return ""
    return value


def require_count(parent: dict[str, Any], key: str, path: str, errors: list[str]) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"{path}.{key} must be a non-negative integer")
        return 0
    return value


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        fail(f"cannot read {path}: {exc}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path}: {exc}")
    if not isinstance(value, dict):
        fail("top-level JSON value must be an object")
    return value


def validate(path: Path) -> tuple[str, list[str]]:
    data = load(path)
    errors: list[str] = []
    blockers: list[str] = []

    status = data.get("status")
    if status not in {"complete", "incomplete"}:
        errors.append("status must be 'complete' or 'incomplete'")

    p0_passed = data.get("p0Passed")
    if not isinstance(p0_passed, bool):
        errors.append("p0Passed must be a boolean")
        p0_passed = False

    library = require_object(data, "targetLibrary", errors)
    library_name = require_nonempty_string(library.get("name"), "targetLibrary.name", errors)
    require_nonempty_string(library.get("fileKey"), "targetLibrary.fileKey", errors)
    library_key = require_nonempty_string(
        library.get("libraryKey"), "targetLibrary.libraryKey", errors
    )

    metrics: dict[str, dict[str, int]] = {}
    for group, fields in METRIC_FIELDS.items():
        source = require_object(data, group, errors)
        metrics[group] = {
            field: require_count(source, field, group, errors) for field in fields
        }
        covered = (
            metrics[group]["targetDirect"]
            + metrics[group]["targetInherited"]
            + metrics[group]["exceptions"]
        )
        if covered != metrics[group]["totalSpans"]:
            errors.append(
                f"{group} coverage mismatch: direct + inherited + exceptions "
                f"is {covered}, totalSpans is {metrics[group]['totalSpans']}"
            )

    for field in (
        "verificationPending",
        "linkRegressed",
        "otherStyle",
        "unmapped",
        "unclassified",
        "unresolvedUnlinked",
    ):
        value = metrics["typography"].get(field, 0)
        if value:
            blockers.append(f"typography.{field}={value}")

    for field in ("otherStyle", "exactUnlinked", "unclassified", "unresolvedUnlinked"):
        value = metrics["color"].get(field, 0)
        if value:
            blockers.append(f"color.{field}={value}")

    expected_p0 = not blockers and not any("coverage mismatch" in e for e in errors)
    if p0_passed != expected_p0:
        errors.append(
            f"p0Passed is {p0_passed}, but blocking metrics imply {expected_p0}"
        )

    mutations = require_object(data, "mutations", errors)
    mutation_counts = {
        field: require_count(mutations, field, "mutations", errors)
        for field in MUTATION_FIELDS
    }
    if not p0_passed and any(mutation_counts.values()):
        scoped = data.get("scopedContinuation", {})
        if not isinstance(scoped, dict):
            errors.append("scopedContinuation must be an object")
            scoped = {}
        if scoped.get("mode") != "independent-candidates" or data.get("status") != "incomplete":
            errors.append("component mutations with incomplete P0 require scopedContinuation and incomplete status")
        blocked = scoped.get("blockedNodeIds")
        if not isinstance(blocked, list) or not blocked or any(not isinstance(x, str) or not x for x in blocked):
            errors.append("scopedContinuation.blockedNodeIds must enumerate blocked nodes")
            blocked = []
        receipts = scoped.get("candidateReceipts")
        if not isinstance(receipts, list) or not receipts:
            errors.append("scopedContinuation.candidateReceipts required")
            receipts = []
        totals = {key: 0 for key in MUTATION_FIELDS}
        for i, receipt in enumerate(receipts):
            prefix = f"scopedContinuation.candidateReceipts[{i}]"
            if not isinstance(receipt, dict):
                errors.append(f"{prefix} must be an object")
                continue
            for key in ["candidateId", "evidencePath"]:
                require_nonempty_string(receipt.get(key), f"{prefix}.{key}", errors)
            affected = receipt.get("affectedNodeIds")
            if not isinstance(affected, list) or not affected or any(not isinstance(x, str) or not x for x in affected):
                errors.append(f"{prefix}.affectedNodeIds required")
            elif set(affected) & set(blocked):
                errors.append(f"{prefix} intersects blocked nodes")
            for key in ["dependencyCheckPassed", "propertiesPassed", "lineagePassed", "visualPassed", "rollbackReady"]:
                if receipt.get(key) is not True:
                    errors.append(f"{prefix}.{key} must be true")
            for key in MUTATION_FIELDS:
                totals[key] += require_count(receipt, key, prefix, errors)
        if totals != mutation_counts:
            errors.append("scopedContinuation mutation totals must equal mutations")

    sources = data.get("assetSources")
    if not isinstance(sources, list):
        errors.append("assetSources must be an array")
        sources = []

    target_text_usage = 0
    target_paint_usage = 0
    local_component_records = 0
    local_instance_usage = 0

    for index, item in enumerate(sources):
        prefix = f"assetSources[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue

        asset_type = item.get("assetType")
        source_type = item.get("sourceType")
        if asset_type not in ASSET_TYPES:
            errors.append(f"{prefix}.assetType is invalid")
        if source_type not in SOURCE_TYPES:
            errors.append(f"{prefix}.sourceType is invalid")

        asset_name = require_nonempty_string(item.get("assetName"), f"{prefix}.assetName", errors)
        require_nonempty_string(item.get("assetKey"), f"{prefix}.assetKey", errors)
        usage = require_count(item, "usageCount", prefix, errors)
        node_ids = item.get("nodeIds")
        if not isinstance(node_ids, list) or (usage > 0 and not node_ids):
            errors.append(f"{prefix}.nodeIds must be a non-empty array when usageCount > 0")
        elif any(not isinstance(node_id, str) or not node_id for node_id in node_ids):
            errors.append(f"{prefix}.nodeIds must contain non-empty strings")

        remote = item.get("remote")
        if not isinstance(remote, bool):
            errors.append(f"{prefix}.remote must be a boolean")

        if source_type == "target-library":
            if item.get("libraryName") != library_name:
                errors.append(f"{prefix}.libraryName does not match targetLibrary.name")
            if item.get("libraryKey") != library_key:
                errors.append(f"{prefix}.libraryKey does not match targetLibrary.libraryKey")
            if remote is not True:
                errors.append(f"{prefix}.remote must be true for target-library assets")
            if asset_type == "TEXT_STYLE":
                target_text_usage += usage
            elif asset_type == "PAINT_STYLE":
                target_paint_usage += usage

        if source_type == "local-copy":
            if asset_type not in {"COMPONENT", "COMPONENT_SET"}:
                errors.append(f"{prefix}: local-copy is only allowed for components")
            if item.get("libraryName") is not None or item.get("libraryKey") is not None:
                errors.append(f"{prefix}: local-copy library fields must be null")
            if remote is not False:
                errors.append(f"{prefix}.remote must be false for local-copy assets")
            if not asset_name.startswith("本页局部/"):
                errors.append(f"{prefix}.assetName must start with '本页局部/'")
            description = item.get("description")
            if not isinstance(description, str) or "不属于发布库" not in description:
                errors.append(f"{prefix}.description must contain '不属于发布库'")
            if asset_type in {"COMPONENT", "COMPONENT_SET"}:
                local_component_records += 1
                local_instance_usage += usage

    expected_text_usage = (
        metrics["typography"]["targetDirect"]
        + metrics["typography"]["targetInherited"]
    )
    expected_paint_usage = (
        metrics["color"]["targetDirect"] + metrics["color"]["targetInherited"]
    )
    if target_text_usage != expected_text_usage:
        errors.append(
            f"target-library TEXT_STYLE usageCount sum is {target_text_usage}, "
            f"expected {expected_text_usage}"
        )
    if target_paint_usage != expected_paint_usage:
        errors.append(
            f"target-library PAINT_STYLE usageCount sum is {target_paint_usage}, "
            f"expected {expected_paint_usage}"
        )

    created_assets = (
        mutation_counts["createdLocalComponents"] + mutation_counts["createdComponentSets"]
    )
    if local_component_records < created_assets:
        errors.append(
            f"local-copy component source records are {local_component_records}, "
            f"but {created_assets} local component assets were created"
        )
    if local_instance_usage < mutation_counts["replacedWithLocalInstances"]:
        errors.append(
            f"local-copy component usageCount sum is {local_instance_usage}, "
            f"below replacedWithLocalInstances={mutation_counts['replacedWithLocalInstances']}"
        )

    scope_blockers: list[str] = []
    validate_scope(data, errors, scope_blockers)
    blockers.extend(scope_blockers)
    if status == "complete" and scope_blockers:
        errors.append("status is complete while scope completion blockers remain")

    if status == "complete" and not p0_passed:
        errors.append("status cannot be complete while p0Passed is false")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)

    if status == "incomplete":
        if blockers:
            print("VALID INCOMPLETE: " + ", ".join(blockers))
        else:
            print("VALID INCOMPLETE: P0 passed; another declared completion condition remains")
        raise SystemExit(2)

    return "VALID COMPLETE", blockers


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: validate_final_audit.py /absolute/path/to/final-audit.json")
    result, _ = validate(Path(sys.argv[1]).expanduser())
    print(result)


if __name__ == "__main__":
    main()
