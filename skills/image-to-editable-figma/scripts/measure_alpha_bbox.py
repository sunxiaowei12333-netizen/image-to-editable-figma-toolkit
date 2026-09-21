#!/usr/bin/env python3
"""Measure visible alpha bounds and optionally solve CSS placement for a target box."""

from __future__ import annotations

import argparse
import json
import hashlib
import math
from pathlib import Path

from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure a transparent image's alpha-visible bounding box."
    )
    parser.add_argument("image", type=Path, help="PNG/WebP image path")
    parser.add_argument("--plan", type=Path, help="Frozen delivery-generation-plan.json")
    parser.add_argument("--asset-id", help="Asset in the frozen plan; requires --plan")
    parser.add_argument(
        "--alpha-threshold",
        type=int,
        default=1,
        help="Pixels with alpha >= threshold count as visible (default: 1)",
    )
    parser.add_argument("--target-x", type=float)
    parser.add_argument("--target-y", type=float)
    parser.add_argument("--target-width", type=float)
    parser.add_argument("--target-height", type=float)
    parser.add_argument(
        "--preserve-aspect",
        choices=("width", "height", "contain", "cover"),
        help="Use one uniform scale instead of independent x/y scales",
    )
    return parser.parse_args()


def solve_scale(width_scale: float, height_scale: float, mode: str | None) -> tuple[float, float]:
    if mode is None:
        return width_scale, height_scale
    if mode == "width":
        return width_scale, width_scale
    if mode == "height":
        return height_scale, height_scale
    if mode == "contain":
        scale = min(width_scale, height_scale)
        return scale, scale
    scale = max(width_scale, height_scale)
    return scale, scale


def main() -> None:
    args = parse_args()
    frozen = None
    if bool(args.plan) != bool(args.asset_id):
        raise SystemExit("--plan and --asset-id must be supplied together")
    if args.plan:
        if any(v is not None for v in (args.target_x, args.target_y, args.target_width, args.target_height, args.preserve_aspect)):
            raise SystemExit("Frozen plan targets and lock axis cannot be overridden")
        payload = args.plan.read_bytes()
        matches = [a for a in json.loads(payload)["assets"] if a["assetId"] == args.asset_id]
        if len(matches) != 1:
            raise SystemExit("Frozen plan must contain exactly one matching asset")
        asset = matches[0]
        target = asset["referenceBounds"]
        values = [target[k] for k in ("x", "y", "width", "height")]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            raise SystemExit("Frozen bounds must be finite numbers")
        args.target_x, args.target_y, args.target_width, args.target_height = values
        args.preserve_aspect = asset["geometryPolicy"]["lockAxis"]
        if args.preserve_aspect not in ("width", "height"):
            raise SystemExit("Frozen lock axis must be width or height")
        frozen = {"path": str(args.plan.resolve()), "sha256": hashlib.sha256(payload).hexdigest(),
                  "assetId": args.asset_id, "referenceBounds": target}
    if not 1 <= args.alpha_threshold <= 255:
        raise SystemExit("--alpha-threshold must be between 1 and 255")

    with Image.open(args.image) as source:
        image = source.convert("RGBA")
        alpha = image.getchannel("A")
        mask = alpha.point(lambda value: 255 if value >= args.alpha_threshold else 0)
        bbox = mask.getbbox()
        if bbox is None:
            raise SystemExit("Image contains no visible pixels at this alpha threshold")

        source_width, source_height = image.size
        left, top, right, bottom = bbox
        visible_width = right - left
        visible_height = bottom - top

    result: dict[str, object] = {
        "image": str(args.image.resolve()),
        "source_size": {"width": source_width, "height": source_height},
        "alpha_threshold": args.alpha_threshold,
        "alpha_bbox": {"left": left, "top": top, "right": right, "bottom": bottom},
        "visible_size": {"width": visible_width, "height": visible_height},
        "transparent_padding": {
            "left": left,
            "top": top,
            "right": source_width - right,
            "bottom": source_height - bottom,
        },
        "visible_fraction": {
            "width": visible_width / source_width,
            "height": visible_height / source_height,
        },
    }
    if frozen:
        result["frozen_plan"] = frozen
        result["image_sha256"] = hashlib.sha256(args.image.read_bytes()).hexdigest()

    target_values = (args.target_x, args.target_y, args.target_width, args.target_height)
    supplied_target_values = [value is not None for value in target_values]
    if any(supplied_target_values) and not all(supplied_target_values):
        raise SystemExit(
            "Provide --target-x, --target-y, --target-width and --target-height together"
        )
    if all(supplied_target_values):
        assert args.target_x is not None
        assert args.target_y is not None
        assert args.target_width is not None
        assert args.target_height is not None
        if args.target_width <= 0 or args.target_height <= 0:
            raise SystemExit("Target width and height must be positive")

        width_scale = args.target_width / visible_width
        height_scale = args.target_height / visible_height
        scale_x, scale_y = solve_scale(width_scale, height_scale, args.preserve_aspect)
        result["css_solution"] = {
            "left": args.target_x - left * scale_x,
            "top": args.target_y - top * scale_y,
            "width": source_width * scale_x,
            "height": source_height * scale_y,
            "scale_x": scale_x,
            "scale_y": scale_y,
            "preserve_aspect": args.preserve_aspect,
            "predicted_visible_bbox": {
                "left": args.target_x,
                "top": args.target_y,
                "width": visible_width * scale_x,
                "height": visible_height * scale_y,
            },
        }
        actual_width, actual_height = visible_width * scale_x, visible_height * scale_y
        delta_width, delta_height = actual_width - args.target_width, actual_height - args.target_height
        percentage = max(abs(delta_width / args.target_width), abs(delta_height / args.target_height)) * 100
        max_delta = max(abs(delta_width), abs(delta_height))
        result["target_comparison"] = {
            "width_delta_px": delta_width, "height_delta_px": delta_height,
            "max_absolute_delta_px": max_delta, "max_size_delta_percent": percentage,
            "source_aspect_delta_percent": (visible_width / visible_height / (args.target_width / args.target_height) - 1) * 100,
            "nonuniform_scaling": not math.isclose(scale_x, scale_y),
            "effective_resolution_scale": min(visible_width / actual_width, visible_height / actual_height),
            "needs_visual_attention": max_delta > 4 or percentage > 3,
            "visual_status": "pending",
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
