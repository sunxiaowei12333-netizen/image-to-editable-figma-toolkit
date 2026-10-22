#!/usr/bin/env python3
"""Validate the standalone third-stage component audit.

Exit codes:
0: valid and complete
1: malformed or internally contradictory audit
2: valid audit that is still incomplete
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from audit_scope import validate_scope
from verify_component_evidence import validate as validate_evidence


def fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"audit file not found: {path}")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"cannot read audit JSON: {exc}")
    if not isinstance(data, dict):
        fail("audit root must be an object")
    return data


def require_object(parent: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} must be an object")
        return {}
    return value


def require_nonnegative_int(
    parent: dict[str, Any], key: str, prefix: str, errors: list[str]
) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"{prefix}.{key} must be a non-negative integer")
        return 0
    return value


def require_bool(
    parent: dict[str, Any], key: str, prefix: str, errors: list[str]
) -> bool:
    value = parent.get(key)
    if not isinstance(value, bool):
        errors.append(f"{prefix}.{key} must be a boolean")
        return False
    return value


def require_id_list(
    parent: dict[str, Any], key: str, prefix: str, errors: list[str]
) -> list[str]:
    value = parent.get(key)
    if not isinstance(value, list) or not value:
        errors.append(f"{prefix}.{key} must be a non-empty array")
        return []
    if any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{prefix}.{key} must contain non-empty strings")
        return []
    if len(value) != len(set(value)):
        errors.append(f"{prefix}.{key} must contain unique IDs")
    return value


def validate_asset_sources(
    assets: Any,
    created_local_assets: int,
    errors: list[str],
) -> None:
    if not isinstance(assets, list):
        errors.append("assetSources must be an array")
        return

    local_records = 0
    for index, asset in enumerate(assets):
        prefix = f"assetSources[{index}]"
        if not isinstance(asset, dict):
            errors.append(f"{prefix} must be an object")
            continue

        asset_type = asset.get("assetType")
        source_type = asset.get("sourceType")
        if asset_type not in {"COMPONENT", "COMPONENT_SET"}:
            errors.append(f"{prefix}.assetType must be COMPONENT or COMPONENT_SET")
        if source_type not in {"target-library", "local-copy"}:
            errors.append(f"{prefix}.sourceType must be target-library or local-copy")

        name = asset.get("assetName")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.assetName must be a non-empty string")

        usage_count = asset.get("usageCount")
        if isinstance(usage_count, bool) or not isinstance(usage_count, int) or usage_count < 0:
            errors.append(f"{prefix}.usageCount must be a non-negative integer")

        node_ids = asset.get("nodeIds")
        if not isinstance(node_ids, list) or not node_ids or any(
            not isinstance(item, str) or not item.strip() for item in node_ids
        ):
            errors.append(f"{prefix}.nodeIds must contain at least one node id")

        if source_type == "target-library":
            for key in ("libraryName", "libraryKey", "assetKey"):
                if not isinstance(asset.get(key), str) or not asset[key].strip():
                    errors.append(f"{prefix}.{key} must be non-empty for target-library")
            if asset.get("remote") is not True:
                errors.append(f"{prefix}.remote must be true for target-library")

        if source_type == "local-copy":
            local_records += 1
            for key in ("libraryName", "libraryKey", "assetKey"):
                if asset.get(key) is not None:
                    errors.append(f"{prefix}.{key} must be null for local-copy")
            if asset.get("remote") is not False:
                errors.append(f"{prefix}.remote must be false for local-copy")
            if not isinstance(name, str) or not name.startswith("本页局部/"):
                errors.append(f"{prefix}.assetName must start with 本页局部/")
            description = asset.get("description")
            if not isinstance(description, str) or "不属于发布库" not in description:
                errors.append(f"{prefix}.description must contain 不属于发布库")

    if local_records < created_local_assets:
        errors.append(
            "assetSources has fewer local-copy records than created local components and sets"
        )


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: validate_component_audit.py /absolute/path/to/component-audit.json")

    audit_path = Path(sys.argv[1])
    data = read_json(audit_path)
    errors: list[str] = []
    blockers: list[str] = []

    if data.get("schemaVersion") != 2:
        errors.append("schemaVersion=2 and actual evidence are required; legacy audit is not a new pass")
    if not isinstance(data.get("scope"), dict):
        errors.append("v2 requires an explicit processing scope")
    edit_mode = data.get("editMode", "safe-copy")
    if edit_mode not in {"in-place", "safe-copy"}:
        errors.append("editMode must be in-place or safe-copy")
    if edit_mode == "in-place":
        protection = require_object(data, "targetProtection", errors)
        target_ids = require_id_list(protection, "targetNodeIds", "targetProtection", errors)
        for key in ("scopeRespected", "sharedDependenciesUnchanged", "canvasBoundaryPassed"):
            if not require_bool(protection, key, "targetProtection", errors):
                blockers.append(f"targetProtection.{key} is false")
    else:
        protection = require_object(data, "sourceProtection", errors)
        source_ids = require_id_list(protection, "sourceNodeIds", "sourceProtection", errors)
        target_ids = require_id_list(protection, "copyNodeIds", "sourceProtection", errors)
        if source_ids and target_ids and len(source_ids) != len(target_ids):
            errors.append("sourceProtection source/copy node counts must match")
        for key in ("mappingComplete", "sourceUnchanged", "canvasBoundaryPassed"):
            if not require_bool(protection, key, "sourceProtection", errors):
                blockers.append(f"sourceProtection.{key} is false")
    evidence = None
    manifest = data.get("evidenceManifest")
    if not isinstance(manifest, str) or not manifest:
        errors.append("evidenceManifest is required")
    else:
        evidence = validate_evidence(audit_path.parent / manifest)
        errors.extend("evidence: " + e for e in evidence["errors"])
        blockers.extend("evidence: " + b for b in evidence["blockers"])
        if not evidence["errors"]:
            if evidence["editMode"] != edit_mode:
                errors.append("editMode differs from evidence")
            coverage = data.get("candidateCoverage", {})
            if not isinstance(coverage, dict) or any(
                coverage.get(k) != v for k, v in evidence["candidateCoverage"].items()
            ):
                errors.append("candidateCoverage differs from evidence-derived counts")
            for audit_key, evidence_key in (
                ("affectedBeforeNodeIds", "affectedBeforeIds"),
                ("affectedAfterNodeIds", "affectedAfterIds"),
            ):
                value = data.get(audit_key)
                if (not isinstance(value, list) or any(not isinstance(v, str) for v in value)
                        or len(value) != len(set(value)) or set(value) != set(evidence[evidence_key])):
                    errors.append(f"{audit_key} differs from mapped snapshot scope")
            visual = data.get("visualValidation", {})
            if visual.get("acceptedMinorTextDifferences", 0) != evidence["acceptedMinorTextDifferences"]:
                errors.append("acceptedMinorTextDifferences differs from actual image evidence")
            expected_sources = {r["sourceId"] for r in evidence["rootMappings"]}
            expected_copies = {r["copyId"] for r in evidence["rootMappings"]}
            if set(target_ids) != expected_copies:
                errors.append("target scope differs from evidence root mappings")
            if edit_mode == "safe-copy" and set(source_ids) != expected_sources:
                errors.append("source scope differs from evidence root mappings")
            scope = data.get("scope")
            if isinstance(scope, dict):
                processing_ids = scope.get("processingRootIds")
                if (not isinstance(processing_ids, list)
                    or any(not isinstance(v, str) for v in processing_ids)
                    or set(processing_ids) != expected_copies):
                    errors.append("scope.processingRootIds differs from evidence target roots")
            if visual.get("rootsCompared") != len(expected_copies):
                errors.append("visualValidation.rootsCompared differs from evidence")

    validate_scope(data, errors, blockers)

    status = data.get("status")
    if status not in {"complete", "incomplete"}:
        errors.append("status must be complete or incomplete")
    if data.get("mode") != "third-stage-only":
        errors.append("mode must be third-stage-only")

    candidates = require_object(data, "candidateCoverage", errors)
    candidate_values = {
        key: require_nonnegative_int(candidates, key, "candidateCoverage", errors)
        for key in (
            "total",
            "componentized",
            "alreadyComponentized",
            "skippedWithReason",
            "unclassified",
        )
    }
    classified_total = (
        candidate_values["componentized"]
        + candidate_values["alreadyComponentized"]
        + candidate_values["skippedWithReason"]
        + candidate_values["unclassified"]
    )
    if classified_total != candidate_values["total"]:
        errors.append("candidateCoverage classified counts must equal total")
    if candidate_values["unclassified"] != 0:
        blockers.append("candidateCoverage.unclassified is not zero")

    mutations = require_object(data, "mutations", errors)
    mutation_values = {
        key: require_nonnegative_int(mutations, key, "mutations", errors)
        for key in (
            "createdLocalComponents",
            "createdComponentSets",
            "replacedWithLocalInstances",
        )
    }

    preservation = require_object(data, "stylePreservation", errors)
    preservation_values = {
        key: require_nonnegative_int(preservation, key, "stylePreservation", errors)
        for key in (
            "affectedTextSpans",
            "unchanged",
            "intentionalOverrides",
            "unexpectedChanges",
            "missingBeforeAfterEvidence",
        )
    }
    preserved_total = (
        preservation_values["unchanged"] + preservation_values["intentionalOverrides"]
    )
    if preserved_total != preservation_values["affectedTextSpans"]:
        errors.append("stylePreservation unchanged + intentionalOverrides must equal affectedTextSpans")
    for key in ("unexpectedChanges", "missingBeforeAfterEvidence"):
        if preservation_values[key] != 0:
            blockers.append(f"stylePreservation.{key} is not zero")

    lineage = require_object(data, "lineage", errors)
    lineage_values = {
        key: require_nonnegative_int(lineage, key, "lineage", errors)
        for key in (
            "instancesChecked",
            "missingMainComponent",
            "orphanLocalInstances",
            "wrongMainComponent",
            "temporaryNodes",
        )
    }
    for key in (
        "missingMainComponent",
        "orphanLocalInstances",
        "wrongMainComponent",
        "temporaryNodes",
    ):
        if lineage_values[key] != 0:
            blockers.append(f"lineage.{key} is not zero")

    visual = require_object(data, "visualValidation", errors)
    visual_values = {
        key: require_nonnegative_int(visual, key, "visualValidation", errors)
        for key in ("rootsCompared", "unexpectedPixelDifferences", "geometryRegressions")
    }
    if visual_values["rootsCompared"] == 0:
        blockers.append("visualValidation.rootsCompared is zero")
    for key in ("unexpectedPixelDifferences", "geometryRegressions"):
        if visual_values[key] != 0:
            blockers.append(f"visualValidation.{key} is not zero")

    created_local_assets = (
        mutation_values["createdLocalComponents"] + mutation_values["createdComponentSets"]
    )
    validate_asset_sources(data.get("assetSources"), created_local_assets, errors)

    if status == "complete" and blockers:
        errors.append("status is complete while completion blockers remain")

    if errors:
        for item in errors:
            print(f"ERROR: {item}", file=sys.stderr)
        raise SystemExit(1)

    if status == "incomplete" or blockers:
        for item in blockers or ["audit is explicitly marked incomplete"]:
            print(f"BLOCKER: {item}", file=sys.stderr)
        raise SystemExit(2)

    print("component audit valid: third-stage-only is complete")


if __name__ == "__main__":
    main()
