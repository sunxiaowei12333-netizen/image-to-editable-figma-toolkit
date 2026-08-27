#!/usr/bin/env python3
"""Adaptive extraction for intentionally planned generated color-key images."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from PIL import Image


EDGE_NAMES = ("top", "right", "bottom", "left")
VISIBLE_ALPHA_THRESHOLD = 16


@dataclass
class AdaptiveKeyResult:
    image: Image.Image
    audit: dict[str, Any]
    enclosed_candidates: list[dict[str, Any]]


class AdaptiveKeyError(Exception):
    def __init__(self, reason: str, message: str, audit: dict[str, Any]) -> None:
        super().__init__(message)
        self.reason = reason
        self.audit = audit


def _smoothstep(values: np.ndarray, lower: float, upper: float) -> np.ndarray:
    scaled = np.clip((values - lower) / (upper - lower), 0.0, 1.0)
    return scaled * scaled * (3.0 - 2.0 * scaled)


def _edge_arrays(array: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "top": array[0, :],
        "right": array[:, -1],
        "bottom": array[-1, :],
        "left": array[:, 0],
    }


def _connected_to_boundary(mask: np.ndarray) -> tuple[np.ndarray, int]:
    count, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    if count <= 1:
        return np.zeros_like(mask, dtype=bool), 0
    boundary_labels = np.unique(
        np.concatenate((labels[0, :], labels[:, -1], labels[-1, :], labels[:, 0]))
    )
    boundary_labels = boundary_labels[boundary_labels != 0]
    return np.isin(labels, boundary_labels), int(boundary_labels.size)


def _components(mask: np.ndarray, minimum_area: int) -> list[dict[str, Any]]:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    output: list[dict[str, Any]] = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < minimum_area:
            continue
        left = int(stats[label, cv2.CC_STAT_LEFT])
        top = int(stats[label, cv2.CC_STAT_TOP])
        width = int(stats[label, cv2.CC_STAT_WIDTH])
        height = int(stats[label, cv2.CC_STAT_HEIGHT])
        output.append(
            {
                "area": area,
                "bbox": {
                    "left": left,
                    "top": top,
                    "right": left + width,
                    "bottom": top + height,
                },
            }
        )
    output.sort(key=lambda component: int(component["area"]), reverse=True)
    for component_id, component in enumerate(output, start=1):
        component["id"] = component_id
    return output


def _alpha_bbox(alpha: np.ndarray) -> dict[str, int] | None:
    ys, xs = np.nonzero(alpha > 0)
    if not len(xs):
        return None
    return {
        "left": int(xs.min()),
        "top": int(ys.min()),
        "right": int(xs.max() + 1),
        "bottom": int(ys.max() + 1),
    }


def _extend_foreground_rgb(
    rgb: np.ndarray,
    alpha: np.ndarray,
    key_confidence: np.ndarray,
) -> tuple[np.ndarray, int]:
    """Extend clean interior RGB into the soft matte without key-color inversion."""
    opaque = alpha >= 250
    soft_or_transparent = alpha < 250
    near_soft_edge = cv2.dilate(
        soft_or_transparent.astype(np.uint8), np.ones((3, 3), np.uint8)
    ) > 0
    suspected_spill = opaque & near_soft_edge & (key_confidence >= 0.05)
    known = opaque & ~suspected_spill
    filled = rgb.astype(np.float32).copy()
    kernel = np.ones((3, 3), dtype=np.float32)
    for _ in range(16):
        if np.all(known | (alpha == 0)):
            break
        known_float = known.astype(np.float32)
        counts = cv2.filter2D(known_float, -1, kernel, borderType=cv2.BORDER_CONSTANT)
        frontier = (~known) & (counts > 0)
        if not np.any(frontier):
            break
        for channel in range(3):
            sums = cv2.filter2D(
                filled[..., channel] * known_float,
                -1,
                kernel,
                borderType=cv2.BORDER_CONSTANT,
            )
            filled[..., channel][frontier] = sums[frontier] / counts[frontier]
        known[frontier] = True

    replace = ((alpha > 0) & (alpha < 250)) | suspected_spill
    output = rgb.astype(np.float32).copy()
    output[replace] = filled[replace]
    output[alpha == 0] = 0.0
    return output, int(np.count_nonzero(replace))


def _suppress_magenta_spill(
    rgb: np.ndarray,
    alpha: np.ndarray,
    planned_key: tuple[int, int, int],
) -> tuple[np.ndarray, int]:
    """Remove residual R+B spill in the visible contour for a planned magenta key."""
    red_key, green_key, blue_key = planned_key
    if red_key < 180 or blue_key < 180 or green_key > 100:
        return rgb, 0
    transparent = alpha <= VISIBLE_ALPHA_THRESHOLD
    contour_band = (alpha > VISIBLE_ALPHA_THRESHOLD) & (
        cv2.dilate(transparent.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    )
    output = rgb.astype(np.float32).copy()
    red = output[..., 0]
    green = output[..., 1]
    blue = output[..., 2]
    excess = np.maximum(np.minimum(red, blue) - green - 1.0, 0.0)
    spill = contour_band & (excess > 0.0)
    red[spill] -= excess[spill]
    blue[spill] -= excess[spill]
    return np.clip(output, 0.0, 255.0), int(np.count_nonzero(spill))


def extract_adaptive_generated_key(
    source: Image.Image,
    planned_key: tuple[int, int, int],
    *,
    allowed_subject_touch_edges: set[str],
    include_enclosed_key_regions: bool,
    minimum_enclosed_area: int,
) -> AdaptiveKeyResult:
    """Extract a planned key family while preserving protected subject details."""
    invalid_edges = sorted(allowed_subject_touch_edges - set(EDGE_NAMES))
    if invalid_edges:
        raise ValueError(f"Unsupported touch edges: {invalid_edges}")

    rgba_source = source.convert("RGBA")
    source_rgba = np.asarray(rgba_source, dtype=np.uint8)
    rgb_u8 = source_rgba[..., :3]
    source_alpha = source_rgba[..., 3]
    height, width = rgb_u8.shape[:2]
    bgr = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hue = hsv[..., 0].astype(np.float32)
    saturation = hsv[..., 1].astype(np.float32)
    value = hsv[..., 2].astype(np.float32)

    key_rgb = np.asarray(planned_key, dtype=np.float32)
    key_bgr = np.uint8([[key_rgb[::-1]]])
    key_hsv = cv2.cvtColor(key_bgr, cv2.COLOR_BGR2HSV)[0, 0]
    key_hue = float(key_hsv[0])
    hue_distance = np.minimum(np.abs(hue - key_hue), 180.0 - np.abs(hue - key_hue))

    rgb = rgb_u8.astype(np.float32)
    chroma = rgb - rgb.min(axis=2, keepdims=True)
    chroma_norm = np.linalg.norm(chroma, axis=2)
    key_chroma = key_rgb - key_rgb.min()
    key_chroma /= max(float(np.linalg.norm(key_chroma)), 1e-6)
    chroma_cosine = np.sum(chroma * key_chroma, axis=2) / np.maximum(chroma_norm, 1e-6)

    hue_confidence = 1.0 - _smoothstep(hue_distance, 8.0, 30.0)
    saturation_confidence = _smoothstep(saturation, 28.0, 150.0)
    chroma_confidence = _smoothstep(chroma_cosine, 0.68, 0.96)
    value_confidence = _smoothstep(value, 22.0, 90.0)
    key_confidence = hue_confidence * np.sqrt(
        saturation_confidence * chroma_confidence * value_confidence
    )

    strong = (
        (hue_distance <= 10.0)
        & (saturation >= 135.0)
        & (value >= 45.0)
        & (chroma_cosine >= 0.90)
    )
    family = (
        (hue_distance <= 26.0)
        & (saturation >= 30.0)
        & (value >= 22.0)
        & (chroma_cosine >= 0.70)
    )
    strong_edges = _edge_arrays(strong)
    family_edges = _edge_arrays(family)
    edge_coverage = {
        edge: {
            "strong_ratio": round(float(strong_edges[edge].mean()), 6),
            "family_ratio": round(float(family_edges[edge].mean()), 6),
            "allowed_subject_touch": edge in allowed_subject_touch_edges,
        }
        for edge in EDGE_NAMES
    }
    incompatible_edges = [
        edge
        for edge in EDGE_NAMES
        if edge not in allowed_subject_touch_edges
        and float(edge_coverage[edge]["family_ratio"]) < 0.95
    ]
    base_audit: dict[str, Any] = {
        "selection_mode": "adaptive-planned-key-family-v3",
        "planned_key": "#{:02X}{:02X}{:02X}".format(*planned_key),
        "allowed_subject_touch_edges": sorted(allowed_subject_touch_edges),
        "edge_key_coverage": edge_coverage,
    }
    if incompatible_edges:
        base_audit["incompatible_edges"] = incompatible_edges
        raise AdaptiveKeyError(
            "key-background-impure",
            "Generated background contains an incompatible or multicolor outer edge; "
            "only a planned-key color family or an explicitly declared subject crop is accepted",
            base_audit,
        )

    boundary_family, family_component_count = _connected_to_boundary(family)
    known_background = strong & boundary_family
    if not np.any(known_background):
        raise AdaptiveKeyError(
            "key-background-impure",
            "No strong planned-key family pixels connect to the canvas boundary",
            base_audit,
        )

    inpaint_mask = (~known_background).astype(np.uint8) * 255
    background_model_bgr = cv2.inpaint(bgr, inpaint_mask, 9.0, cv2.INPAINT_TELEA)
    background_model = cv2.cvtColor(background_model_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
    color_distance = np.linalg.norm(rgb - background_model, axis=2)
    removal_candidate = boundary_family | (color_distance <= 112.0)
    boundary_removal_region, removal_component_count = _connected_to_boundary(removal_candidate)
    enclosed_family = family & ~boundary_family
    enclosed_candidates = _components(enclosed_family, minimum_enclosed_area)
    removal_region = boundary_removal_region.copy()
    if include_enclosed_key_regions:
        removal_region |= enclosed_family

    alpha_from_distance = _smoothstep(color_distance, 5.0, 112.0)
    alpha_from_family = 1.0 - _smoothstep(key_confidence, 0.32, 0.93)
    alpha_float = np.ones((height, width), dtype=np.float32)
    alpha_float[removal_region] = np.minimum(
        alpha_from_distance[removal_region], alpha_from_family[removal_region]
    )
    alpha_float[removal_region & (key_confidence >= 0.92)] = 0.0
    alpha_float[alpha_float <= 0.012] = 0.0
    alpha_float[alpha_float >= 0.992] = 1.0

    for edge, values in _edge_arrays(alpha_float).items():
        if edge in allowed_subject_touch_edges:
            continue
        edge_family = family_edges[edge]
        edge_confidence = _edge_arrays(key_confidence)[edge]
        values[(edge_family | (edge_confidence >= 0.05))] = 0.0

    alpha_u8 = np.round(alpha_float * 255.0).astype(np.uint8)
    alpha_u8[alpha_u8 <= VISIBLE_ALPHA_THRESHOLD] = 0
    alpha_u8 = np.minimum(alpha_u8, source_alpha)
    boundary = {
        edge: {
            "maximum": int(values.max()),
            "visible_pixels_over_16": int(np.count_nonzero(values > VISIBLE_ALPHA_THRESHOLD)),
            "allowed_subject_touch": edge in allowed_subject_touch_edges,
        }
        for edge, values in _edge_arrays(alpha_u8).items()
    }
    unapproved_touch_edges = [
        edge
        for edge in EDGE_NAMES
        if edge not in allowed_subject_touch_edges
        and int(boundary[edge]["visible_pixels_over_16"]) > 0
    ]
    if unapproved_touch_edges:
        rejection_audit = {
            **base_audit,
            "unapproved_subject_touch_edges": unapproved_touch_edges,
            "output_alpha": {"boundary": boundary, "visible_bbox": _alpha_bbox(alpha_u8)},
        }
        raise AdaptiveKeyError(
            "unapproved-subject-edge-contact",
            "Visible non-key subject pixels touch an undeclared canvas edge; declare an "
            "intentional crop edge or regenerate with safe padding",
            rejection_audit,
        )

    output_rgb, extended_pixels = _extend_foreground_rgb(rgb, alpha_u8, key_confidence)
    output_rgb, spill_suppressed_pixels = _suppress_magenta_spill(
        output_rgb, alpha_u8, planned_key
    )
    output = Image.fromarray(np.dstack((np.round(output_rgb).astype(np.uint8), alpha_u8)))

    output_hsv = cv2.cvtColor(
        cv2.cvtColor(np.asarray(output)[..., :3], cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2HSV
    )
    output_hue = output_hsv[..., 0].astype(np.float32)
    output_saturation = output_hsv[..., 1].astype(np.float32)
    output_hue_distance = np.minimum(
        np.abs(output_hue - key_hue), 180.0 - np.abs(output_hue - key_hue)
    )
    semitransparent = (alpha_u8 > VISIBLE_ALPHA_THRESHOLD) & (alpha_u8 < 250)
    key_like_fringe = (
        semitransparent & (output_hue_distance <= 26.0) & (output_saturation >= 48.0)
    )
    audit = {
        **base_audit,
        "segmentation": {
            "strong_pixels": int(np.count_nonzero(strong)),
            "boundary_key_family_pixels": int(np.count_nonzero(boundary_family)),
            "boundary_key_family_components": family_component_count,
            "boundary_removal_pixels": int(np.count_nonzero(removal_region)),
            "boundary_removal_components": removal_component_count,
            "foreground_rgb_extended_pixels": extended_pixels,
            "magenta_spill_suppressed_pixels": spill_suppressed_pixels,
        },
        "output_alpha": {
            "boundary": boundary,
            "visible_bbox": _alpha_bbox(alpha_u8),
        },
        "edge_qa": {
            "semitransparent_pixels_over_16": int(np.count_nonzero(semitransparent)),
            "key_like_semitransparent_pixels": int(np.count_nonzero(key_like_fringe)),
            "key_like_semitransparent_ratio": round(
                float(np.count_nonzero(key_like_fringe) / max(1, np.count_nonzero(semitransparent))),
                6,
            ),
        },
    }
    return AdaptiveKeyResult(output, audit, enclosed_candidates)
