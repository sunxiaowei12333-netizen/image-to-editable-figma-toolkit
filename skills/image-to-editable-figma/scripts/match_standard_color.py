#!/usr/bin/env python3
"""Match one deduplicated UI color to the fixed design-system palette.

The helper intentionally does not sample or scan an image. It receives a
representative solid-fill HEX selected from a text/icon interior and returns a
deterministic CIEDE2000 decision for the HTML color-decision record.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import math
from typing import Dict, Iterable, Optional, Tuple


PALETTE: Dict[str, str] = {
    "Color_Orange_01": "#FF7400",
    "Color_Gray_01": "#222222",
    "Color_Gray_02": "#333333",
    "Color_Gray_03": "#666666",
    "Color_Gray_04": "#999999",
    "Color_Gray_05": "#CCCCCC",
    "Color_Gray_06": "#E5E5E5",
    "Color_Gray_07": "#F4F4F4",
    "Color_Gray_08": "#F8F8F8",
    "Color_White": "#FFFFFF",
    "Color_Yellow_01": "#FFB122",
    "Color_Yellow_02": "#F8E966",
    "Color_Blue_01": "#48A5FF",
    "Color_Green_01": "#25CA7B",
    "Color_Red_01": "#FF3939",
    "Color_Orange_02": "#FFD5B3",
    "Color_Orange_03": "#FFF3EB",
    "Color_Yellow_03": "#FFFAEA",
    "Color_Green_02": "#F0F9EF",
    "Color_Blue_02": "#EBF7FF",
}


def parse_hex(value: str) -> Tuple[int, int, int]:
    text = value.strip().upper()
    if text.startswith("#"):
        text = text[1:]
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6 or any(ch not in "0123456789ABCDEF" for ch in text):
        raise ValueError(f"expected #RRGGBB, got {value!r}")
    return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))


def canonical_hex(value: str) -> str:
    return "#{:02X}{:02X}{:02X}".format(*parse_hex(value))


def _linear_channel(channel: int) -> float:
    value = channel / 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def rgb_to_lab(value: str) -> Tuple[float, float, float]:
    red, green, blue = (_linear_channel(channel) for channel in parse_hex(value))
    x = (0.4124564 * red + 0.3575761 * green + 0.1804375 * blue) / 0.95047
    y = (0.2126729 * red + 0.7151522 * green + 0.0721750 * blue) / 1.00000
    z = (0.0193339 * red + 0.1191920 * green + 0.9503041 * blue) / 1.08883

    delta = 6.0 / 29.0

    def pivot(component: float) -> float:
        if component > delta**3:
            return component ** (1.0 / 3.0)
        return component / (3.0 * delta**2) + 4.0 / 29.0

    fx, fy, fz = pivot(x), pivot(y), pivot(z)
    return 116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def _hue_degrees(a_value: float, b_value: float) -> float:
    angle = math.degrees(math.atan2(b_value, a_value))
    return angle + 360.0 if angle < 0.0 else angle


def delta_e_2000(lab1: Iterable[float], lab2: Iterable[float]) -> float:
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2.0
    g = 0.5 * (1.0 - math.sqrt(c_bar**7 / (c_bar**7 + 25.0**7)))
    a1_prime = (1.0 + g) * a1
    a2_prime = (1.0 + g) * a2
    c1_prime = math.hypot(a1_prime, b1)
    c2_prime = math.hypot(a2_prime, b2)
    h1_prime = _hue_degrees(a1_prime, b1)
    h2_prime = _hue_degrees(a2_prime, b2)

    delta_l_prime = l2 - l1
    delta_c_prime = c2_prime - c1_prime
    hue_gap = h2_prime - h1_prime
    if c1_prime * c2_prime == 0.0:
        delta_h_prime = 0.0
    elif abs(hue_gap) <= 180.0:
        delta_h_prime = hue_gap
    elif hue_gap > 180.0:
        delta_h_prime = hue_gap - 360.0
    else:
        delta_h_prime = hue_gap + 360.0
    delta_big_h_prime = 2.0 * math.sqrt(c1_prime * c2_prime) * math.sin(
        math.radians(delta_h_prime / 2.0)
    )

    l_bar_prime = (l1 + l2) / 2.0
    c_bar_prime = (c1_prime + c2_prime) / 2.0
    if c1_prime * c2_prime == 0.0:
        h_bar_prime = h1_prime + h2_prime
    elif abs(h1_prime - h2_prime) <= 180.0:
        h_bar_prime = (h1_prime + h2_prime) / 2.0
    elif h1_prime + h2_prime < 360.0:
        h_bar_prime = (h1_prime + h2_prime + 360.0) / 2.0
    else:
        h_bar_prime = (h1_prime + h2_prime - 360.0) / 2.0

    t = (
        1.0
        - 0.17 * math.cos(math.radians(h_bar_prime - 30.0))
        + 0.24 * math.cos(math.radians(2.0 * h_bar_prime))
        + 0.32 * math.cos(math.radians(3.0 * h_bar_prime + 6.0))
        - 0.20 * math.cos(math.radians(4.0 * h_bar_prime - 63.0))
    )
    delta_theta = 30.0 * math.exp(-(((h_bar_prime - 275.0) / 25.0) ** 2))
    r_c = 2.0 * math.sqrt(c_bar_prime**7 / (c_bar_prime**7 + 25.0**7))
    s_l = 1.0 + 0.015 * (l_bar_prime - 50.0) ** 2 / math.sqrt(
        20.0 + (l_bar_prime - 50.0) ** 2
    )
    s_c = 1.0 + 0.045 * c_bar_prime
    s_h = 1.0 + 0.015 * c_bar_prime * t
    r_t = -math.sin(math.radians(2.0 * delta_theta)) * r_c

    l_term = delta_l_prime / s_l
    c_term = delta_c_prime / s_c
    h_term = delta_big_h_prime / s_h
    return math.sqrt(
        l_term**2 + c_term**2 + h_term**2 + r_t * c_term * h_term
    )


def relative_luminance(value: str) -> float:
    red, green, blue = (_linear_channel(channel) for channel in parse_hex(value))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float:
    first = relative_luminance(foreground)
    second = relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def hue_gap(lab1: Tuple[float, float, float], lab2: Tuple[float, float, float]) -> float:
    first = _hue_degrees(lab1[1], lab1[2])
    second = _hue_degrees(lab2[1], lab2[2])
    difference = abs(first - second)
    return min(difference, 360.0 - difference)


# Versioned local matching bounds. These are design heuristics, not proof of
# perceptual equivalence or universal image accuracy. Review in the existing QA.
POLICY_VERSION = 2
MAX_DELTA_E = 15.0
MAX_LIGHTNESS_DELTA = 12.0
MAX_CHROMA_DELTA = 40.0
MAX_HUE_DELTA = 15.0
NEUTRAL_MAX_CHROMA = 6.0
NEAR_WHITE_MIN_LIGHTNESS = 90.0
NEAR_WHITE_MAX_CHROMA = 14.0
MIN_RELATIVE_CONTRAST = 0.75
READABLE_CONTRAST_FLOOR = 4.5


def color_family(value: str) -> Optional[str]:
    """Coarse routing only; Lab bounds must still pass for every candidate.

    Cyan, purple and magenta have no dedicated entries in this fixed palette.
    Do not force them into blue/red. Exact standard tokens bypass this routing.
    """
    red, green, blue = (channel / 255.0 for channel in parse_hex(value))
    hue = colorsys.rgb_to_hsv(red, green, blue)[0] * 360.0
    if hue < 20.0 or hue >= 345.0:
        return "Red"
    if hue < 36.0:
        return "Orange"
    if hue < 70.0:
        return "Yellow"
    if hue < 165.0:
        return "Green"
    if 200.0 <= hue < 260.0:
        return "Blue"
    return None


def evaluate(reference: str, background: Optional[str] = None) -> dict:
    reference = canonical_hex(reference)
    background = canonical_hex(background) if background else None
    reference_lab = rgb_to_lab(reference)
    reference_chroma = math.hypot(reference_lab[1], reference_lab[2])
    channels = parse_hex(reference)
    near_black = max(channels) <= 51 and max(channels) - min(channels) <= 8
    exact = next((name for name, color in PALETTE.items() if color == reference), None)

    # Near-black normalization deliberately takes precedence over exact #222222.
    if near_black:
        family, route = "near-black", "near-black-default"
        names = ["Color_Gray_02"]
    elif exact:
        family, route, names = "exact-standard", "exact-standard", [exact]
    elif reference_chroma <= NEUTRAL_MAX_CHROMA:
        family, route = "neutral", "full-gray-scale"
        names = [name for name in PALETTE if name.startswith("Color_Gray_") or name == "Color_White"]
    elif reference_lab[0] >= NEAR_WHITE_MIN_LIGHTNESS and reference_chroma <= NEAR_WHITE_MAX_CHROMA:
        family, route, names = "near-white", "near-white", ["Color_White"]
    else:
        family = color_family(reference)
        route = "bounded-same-family"
        names = [name for name in PALETTE if family and name.startswith("Color_" + family + "_")]

    source_contrast = contrast_ratio(reference, background) if background else None
    # Preserve the existing readable floor. General matching limits relative
    # loss on low-contrast sources too; it does not certify readability.
    # Explicit near-black normalization keeps only the floor, or no worsening
    # when the source was already low contrast.
    minimum_contrast = (
        (min(source_contrast, READABLE_CONTRAST_FLOOR) if near_black else
         max(source_contrast * MIN_RELATIVE_CONTRAST,
             READABLE_CONTRAST_FLOOR if source_contrast >= READABLE_CONTRAST_FLOOR else 0.0))
        if source_contrast is not None else None
    )
    candidates = []
    for name in names:
        target = PALETTE[name]
        target_lab = rgb_to_lab(target)
        delta_e = delta_e_2000(reference_lab, target_lab)
        lightness_delta = abs(reference_lab[0] - target_lab[0])
        target_chroma = math.hypot(target_lab[1], target_lab[2])
        chroma_delta = abs(reference_chroma - target_chroma)
        hue_delta = hue_gap(reference_lab, target_lab)
        failures = []
        if delta_e > MAX_DELTA_E:
            failures.append("delta-e-gap")
        if not near_black and lightness_delta > MAX_LIGHTNESS_DELTA:
            failures.append("lightness-gap")
        if chroma_delta > MAX_CHROMA_DELTA:
            failures.append("chroma-gap")
        if route == "bounded-same-family" and hue_delta > MAX_HUE_DELTA:
            failures.append("hue-gap")
        contrast = None
        if background:
            target_contrast = contrast_ratio(target, background)
            contrast_ok = target_contrast + 1e-9 >= minimum_contrast
            contrast = {
                "background": background,
                "reference": round(source_contrast, 4),
                "target": round(target_contrast, 4),
                "minimumAllowed": round(minimum_contrast, 4),
                "passed": contrast_ok,
            }
            if not contrast_ok:
                failures.append("contrast-drop")
        candidates.append({
            "name": name, "hex": target, "deltaE00": delta_e,
            "lightnessDelta": lightness_delta, "targetChroma": target_chroma,
            "chromaDelta": chroma_delta, "hueDelta": hue_delta,
            "contrastGuard": contrast, "guardFailures": failures,
        })

    # Filter BEFORE ranking. A rejected nearest gray must not hide a valid
    # adjacent gray; all eight gray levels participate in the same computation.
    rank_key = "lightnessDelta" if family == "neutral" else "deltaE00"
    eligible = [item for item in candidates if not item["guardFailures"]]
    selected = min(eligible, key=lambda item: item[rank_key]) if eligible else None
    diagnostic = selected or (min(candidates, key=lambda item: item[rank_key]) if candidates else None)
    nearest = min(PALETTE.items(), key=lambda item: delta_e_2000(reference_lab, rgb_to_lab(item[1])))
    if diagnostic is None:
        target_lab = rgb_to_lab(nearest[1])
        diagnostic = {
            "deltaE00": delta_e_2000(reference_lab, target_lab),
            "lightnessDelta": abs(reference_lab[0] - target_lab[0]),
            "targetChroma": math.hypot(target_lab[1], target_lab[2]),
            "chromaDelta": abs(reference_chroma - math.hypot(target_lab[1], target_lab[2])),
            "hueDelta": hue_gap(reference_lab, target_lab),
            "contrastGuard": None, "guardFailures": ["no-palette-family"],
        }
    return {
        "policyVersion": POLICY_VERSION,
        "referenceHex": reference,
        "nearestStandard": {"name": nearest[0], "hex": nearest[1]},
        "matchedStandard": {"name": selected["name"], "hex": selected["hex"]} if selected else None,
        "decisionFamily": family or "unsupported",
        "candidateCount": len(candidates),
        "eligibleCandidateCount": len(eligible),
        "deltaE00": round(diagnostic["deltaE00"], 4),
        "lightnessDelta": round(diagnostic["lightnessDelta"], 4),
        "referenceChroma": round(reference_chroma, 4),
        "targetChroma": round(diagnostic["targetChroma"], 4),
        "chromaDelta": round(diagnostic["chromaDelta"], 4),
        "hueDelta": round(diagnostic["hueDelta"], 4),
        "contrastGuard": diagnostic["contrastGuard"],
        "guardFailures": diagnostic["guardFailures"],
        "action": "use-standard" if selected else "preserve-reference",
        "targetHex": selected["hex"] if selected else reference,
        "method": "closest-standard" if selected else "reference-preserved",
        "reason": route if selected else ("no-palette-family" if not candidates else "no-eligible-candidate"),
        "requiresVisualReview": selected is not None and selected["hex"] != reference,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Match one reference UI color to the fixed design-system palette."
    )
    parser.add_argument("color", help="representative solid-fill color, e.g. #F36E00")
    parser.add_argument(
        "--background",
        help="optional representative placement background used by the 3-5 contrast guard",
    )
    args = parser.parse_args()
    try:
        result = evaluate(args.color, args.background)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
