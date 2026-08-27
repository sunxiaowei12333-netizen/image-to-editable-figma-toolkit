#!/usr/bin/env python3
"""Convert a deliberately planned solid color key into a reviewed RGBA PNG."""

from __future__ import annotations

import argparse
from collections import deque
import json
import math
from pathlib import Path
from statistics import median

from PIL import Image, ImageDraw


MAX_RGB_DISTANCE = math.sqrt(3 * 255 * 255)
DEFAULT_SEED_TOLERANCE = 18.0
DEFAULT_GROW_TOLERANCE = 72.0
BOUNDARY_VISIBLE_ALPHA_THRESHOLD = 16


def parse_hex_color(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(character * 2 for character in text)
    if len(text) != 6:
        raise argparse.ArgumentTypeError("Color must use #RGB or #RRGGBB")
    try:
        return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError as error:
        raise argparse.ArgumentTypeError("Color must use hexadecimal digits") from error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract a real alpha channel from an intentionally planned, solid color-key "
            "background using boundary-connected segmentation."
        )
    )
    parser.add_argument("input", type=Path, help="Color-key input image")
    parser.add_argument("output", type=Path, help="New RGBA PNG output path")
    parser.add_argument("--key", required=True, type=parse_hex_color, help="Planned key color")
    parser.add_argument(
        "--seed-tolerance",
        type=float,
        default=DEFAULT_SEED_TOLERANCE,
        help="Maximum RGB distance for strong border seeds (default: 18)",
    )
    parser.add_argument(
        "--grow-tolerance",
        type=float,
        default=DEFAULT_GROW_TOLERANCE,
        help="Maximum RGB distance for boundary-connected growth (default: 72)",
    )
    parser.add_argument(
        "--generated-key-input",
        action="store_true",
        help=(
            "Audit an AI-generated planned key with the default tolerances. A uniformly "
            "shifted outer border may be recentered without widening tolerances; gradients, "
            "multiple border colors, or larger overrides are rejected."
        ),
    )
    parser.add_argument(
        "--allow-subject-touch-edge",
        "--allow-touch-edge",
        action="append",
        default=[],
        choices=("top", "right", "bottom", "left"),
        help=(
            "Declare an intentional subject crop/touch edge in a generated key image; "
            "repeat for multiple edges"
        ),
    )
    parser.add_argument(
        "--connectivity",
        type=int,
        choices=(4, 8),
        default=8,
        help="Flood-fill connectivity (default: 8)",
    )
    parser.add_argument(
        "--include-enclosed-key-regions",
        action="store_true",
        help="Also remove enclosed key-like components; use only after every candidate is reviewed",
    )
    parser.add_argument(
        "--minimum-enclosed-area",
        type=int,
        default=4,
        help="Minimum pixel area reported as an enclosed key candidate (default: 4)",
    )
    decontamination = parser.add_mutually_exclusive_group()
    decontamination.add_argument(
        "--decontaminate-edges",
        dest="decontaminate_edges",
        action="store_true",
        default=True,
        help="Reverse-composite semi-transparent edge RGB away from the key (default)",
    )
    decontamination.add_argument(
        "--no-decontaminate-edges",
        dest="decontaminate_edges",
        action="store_false",
        help="Leave semi-transparent edge RGB unchanged",
    )
    parser.add_argument("--qa-dir", type=Path, help="Write mask and dark/light/checker previews")
    parser.add_argument("--report", type=Path, help="JSON report path (default: output.report.json)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output/report files")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if not 0 <= args.seed_tolerance < args.grow_tolerance <= MAX_RGB_DISTANCE:
        raise SystemExit(
            f"Require 0 <= seed tolerance < grow tolerance <= {MAX_RGB_DISTANCE:.2f}"
        )
    if args.minimum_enclosed_area < 1:
        raise SystemExit("--minimum-enclosed-area must be positive")
    if args.generated_key_input and (
        args.seed_tolerance != DEFAULT_SEED_TOLERANCE
        or args.grow_tolerance != DEFAULT_GROW_TOLERANCE
    ):
        raise SystemExit(
            "--generated-key-input requires the default seed/grow tolerances; "
            "do not widen thresholds to rescue an impure generated key"
        )
    if args.output.suffix.lower() != ".png":
        raise SystemExit("Output must use .png so the alpha channel is preserved")
    input_path = args.input.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    if input_path == output_path:
        raise SystemExit("Input and output must be different files")
    report_path = (
        args.report.expanduser().resolve()
        if args.report
        else output_path.with_suffix(".report.json")
    )
    existing = [path for path in (output_path, report_path) if path.exists()]
    if existing and not args.force:
        raise SystemExit(
            "Refusing to overwrite existing output: " + ", ".join(str(path) for path in existing)
        )


def rgb_distance(pixel: tuple[int, int, int, int], key: tuple[int, int, int]) -> float:
    return math.sqrt(sum((pixel[index] - key[index]) ** 2 for index in range(3)))


def format_hex(color: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*color)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("Cannot calculate a percentile of an empty sequence")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def outer_edge_pixels(
    image: Image.Image,
) -> dict[str, list[tuple[int, int, int, int]]]:
    width, height = image.size
    pixels = image.load()
    assert pixels is not None
    return {
        "top": [pixels[x, 0] for x in range(width)],
        "right": [pixels[width - 1, y] for y in range(height)],
        "bottom": [pixels[x, height - 1] for x in range(width)],
        "left": [pixels[0, y] for y in range(height)],
    }


def median_rgb(pixels: list[tuple[int, int, int, int]]) -> tuple[int, int, int]:
    return tuple(
        int(round(median(pixel[channel] for pixel in pixels))) for channel in range(3)
    )  # type: ignore[return-value]


def distance_summary(
    pixels: list[tuple[int, int, int, int]],
    key: tuple[int, int, int],
    seed_tolerance: float,
) -> dict[str, object]:
    distances = [rgb_distance(pixel, key) for pixel in pixels]
    within_seed = sum(distance <= seed_tolerance for distance in distances)
    return {
        "pixels": len(pixels),
        "within_seed_pixels": within_seed,
        "within_seed_ratio": round(within_seed / len(pixels), 6),
        "distance": {
            "minimum": round(min(distances), 4),
            "p50": round(percentile(distances, 0.50), 4),
            "p95": round(percentile(distances, 0.95), 4),
            "p99": round(percentile(distances, 0.99), 4),
            "maximum": round(max(distances), 4),
        },
    }


class GeneratedKeyAuditError(Exception):
    def __init__(self, message: str, audit: dict[str, object]) -> None:
        super().__init__(message)
        self.audit = audit


def audit_key_source(
    image: Image.Image,
    planned_key: tuple[int, int, int],
    seed_tolerance: float,
    grow_tolerance: float,
    generated_key_input: bool,
) -> tuple[tuple[int, int, int], dict[str, object]]:
    edges = outer_edge_pixels(image)
    all_edge_pixels = [pixel for edge in edges.values() for pixel in edge]
    observed_key = median_rgb(all_edge_pixels)
    planned_edges = {
        name: distance_summary(pixels, planned_key, seed_tolerance)
        for name, pixels in edges.items()
    }
    observed_edges = {
        name: distance_summary(pixels, observed_key, seed_tolerance)
        for name, pixels in edges.items()
    }
    planned_uniform = all(
        float(summary["distance"]["p95"]) <= seed_tolerance  # type: ignore[index]
        for summary in planned_edges.values()
    )
    observed_uniform = all(
        float(summary["distance"]["p95"]) <= seed_tolerance  # type: ignore[index]
        for summary in observed_edges.values()
    )
    planned_to_observed = math.sqrt(
        sum((planned_key[index] - observed_key[index]) ** 2 for index in range(3))
    )

    selection_mode = "planned-key"
    effective_key = planned_key
    if generated_key_input and not planned_uniform:
        if observed_uniform and planned_to_observed <= grow_tolerance:
            selection_mode = "uniform-border-recenter"
            effective_key = observed_key
        else:
            selection_mode = "rejected"

    effective_edges = {
        name: distance_summary(pixels, effective_key, seed_tolerance)
        for name, pixels in edges.items()
    }
    audit: dict[str, object] = {
        "generated_key_input": generated_key_input,
        "selection_mode": selection_mode,
        "planned_key": format_hex(planned_key),
        "observed_outer_border_key": format_hex(observed_key),
        "effective_key": format_hex(effective_key),
        "planned_to_observed_distance": round(planned_to_observed, 4),
        "planned_key_uniform_on_all_edges": planned_uniform,
        "observed_border_uniform_on_all_edges": observed_uniform,
        "per_edge_against_planned_key": planned_edges,
        "per_edge_against_observed_key": observed_edges,
        "per_edge_against_effective_key": effective_edges,
    }
    if generated_key_input and selection_mode == "rejected":
        raise GeneratedKeyAuditError(
            "Generated key background is not a single boundary-touching color compatible "
            "with the planned key; reject or regenerate it instead of widening tolerances",
            audit,
        )
    return effective_key, audit


def neighbor_offsets(connectivity: int) -> tuple[tuple[int, int], ...]:
    if connectivity == 4:
        return ((-1, 0), (1, 0), (0, -1), (0, 1))
    return (
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1),
        (-1, -1),
        (-1, 1),
        (1, -1),
        (1, 1),
    )


def border_indices(width: int, height: int) -> set[int]:
    indices = {x for x in range(width)}
    indices.update((height - 1) * width + x for x in range(width))
    indices.update(y * width for y in range(height))
    indices.update(y * width + width - 1 for y in range(height))
    return indices


def flood_from_border(
    width: int,
    height: int,
    strong: list[bool],
    candidate: list[bool],
    connectivity: int,
) -> tuple[list[bool], int]:
    connected = [False] * (width * height)
    queue: deque[int] = deque()
    seeds = 0
    for index in border_indices(width, height):
        if strong[index]:
            connected[index] = True
            queue.append(index)
            seeds += 1
    if not queue:
        raise SystemExit(
            "No strong key-colored pixels touch the image boundary; this is not a valid planned key input"
        )

    offsets = neighbor_offsets(connectivity)
    while queue:
        index = queue.popleft()
        x = index % width
        y = index // width
        for dx, dy in offsets:
            nx = x + dx
            ny = y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            neighbor = ny * width + nx
            if candidate[neighbor] and not connected[neighbor]:
                connected[neighbor] = True
                queue.append(neighbor)
    return connected, seeds


def enclosed_components(
    width: int,
    height: int,
    candidate: list[bool],
    boundary_connected: list[bool],
    connectivity: int,
    minimum_area: int,
) -> tuple[list[dict[str, object]], list[bool]]:
    visited = boundary_connected.copy()
    included = [False] * (width * height)
    offsets = neighbor_offsets(connectivity)
    components: list[dict[str, object]] = []

    for start in range(width * height):
        if visited[start] or not candidate[start]:
            continue
        queue: deque[int] = deque((start,))
        visited[start] = True
        pixels: list[int] = []
        while queue:
            index = queue.popleft()
            pixels.append(index)
            x = index % width
            y = index // width
            for dx, dy in offsets:
                nx = x + dx
                ny = y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                neighbor = ny * width + nx
                if candidate[neighbor] and not visited[neighbor]:
                    visited[neighbor] = True
                    queue.append(neighbor)

        if len(pixels) < minimum_area:
            continue
        xs = [index % width for index in pixels]
        ys = [index // width for index in pixels]
        components.append(
            {
                "area": len(pixels),
                "bbox": {
                    "left": min(xs),
                    "top": min(ys),
                    "right": max(xs) + 1,
                    "bottom": max(ys) + 1,
                },
            }
        )
        for index in pixels:
            included[index] = True

    components.sort(key=lambda component: int(component["area"]), reverse=True)
    for component_id, component in enumerate(components, start=1):
        component["id"] = component_id
    return components, included


def reverse_composite_channel(composite: int, key: int, alpha: float) -> int:
    if alpha <= 0.0:
        return composite
    value = (composite - (1.0 - alpha) * key) / alpha
    return int(round(max(0.0, min(255.0, value))))


def composite_preview(image: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    background = Image.new("RGBA", image.size, (*color, 255))
    return Image.alpha_composite(background, image).convert("RGB")


def checker_preview(image: Image.Image, tile: int = 16) -> Image.Image:
    width, height = image.size
    checker = Image.new("RGBA", image.size)
    pixels = checker.load()
    assert pixels is not None
    for y in range(height):
        for x in range(width):
            shade = 224 if ((x // tile) + (y // tile)) % 2 == 0 else 176
            pixels[x, y] = (shade, shade, shade, 255)
    return Image.alpha_composite(checker, image).convert("RGB")


def enclosed_candidate_previews(
    image: Image.Image,
    components: list[dict[str, object]],
    qa_dir: Path,
) -> dict[str, str]:
    if not components:
        return {}

    marked = image.convert("RGB")
    marked_draw = ImageDraw.Draw(marked)
    for component in components:
        bbox = component["bbox"]
        assert isinstance(bbox, dict)
        left = int(bbox["left"])
        top = int(bbox["top"])
        right = int(bbox["right"])
        bottom = int(bbox["bottom"])
        component_id = int(component["id"])
        marked_draw.rectangle((left, top, right - 1, bottom - 1), outline=(255, 0, 0), width=3)
        marked_draw.text((left + 3, max(0, top - 12)), str(component_id), fill=(255, 0, 0))
    marked_path = qa_dir / "enclosed-candidates-marked.png"
    marked.save(marked_path)

    panel_width = 280
    panel_height = 220
    columns = min(3, len(components))
    rows = math.ceil(len(components) / columns)
    contact_sheet = Image.new(
        "RGB",
        (panel_width * columns, panel_height * rows),
        (246, 246, 246),
    )
    sheet_draw = ImageDraw.Draw(contact_sheet)
    for index, component in enumerate(components):
        bbox = component["bbox"]
        assert isinstance(bbox, dict)
        left = int(bbox["left"])
        top = int(bbox["top"])
        right = int(bbox["right"])
        bottom = int(bbox["bottom"])
        component_id = int(component["id"])
        padding = max(24, round(max(right - left, bottom - top) * 0.75))
        crop_box = (
            max(0, left - padding),
            max(0, top - padding),
            min(image.width, right + padding),
            min(image.height, bottom + padding),
        )
        crop = image.convert("RGB").crop(crop_box)
        crop.thumbnail((panel_width - 24, panel_height - 54), Image.Resampling.LANCZOS)
        column = index % columns
        row = index // columns
        panel_left = column * panel_width
        panel_top = row * panel_height
        paste_left = panel_left + (panel_width - crop.width) // 2
        paste_top = panel_top + 38 + (panel_height - 50 - crop.height) // 2
        contact_sheet.paste(crop, (paste_left, paste_top))
        sheet_draw.text(
            (panel_left + 10, panel_top + 9),
            (
                f"{component_id}  area={int(component['area'])}  "
                f"bbox={left},{top},{right},{bottom}"
            ),
            fill=(24, 24, 24),
        )
    contact_sheet_path = qa_dir / "enclosed-candidates-contact-sheet.png"
    contact_sheet.save(contact_sheet_path)
    return {
        "enclosed_candidates_marked": str(marked_path),
        "enclosed_candidates_contact_sheet": str(contact_sheet_path),
    }


def main() -> None:
    args = parse_args()
    validate_args(args)

    input_path = args.input.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    report_path = (
        args.report.expanduser().resolve()
        if args.report
        else output_path.with_suffix(".report.json")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(input_path) as source:
        image = source.convert("RGBA")
    width, height = image.size
    if args.generated_key_input:
        try:
            from adaptive_generated_colorkey import (
                AdaptiveKeyError,
                extract_adaptive_generated_key,
            )
        except ImportError as error:
            raise SystemExit(
                "Adaptive generated-key extraction requires Pillow, NumPy, and OpenCV. "
                "Install the Skill requirements with: python3 -m pip install -r requirements.txt"
            ) from error

        try:
            adaptive = extract_adaptive_generated_key(
                image,
                args.key,
                allowed_subject_touch_edges=set(args.allow_subject_touch_edge),
                include_enclosed_key_regions=args.include_enclosed_key_regions,
                minimum_enclosed_area=args.minimum_enclosed_area,
            )
        except AdaptiveKeyError as error:
            rejection_report: dict[str, object] = {
                "status": "rejected",
                "reason": error.reason,
                "message": str(error),
                "input": str(input_path),
                "output": str(output_path),
                "size": {"width": width, "height": height},
                "planned_key": format_hex(args.key),
                "parameters": {
                    "seed_tolerance": args.seed_tolerance,
                    "grow_tolerance": args.grow_tolerance,
                    "connectivity": args.connectivity,
                    "generated_key_input": True,
                    "allowed_subject_touch_edges": sorted(set(args.allow_subject_touch_edge)),
                },
                "key_source_audit": error.audit,
            }
            report_path.write_text(
                json.dumps(rejection_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            raise SystemExit(str(error)) from error

        output = adaptive.image
        output_alpha = output.getchannel("A")
        alpha_values = list(output_alpha.getdata())
        alpha_min, alpha_max = output_alpha.getextrema() or (255, 255)
        if alpha_min == 255:
            raise SystemExit("Extraction produced no non-opaque pixels")
        if alpha_max == 0:
            raise SystemExit("Extraction removed the entire image")
        visible_bbox = output_alpha.point(lambda value: 255 if value > 0 else 0).getbbox()
        boundary_alpha_values = [alpha_values[index] for index in border_indices(width, height)]
        boundary_alpha_maximum = max(boundary_alpha_values)
        visible_touches_boundary = any(
            value > BOUNDARY_VISIBLE_ALPHA_THRESHOLD for value in boundary_alpha_values
        )
        output.save(output_path, format="PNG", optimize=True)
        report: dict[str, object] = {
            "input": str(input_path),
            "output": str(output_path),
            "size": {"width": width, "height": height},
            "planned_key": format_hex(args.key),
            "key": format_hex(args.key),
            "key_source_audit": adaptive.audit,
            "parameters": {
                "seed_tolerance": args.seed_tolerance,
                "grow_tolerance": args.grow_tolerance,
                "connectivity": args.connectivity,
                "generated_key_input": True,
                "allowed_subject_touch_edges": sorted(set(args.allow_subject_touch_edge)),
                "include_enclosed_key_regions": args.include_enclosed_key_regions,
                "decontaminate_edges": True,
            },
            "segmentation": {
                **adaptive.audit["segmentation"],
                "enclosed_key_candidates": adaptive.enclosed_candidates,
                "enclosed_key_candidate_count": len(adaptive.enclosed_candidates),
                "enclosed_key_candidate_pixels": sum(
                    int(component["area"]) for component in adaptive.enclosed_candidates
                ),
            },
            "output_alpha": {
                "minimum": alpha_min,
                "maximum": alpha_max,
                "transparent_pixels": sum(value == 0 for value in alpha_values),
                "semitransparent_pixels": sum(0 < value < 255 for value in alpha_values),
                "opaque_pixels": sum(value == 255 for value in alpha_values),
                "has_nonopaque_pixels": alpha_min < 255,
                "has_visible_pixels": alpha_max > 0,
                "visible_touches_boundary": visible_touches_boundary,
                "allowed_subject_touch_edges": sorted(set(args.allow_subject_touch_edge)),
                "boundary_alpha_maximum": boundary_alpha_maximum,
                "boundary_visible_alpha_threshold": BOUNDARY_VISIBLE_ALPHA_THRESHOLD,
                "visible_bbox": (
                    {
                        "left": visible_bbox[0],
                        "top": visible_bbox[1],
                        "right": visible_bbox[2],
                        "bottom": visible_bbox[3],
                    }
                    if visible_bbox
                    else None
                ),
            },
            "review_required": {
                "enclosed_key_candidates": bool(adaptive.enclosed_candidates),
                "dark_light_edge_review": True,
                "protected_detail_review": True,
                "internal_alpha_island_review": True,
                "final_background_100_200_review": True,
            },
        }
        if args.qa_dir:
            qa_dir = args.qa_dir.expanduser().resolve()
            qa_dir.mkdir(parents=True, exist_ok=True)
            output_alpha.save(qa_dir / "alpha-mask.png")
            composite_preview(output, (24, 24, 24)).save(qa_dir / "composite-dark.png")
            composite_preview(output, (246, 246, 246)).save(qa_dir / "composite-light.png")
            checker_preview(output).save(qa_dir / "composite-checker.png")
            report["qa_dir"] = str(qa_dir)
            report["qa_artifacts"] = enclosed_candidate_previews(
                image, adaptive.enclosed_candidates, qa_dir
            )
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    try:
        effective_key, key_source_audit = audit_key_source(
            image,
            args.key,
            args.seed_tolerance,
            args.grow_tolerance,
            args.generated_key_input,
        )
    except GeneratedKeyAuditError as error:
        rejection_report: dict[str, object] = {
            "status": "rejected",
            "reason": "key-background-impure",
            "message": str(error),
            "input": str(input_path),
            "output": str(output_path),
            "size": {"width": width, "height": height},
            "planned_key": format_hex(args.key),
            "parameters": {
                "seed_tolerance": args.seed_tolerance,
                "grow_tolerance": args.grow_tolerance,
                "connectivity": args.connectivity,
                "generated_key_input": args.generated_key_input,
            },
            "key_source_audit": error.audit,
        }
        report_path.write_text(
            json.dumps(rejection_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raise SystemExit(str(error)) from error

    source_pixels = list(image.getdata())
    distances = [rgb_distance(pixel, effective_key) for pixel in source_pixels]
    strong = [distance <= args.seed_tolerance for distance in distances]
    candidate = [distance <= args.grow_tolerance for distance in distances]
    boundary_connected, border_seed_count = flood_from_border(
        width, height, strong, candidate, args.connectivity
    )
    enclosed, enclosed_pixels = enclosed_components(
        width,
        height,
        candidate,
        boundary_connected,
        args.connectivity,
        args.minimum_enclosed_area,
    )

    removal_region = boundary_connected.copy()
    if args.include_enclosed_key_regions:
        removal_region = [
            boundary or enclosed_pixel
            for boundary, enclosed_pixel in zip(boundary_connected, enclosed_pixels)
        ]

    output_pixels: list[tuple[int, int, int, int]] = []
    decontaminated_pixels = 0
    for pixel, distance, remove in zip(source_pixels, distances, removal_region):
        red, green, blue, source_alpha = pixel
        if not remove:
            output_pixels.append(pixel)
            continue

        matte_alpha = max(
            0.0,
            min(
                1.0,
                (distance - args.seed_tolerance)
                / (args.grow_tolerance - args.seed_tolerance),
            ),
        )
        output_alpha = int(round(source_alpha * matte_alpha))
        if args.decontaminate_edges and 0.08 <= matte_alpha < 1.0 and output_alpha > 0:
            red = reverse_composite_channel(red, effective_key[0], matte_alpha)
            green = reverse_composite_channel(green, effective_key[1], matte_alpha)
            blue = reverse_composite_channel(blue, effective_key[2], matte_alpha)
            decontaminated_pixels += 1
        output_pixels.append((red, green, blue, output_alpha))

    output = Image.new("RGBA", (width, height))
    output.putdata(output_pixels)
    output_alpha = output.getchannel("A")
    extrema = output_alpha.getextrema()
    if extrema is None:
        raise SystemExit("Unable to inspect the output alpha channel")
    alpha_min, alpha_max = extrema
    if alpha_min == 255:
        raise SystemExit("Extraction produced no non-opaque pixels")
    if alpha_max == 0:
        raise SystemExit("Extraction removed the entire image")

    alpha_values = list(output_alpha.getdata())
    visible_mask = output_alpha.point(lambda value: 255 if value > 0 else 0)
    visible_bbox = visible_mask.getbbox()
    boundary_alpha_values = [
        alpha_values[index] for index in border_indices(width, height)
    ]
    boundary_alpha_maximum = max(boundary_alpha_values)
    visible_touches_boundary = any(
        value > BOUNDARY_VISIBLE_ALPHA_THRESHOLD for value in boundary_alpha_values
    )
    if args.generated_key_input and visible_touches_boundary:
        rejection_report = {
            "status": "rejected",
            "reason": "key-background-residue",
            "message": (
                "Generated key extraction left visible pixels touching the canvas boundary; "
                "the background is not a clean uniform key and must not be rescued by wider tolerances"
            ),
            "input": str(input_path),
            "output": str(output_path),
            "size": {"width": width, "height": height},
            "planned_key": format_hex(args.key),
            "key": format_hex(effective_key),
            "parameters": {
                "seed_tolerance": args.seed_tolerance,
                "grow_tolerance": args.grow_tolerance,
                "connectivity": args.connectivity,
                "generated_key_input": args.generated_key_input,
            },
            "key_source_audit": key_source_audit,
            "output_alpha": {
                "minimum": alpha_min,
                "maximum": alpha_max,
                "transparent_pixels": sum(value == 0 for value in alpha_values),
                "semitransparent_pixels": sum(0 < value < 255 for value in alpha_values),
                "opaque_pixels": sum(value == 255 for value in alpha_values),
                "visible_bbox": {
                    "left": visible_bbox[0],
                    "top": visible_bbox[1],
                    "right": visible_bbox[2],
                    "bottom": visible_bbox[3],
                },
                "visible_touches_boundary": True,
                "boundary_alpha_maximum": boundary_alpha_maximum,
                "boundary_visible_alpha_threshold": BOUNDARY_VISIBLE_ALPHA_THRESHOLD,
            },
        }
        report_path.write_text(
            json.dumps(rejection_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raise SystemExit(rejection_report["message"])

    output.save(output_path, format="PNG", optimize=True)
    report: dict[str, object] = {
        "input": str(input_path),
        "output": str(output_path),
        "size": {"width": width, "height": height},
        "planned_key": format_hex(args.key),
        "key": format_hex(effective_key),
        "key_source_audit": key_source_audit,
        "parameters": {
            "seed_tolerance": args.seed_tolerance,
            "grow_tolerance": args.grow_tolerance,
            "connectivity": args.connectivity,
            "generated_key_input": args.generated_key_input,
            "include_enclosed_key_regions": args.include_enclosed_key_regions,
            "decontaminate_edges": args.decontaminate_edges,
        },
        "segmentation": {
            "border_seed_pixels": border_seed_count,
            "boundary_connected_pixels": sum(boundary_connected),
            "enclosed_key_candidates": enclosed,
            "enclosed_key_candidate_count": len(enclosed),
            "enclosed_key_candidate_pixels": sum(
                int(component["area"]) for component in enclosed
            ),
            "decontaminated_edge_pixels": decontaminated_pixels,
        },
        "output_alpha": {
            "minimum": alpha_min,
            "maximum": alpha_max,
            "transparent_pixels": sum(value == 0 for value in alpha_values),
            "semitransparent_pixels": sum(0 < value < 255 for value in alpha_values),
            "opaque_pixels": sum(value == 255 for value in alpha_values),
            "has_nonopaque_pixels": alpha_min < 255,
            "has_visible_pixels": alpha_max > 0,
            "visible_touches_boundary": visible_touches_boundary,
            "boundary_alpha_maximum": boundary_alpha_maximum,
            "boundary_visible_alpha_threshold": BOUNDARY_VISIBLE_ALPHA_THRESHOLD,
            "visible_bbox": (
                {
                    "left": visible_bbox[0],
                    "top": visible_bbox[1],
                    "right": visible_bbox[2],
                    "bottom": visible_bbox[3],
                }
                if visible_bbox
                else None
            ),
        },
        "review_required": {
            "enclosed_key_candidates": bool(enclosed),
            "dark_light_edge_review": True,
            "internal_alpha_island_review": True,
        },
    }

    if args.qa_dir:
        qa_dir = args.qa_dir.expanduser().resolve()
        qa_dir.mkdir(parents=True, exist_ok=True)
        output_alpha.save(qa_dir / "alpha-mask.png")
        composite_preview(output, (24, 24, 24)).save(qa_dir / "composite-dark.png")
        composite_preview(output, (246, 246, 246)).save(qa_dir / "composite-light.png")
        checker_preview(output).save(qa_dir / "composite-checker.png")
        report["qa_dir"] = str(qa_dir)
        report["qa_artifacts"] = enclosed_candidate_previews(image, enclosed, qa_dir)

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
