#!/usr/bin/env python3
"""Validate that normalized Figma copies preserve the source root boundaries."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    print(f"INVALID: {message}", file=sys.stderr)
    raise SystemExit(1)


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


def require_object(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return {}
    return value


def require_node_id(value: Any, path: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} must be a non-empty string")
        return ""
    return value


def require_dimension(value: Any, path: str, errors: list[str]) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{path} must be a number")
        return 0.0
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        errors.append(f"{path} must be finite and greater than 0")
        return 0.0
    return result


def require_clip(value: Any, path: str, errors: list[str]) -> bool | None:
    if value is not None and not isinstance(value, bool):
        errors.append(f"{path} must be a boolean or null")
        return None
    return value


def require_overflow(value: Any, path: str, errors: list[str]) -> str | None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        errors.append(f"{path} must be a non-empty string or null")
        return None
    return value


def close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=0.0, abs_tol=0.01)


def validate(path: Path) -> None:
    data = load(path)
    targets = data.get("targets")
    if not isinstance(targets, list) or not targets:
        fail("targets must be a non-empty array")

    errors: list[str] = []
    mode = data.get("mode", "source-copy")
    if mode not in {"source-copy", "before-after"}:
        errors.append("mode must be source-copy or before-after")
    for index, item in enumerate(targets):
        prefix = f"targets[{index}]"
        row = require_object(item, prefix, errors)
        source = require_object(row.get("source"), f"{prefix}.source", errors)
        copy = require_object(row.get("copy"), f"{prefix}.copy", errors)
        source_shot = require_object(
            row.get("sourceScreenshot"), f"{prefix}.sourceScreenshot", errors
        )
        copy_shot = require_object(
            row.get("copyScreenshot"), f"{prefix}.copyScreenshot", errors
        )

        source_id = require_node_id(source.get("nodeId"), f"{prefix}.source.nodeId", errors)
        copy_id = require_node_id(copy.get("nodeId"), f"{prefix}.copy.nodeId", errors)
        source_width = require_dimension(source.get("width"), f"{prefix}.source.width", errors)
        source_height = require_dimension(source.get("height"), f"{prefix}.source.height", errors)
        copy_width = require_dimension(copy.get("width"), f"{prefix}.copy.width", errors)
        copy_height = require_dimension(copy.get("height"), f"{prefix}.copy.height", errors)
        source_clip = require_clip(
            source.get("clipsContent"), f"{prefix}.source.clipsContent", errors
        )
        copy_clip = require_clip(copy.get("clipsContent"), f"{prefix}.copy.clipsContent", errors)
        source_overflow = require_overflow(
            source.get("overflowDirection"), f"{prefix}.source.overflowDirection", errors
        )
        copy_overflow = require_overflow(
            copy.get("overflowDirection"), f"{prefix}.copy.overflowDirection", errors
        )

        source_shot_width = require_dimension(
            source_shot.get("originalWidth"), f"{prefix}.sourceScreenshot.originalWidth", errors
        )
        source_shot_height = require_dimension(
            source_shot.get("originalHeight"), f"{prefix}.sourceScreenshot.originalHeight", errors
        )
        copy_shot_width = require_dimension(
            copy_shot.get("originalWidth"), f"{prefix}.copyScreenshot.originalWidth", errors
        )
        copy_shot_height = require_dimension(
            copy_shot.get("originalHeight"), f"{prefix}.copyScreenshot.originalHeight", errors
        )

        if mode == "before-after":
            if source_id != copy_id:
                errors.append(f"{prefix}: before-after requires the same target nodeId")
            baseline = row.get("baselineId")
            if not isinstance(baseline, str) or not baseline.strip():
                errors.append(f"{prefix}: baselineId required for before-after")
            before_time, after_time = source.get("capturedAt"), copy.get("capturedAt")
            valid_times = all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) for t in [before_time, after_time])
            if not valid_times or after_time <= before_time:
                errors.append(f"{prefix}: capturedAt must be finite increasing timestamps")
        elif source_id == copy_id and source_id:
            errors.append(f"{prefix}: source and copy nodeId must differ")
        if not close(source_width, copy_width) or not close(source_height, copy_height):
            errors.append(
                f"{prefix}: root size mismatch source={source_width:g}x{source_height:g} "
                f"copy={copy_width:g}x{copy_height:g}"
            )
        if source_clip != copy_clip:
            errors.append(
                f"{prefix}: clipsContent mismatch source={source_clip} copy={copy_clip}"
            )
        if source_overflow != copy_overflow:
            errors.append(
                f"{prefix}: overflowDirection mismatch "
                f"source={source_overflow!r} copy={copy_overflow!r}"
            )
        if not close(source_shot_width, copy_shot_width) or not close(
            source_shot_height, copy_shot_height
        ):
            errors.append(
                f"{prefix}: screenshot original size mismatch "
                f"source={source_shot_width:g}x{source_shot_height:g} "
                f"copy={copy_shot_width:g}x{copy_shot_height:g}"
            )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)

    print(f"VALID CANVAS BOUNDARY: {len(targets)} target(s); mode={mode}")


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: validate_canvas_boundary.py /absolute/path/to/boundary.json")
    validate(Path(sys.argv[1]).expanduser())


if __name__ == "__main__":
    main()
