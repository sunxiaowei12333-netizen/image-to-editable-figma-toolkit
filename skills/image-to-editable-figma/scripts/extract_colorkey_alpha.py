#!/usr/bin/env python3
"""Convert a deliberately planned solid color key into a reviewed RGBA PNG."""

from __future__ import annotations

import argparse
from collections import deque
import json
import math
from pathlib import Path

from PIL import Image


MAX_RGB_DISTANCE = math.sqrt(3 * 255 * 255)


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
        default=18.0,
        help="Maximum RGB distance for strong border seeds (default: 18)",
    )
    parser.add_argument(
        "--grow-tolerance",
        type=float,
        default=72.0,
        help="Maximum RGB distance for boundary-connected growth (default: 72)",
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
    source_pixels = list(image.getdata())
    distances = [rgb_distance(pixel, args.key) for pixel in source_pixels]
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
            red = reverse_composite_channel(red, args.key[0], matte_alpha)
            green = reverse_composite_channel(green, args.key[1], matte_alpha)
            blue = reverse_composite_channel(blue, args.key[2], matte_alpha)
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
    output.save(output_path, format="PNG", optimize=True)

    alpha_values = list(output_alpha.getdata())
    visible_mask = output_alpha.point(lambda value: 255 if value > 0 else 0)
    visible_bbox = visible_mask.getbbox()
    report: dict[str, object] = {
        "input": str(input_path),
        "output": str(output_path),
        "size": {"width": width, "height": height},
        "key": "#{:02X}{:02X}{:02X}".format(*args.key),
        "parameters": {
            "seed_tolerance": args.seed_tolerance,
            "grow_tolerance": args.grow_tolerance,
            "connectivity": args.connectivity,
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

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
