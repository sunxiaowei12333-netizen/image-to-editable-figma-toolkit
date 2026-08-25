#!/usr/bin/env python3
"""Run one static preflight pass before Figma HTML Capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse


CAPTURE_SCRIPT = "https://mcp.figma.com/mcp/html-to-design/capture.js"
REMOTE_SCHEMES = {"http", "https", "data", "blob", "mailto", "tel", "javascript"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
FONT_SIZE_RE = re.compile(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", re.I)
FONT_WEIGHT_RE = re.compile(r"font-weight\s*:\s*(bold|[6-9]00)\b", re.I)
FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)
LINE_HEIGHT_RE = re.compile(r"line-height\s*:\s*([^;}{]+)", re.I)
URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)
SCALE_RE = re.compile(r"transform\s*:[^;}{]*\bscale(?:X|Y|3d)?\s*\(", re.I)
ZOOM_RE = re.compile(r"\bzoom\s*:\s*(?!1(?:\.0+)?\s*(?:;|}|$))", re.I)
CLIP_PATH_RE = re.compile(r"(?:-webkit-)?clip-path\s*:", re.I)
LAYOUT_VALUES = {"row", "column", "wrap", "overlay", "viewport"}
SIZING_VALUES = {"fixed", "hug", "fill"}
FIGMA_NODE_TYPES = {
    "IMAGE",
    "RECTANGLE",
    "ELLIPSE",
    "VECTOR",
    "LINE",
    "TEXT",
    "INSTANCE",
    "FRAME",
    "GROUP",
}
LAYOUT_CLASSES = {
    "row": "f-row",
    "column": "f-column",
    "wrap": "f-wrap",
    "overlay": "f-overlay",
    "viewport": "f-viewport",
}
IMAGE_REQUIRED_KINDS = {
    "pure-scene-background",
    "complete-character",
    "person",
    "complex-frame",
    "complex-decoration",
    "standalone-illustration",
    "photo",
    "product-object",
    "material-object",
}
SUPPORTED_RESOURCE_KINDS = IMAGE_REQUIRED_KINDS | {
    "simple-decoration",
    "simple-geometry",
    "ui-container",
    "ui-icon",
}
COMPLEXITY_SIGNALS = {
    "irregular_parts",
    "texture_or_noise",
    "material_edges",
    "precise_highlight_shadow",
    "translucency_or_glow",
    "dense_paths",
    "recognizable_complete_illustration",
}
RESOURCE_SOURCE_METHODS = {
    "provided-original",
    "clean-crop",
    "reliable-separation",
    "localized-repair",
    "reference-guided-edit",
    "new-generation",
    "native-rebuild",
    "library-asset",
}
REUSE_SOURCE_METHODS = {"clean-crop", "reliable-separation"}
BASE_REUSE_EVIDENCE_FIELDS = {
    "completeVisibleBounds",
    "noOcclusion",
    "noBakedUiTextOrAdjacentContent",
    "effectiveResolutionAtLeast2x",
}
SEPARATION_EVIDENCE_FIELDS = {
    "hardEdgesOnly",
    "backgroundClearlySeparable",
    "noFragileEdgeFeatures",
}
ROUTING_EXCEPTION_TYPES = {
    "user_requires_internal_editing",
    "verified_layered_vector_source",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}")


def attrs_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {key.lower(): value or "" for key, value in attrs}


def is_remote(value: str) -> bool:
    if not value or value.startswith(("#", "//")):
        return True
    return urlparse(value).scheme.lower() in REMOTE_SCHEMES


def resolve_local(base: Path, value: str) -> Path | None:
    value = unquote(value.split("#", 1)[0].split("?", 1)[0].strip())
    if not value or is_remote(value):
        return None
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (base / candidate).resolve()


class CaptureHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict[str, str]]] = []
        self.dependencies: list[tuple[str, str, str]] = []
        self.inline_css: list[str] = []
        self.capture_script_found = False
        self.dual_capture_loader_found = False
        self.body_attrs: dict[str, str] = {}
        self.canvas_found = False
        self.canvas_attrs: dict[str, str] = {}
        self.canvas_depth: int | None = None
        self.canvas_first_child: tuple[str, dict[str, str]] | None = None
        self.icon_errors: list[str] = []
        self.rectangle_errors: list[str] = []
        self.node_type_errors: list[str] = []
        self.node_type_counts: dict[str, int] = {}
        self.layout_nodes: list[tuple[str, dict[str, str]]] = []
        self.icon_nodes: list[tuple[str, dict[str, str]]] = []
        self.resource_nodes: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.icon_count = 0
        self.rectangle_count = 0
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        item = attrs_dict(attrs)

        if self.canvas_depth is not None and len(self.stack) == self.canvas_depth:
            if self.canvas_first_child is None:
                self.canvas_first_child = (tag, item)

        if item.get("id") == "canvas" and self.canvas_depth is None:
            self.canvas_found = True
            self.canvas_attrs = item
            self.canvas_depth = len(self.stack) + 1

        if tag == "body":
            self.body_attrs = item

        if tag == "script" and item.get("src", "").split("?", 1)[0] == CAPTURE_SCRIPT:
            self.capture_script_found = True
        if tag == "script" and item.get("data-dual-capture-loader") == "ready":
            self.dual_capture_loader_found = True

        for attr in ("src", "href"):
            if item.get(attr):
                self.dependencies.append((tag, attr, item[attr]))

        if item.get("style"):
            self.inline_css.append(item["style"])

        icon_name = item.get("data-icon-name")
        icon_library = item.get("data-icon-library")
        if icon_name or icon_library:
            self.icon_count += 1
            self.icon_nodes.append((tag, item))
            if not icon_name or not icon_library:
                self.icon_errors.append(
                    f"<{tag}> must contain both data-icon-library and data-icon-name"
                )

        classes = set(item.get("class", "").lower().split())
        looks_like_ui_icon = any("icon" in token for token in classes) and not any(
            marker in token
            for token in classes
            for marker in ("logo", "brand", "illustration", "artwork")
        )
        ancestor_has_icon_marker = any(
            ancestor.get("data-icon-name") and ancestor.get("data-icon-library")
            for _, ancestor in self.stack
        )
        if tag == "svg" and looks_like_ui_icon and not (
            icon_name and icon_library or ancestor_has_icon_marker
        ):
            self.icon_errors.append(
                f"UI icon SVG with class={item.get('class')!r} has no Icon Library traceability"
            )

        figma_node_type = item.get("data-figma-node-type", "").upper()
        if figma_node_type:
            self.node_type_counts[figma_node_type] = self.node_type_counts.get(figma_node_type, 0) + 1
            if figma_node_type not in FIGMA_NODE_TYPES:
                self.node_type_errors.append(
                    f"<{tag}> has unsupported data-figma-node-type={figma_node_type!r}"
                )

        if figma_node_type == "RECTANGLE":
            self.rectangle_count += 1
            if not (item.get("data-corner-radius") or item.get("data-corner-radii")):
                self.rectangle_errors.append(
                    f"<{tag}> marked RECTANGLE is missing data-corner-radius/data-corner-radii"
                )
        elif figma_node_type == "VECTOR":
            explicit_vector = tag in {"svg", "path", "polygon", "polyline"} or bool(
                item.get("data-vector-path")
            )
            if not explicit_vector:
                self.node_type_errors.append(
                    f"<{tag}> marked VECTOR must be explicit SVG/path geometry or provide data-vector-path"
                )

        resource_id = item.get("data-resource-id", "").strip()
        if resource_id:
            self.resource_nodes.setdefault(resource_id, []).append((tag, item))

        if item.get("data-figma-layout"):
            self.layout_nodes.append((tag, item))

        if tag not in VOID_TAGS:
            self.stack.append((tag, item))
            if tag == "style":
                self._in_style = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "style":
            self._in_style = False
        if self.stack:
            self.stack.pop()
        if self.canvas_depth is not None and len(self.stack) < self.canvas_depth:
            self.canvas_depth = None

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.inline_css.append(data)


def inspect_css(label: str, css: str, warnings: list[str], metrics: dict[str, object]) -> list[str]:
    families = [match.group(1).strip() for match in FONT_FAMILY_RE.finditer(css)]
    sizes = [float(match.group(1)) for match in FONT_SIZE_RE.finditer(css)]
    risky_weights = sorted({match.group(1) for match in FONT_WEIGHT_RE.finditer(css)})
    fixed_line_heights = sorted(
        {match.group(1).strip() for match in LINE_HEIGHT_RE.finditer(css) if match.group(1).strip().lower() != "normal"}
    )

    metrics.setdefault("font_families", [])
    for family in families:
        if family not in metrics["font_families"]:
            metrics["font_families"].append(family)

    decimal_sizes = sorted({size for size in sizes if not size.is_integer()})
    odd_sizes = sorted({int(size) for size in sizes if size.is_integer() and int(size) % 2})
    if decimal_sizes:
        warnings.append(f"{label}: decimal font sizes {decimal_sizes}")
    if odd_sizes:
        warnings.append(f"{label}: odd font sizes {odd_sizes}; even sizes are preferred")
    if risky_weights:
        warnings.append(
            f"{label}: weights {risky_weights} require reference/user evidence; 700 is normally forbidden"
        )
    if fixed_line_heights:
        warnings.append(
            f"{label}: fixed line-height values {fixed_line_heights}; default must be normal/Figma AUTO"
        )
    if re.search(r"background-image\s*:", css, re.I):
        warnings.append(f"{label}: contains background-image; pure scene background must be an <img>")
    if SCALE_RE.search(css) or ZOOM_RE.search(css):
        warnings.append(f"{label}: contains scale/zoom that may destabilize Figma text geometry")
    if CLIP_PATH_RE.search(css):
        warnings.append(
            f"{label}: contains clip-path; high-visual editable silhouettes must use an explicit VECTOR marker/path"
        )
    return [match.group(2) for match in URL_RE.finditer(css)]


def element_label(tag: str, attrs: dict[str, str]) -> str:
    identity = attrs.get("id") or attrs.get("data-name") or attrs.get("class")
    return f"<{tag}{' ' + identity if identity else ''}>"


def has_inline_size(attrs: dict[str, str]) -> bool:
    if attrs.get("width") and attrs.get("height"):
        return True
    style = attrs.get("style", "")
    return bool(
        re.search(r"(?:^|;)\s*width\s*:\s*[^;]+", style, re.I)
        and re.search(r"(?:^|;)\s*height\s*:\s*[^;]+", style, re.I)
    )


def read_json_object(path: Path, label: str, errors: list[str]) -> dict[str, object] | None:
    if not path.is_file():
        errors.append(f"{label} not found: {path}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"Unable to read {label} {path}: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{label} root must be a JSON object: {path}")
        return None
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_resource_manifest(
    manifest_path: Path,
    contract_path: Path,
    parser: CaptureHTMLParser,
    errors: list[str],
    warnings: list[str],
    metrics: dict[str, object],
) -> None:
    manifest = read_json_object(manifest_path, "Resource manifest", errors)
    contract = read_json_object(contract_path, "Composition contract", errors)
    if manifest is None or contract is None:
        return

    if manifest.get("schemaVersion") != 3:
        errors.append("Resource manifest schemaVersion must be 3")

    generation_policy = manifest.get("generationPolicy")
    if not isinstance(generation_policy, dict):
        errors.append("Resource manifest generationPolicy must be an object")
    else:
        if generation_policy.get("scope") != "per-visual-atom":
            errors.append("Resource manifest generationPolicy.scope must be 'per-visual-atom'")
        calls_per_atom = generation_policy.get("defaultHighQualityCallsPerAtom")
        if calls_per_atom != 1 or isinstance(calls_per_atom, bool):
            errors.append(
                "Resource manifest generationPolicy.defaultHighQualityCallsPerAtom must be 1"
            )
        if "pageWideCap" not in generation_policy or generation_policy.get("pageWideCap") is not None:
            errors.append("Resource manifest generationPolicy.pageWideCap must be null")

    reference = manifest.get("reference")
    references = manifest.get("references")
    if isinstance(reference, dict) and references is None:
        reference_items = [reference]
    elif reference is None and isinstance(references, list) and references:
        reference_items = references
    else:
        reference_items = []
        errors.append(
            "Resource manifest must contain either one reference object or a non-empty references array"
        )

    seen_reference_hashes: set[str] = set()
    for reference_index, reference_item in enumerate(reference_items):
        reference_label = (
            "Resource manifest reference"
            if len(reference_items) == 1
            else f"Resource manifest references[{reference_index}]"
        )
        if not isinstance(reference_item, dict):
            errors.append(f"{reference_label} must be an object")
            continue
        raw_reference_path = reference_item.get("path")
        expected_sha = reference_item.get("sha256")
        if not isinstance(raw_reference_path, str) or not raw_reference_path.strip():
            errors.append(f"{reference_label}.path must be a non-empty absolute path")
        else:
            reference_path = Path(raw_reference_path).expanduser()
            if not reference_path.is_absolute():
                errors.append(f"{reference_label}.path must be absolute")
            elif not reference_path.is_file():
                errors.append(f"{reference_label} image not found: {reference_path}")
            elif not isinstance(expected_sha, str) or not SHA256_RE.fullmatch(expected_sha):
                errors.append(f"{reference_label}.sha256 must be 64 lowercase hex characters")
            else:
                if expected_sha in seen_reference_hashes:
                    warnings.append(f"{reference_label} repeats an earlier reference SHA-256")
                seen_reference_hashes.add(expected_sha)
                actual_sha = sha256_file(reference_path)
                if actual_sha != expected_sha:
                    errors.append(
                        f"{reference_label} SHA-256 mismatch: expected {expected_sha}, got {actual_sha}"
                    )

    contract_elements_raw = contract.get("elements", [])
    if not isinstance(contract_elements_raw, list):
        errors.append("Composition contract elements must be an array")
        contract_elements_raw = []
    contract_elements = {
        item.get("id"): item
        for item in contract_elements_raw
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        errors.append("Resource manifest assets must be a non-empty array")
        return

    seen_ids: set[str] = set()
    manifest_ids: set[str] = set()
    image_route_count = 0
    complex_route_count = 0

    for index, asset in enumerate(assets):
        label = f"Resource manifest assets[{index}]"
        if not isinstance(asset, dict):
            errors.append(f"{label} must be an object")
            continue

        resource_id = asset.get("id")
        if not isinstance(resource_id, str) or not resource_id.strip():
            errors.append(f"{label}.id must be a non-empty string")
            continue
        resource_id = resource_id.strip()
        label = f"Resource {resource_id!r}"
        if resource_id in seen_ids:
            errors.append(f"Duplicate resource id: {resource_id}")
            continue
        seen_ids.add(resource_id)
        manifest_ids.add(resource_id)

        kind = asset.get("kind")
        if kind not in SUPPORTED_RESOURCE_KINDS:
            errors.append(f"{label} has unsupported kind={kind!r}")

        selector = asset.get("selector")
        if not isinstance(selector, str) or "data-resource-id" not in selector:
            errors.append(f"{label}.selector must target its data-resource-id")

        if not isinstance(asset.get("editableInternals"), bool):
            errors.append(f"{label}.editableInternals must be boolean")

        source_method = asset.get("sourceMethod")
        if not isinstance(source_method, str) or source_method not in RESOURCE_SOURCE_METHODS:
            errors.append(
                f"{label}.sourceMethod must be one of {sorted(RESOURCE_SOURCE_METHODS)}, got {source_method!r}"
            )

        reuse_evidence = asset.get("reuseEvidence")
        if isinstance(source_method, str) and source_method in REUSE_SOURCE_METHODS:
            if not isinstance(reuse_evidence, dict):
                errors.append(f"{label}.reuseEvidence must be an object for {source_method}")
            else:
                required_evidence = set(BASE_REUSE_EVIDENCE_FIELDS)
                if source_method == "reliable-separation":
                    required_evidence.update(SEPARATION_EVIDENCE_FIELDS)
                for field in sorted(required_evidence):
                    if reuse_evidence.get(field) is not True:
                        errors.append(
                            f"{label}.reuseEvidence.{field} must be true for {source_method}"
                        )
                inspection_note = reuse_evidence.get("inspectionNote")
                if not isinstance(inspection_note, str) or not inspection_note.strip():
                    errors.append(
                        f"{label}.reuseEvidence.inspectionNote must be a non-empty string for {source_method}"
                    )

        signals = asset.get("complexitySignals")
        if not isinstance(signals, list) or any(not isinstance(value, str) for value in signals):
            errors.append(f"{label}.complexitySignals must be an array of strings")
            signals = []
        else:
            unknown_signals = sorted(set(signals) - COMPLEXITY_SIGNALS)
            if unknown_signals:
                errors.append(f"{label} has unsupported complexity signals: {unknown_signals}")

        expected_type_raw = asset.get("expectedFigmaType")
        expected_type = expected_type_raw.upper() if isinstance(expected_type_raw, str) else ""
        if expected_type not in FIGMA_NODE_TYPES:
            errors.append(f"{label}.expectedFigmaType is invalid: {expected_type_raw!r}")

        routing_exception = asset.get("routingException")
        valid_exception = False
        if routing_exception is not None:
            if not isinstance(routing_exception, dict):
                errors.append(f"{label}.routingException must be an object")
            else:
                exception_type = routing_exception.get("type")
                evidence = routing_exception.get("evidence")
                valid_exception = (
                    exception_type in ROUTING_EXCEPTION_TYPES
                    and isinstance(evidence, str)
                    and bool(evidence.strip())
                )
                if not valid_exception:
                    errors.append(
                        f"{label}.routingException must use an allowed type and non-empty evidence"
                    )

        requires_image = kind in IMAGE_REQUIRED_KINDS
        if requires_image:
            complex_route_count += 1
            if expected_type != "IMAGE" and not valid_exception:
                errors.append(
                    f"{label} kind={kind!r} must remain IMAGE unless a permitted routingException is recorded"
                )
        if kind == "simple-decoration" and signals:
            errors.append(
                f"{label} cannot be simple-decoration while complexitySignals are present; choose the matching image kind"
            )

        fallbacks = asset.get("fallbacks")
        if not isinstance(fallbacks, list):
            errors.append(f"{label}.fallbacks must be an array")
            fallbacks = []
        for fallback_index, fallback in enumerate(fallbacks):
            fallback_label = f"{label}.fallbacks[{fallback_index}]"
            if not isinstance(fallback, dict):
                errors.append(f"{fallback_label} must be an object")
                continue
            method = fallback.get("method")
            fallback_type_raw = fallback.get("figmaType")
            fallback_type = fallback_type_raw.upper() if isinstance(fallback_type_raw, str) else ""
            if not isinstance(method, str) or not method.strip():
                errors.append(f"{fallback_label}.method must be a non-empty string")
            if fallback_type not in FIGMA_NODE_TYPES:
                errors.append(f"{fallback_label}.figmaType is invalid: {fallback_type_raw!r}")
            if expected_type == "IMAGE" and fallback_type != "IMAGE":
                errors.append(
                    f"{fallback_label} changes an IMAGE resource to {fallback_type or 'an invalid type'}"
                )

        expected_count = asset.get("expectedCount", 1)
        if not isinstance(expected_count, int) or isinstance(expected_count, bool) or expected_count <= 0:
            errors.append(f"{label}.expectedCount must be a positive integer")
            expected_count = 1
        dom_nodes = parser.resource_nodes.get(resource_id, [])
        if len(dom_nodes) != expected_count:
            errors.append(
                f"{label} expects {expected_count} HTML node(s) with data-resource-id, found {len(dom_nodes)}"
            )
        for tag, attrs in dom_nodes:
            dom_type = attrs.get("data-figma-node-type", "").upper()
            if not dom_type:
                errors.append(f"{label} HTML <{tag}> is missing data-figma-node-type")
            elif expected_type and dom_type != expected_type:
                errors.append(
                    f"{label} expects {expected_type}, but HTML <{tag}> declares {dom_type}"
                )
            if expected_type == "IMAGE" and tag != "img":
                errors.append(f"{label} IMAGE must be represented by a direct <img>, found <{tag}>")

        composition_id = asset.get("compositionId")
        if not isinstance(composition_id, str) or not composition_id.strip():
            errors.append(f"{label}.compositionId must be a non-empty string")
        elif composition_id not in contract_elements:
            errors.append(f"{label}.compositionId={composition_id!r} is missing from the composition contract")
        else:
            contract_type_raw = contract_elements[composition_id].get("figmaType")
            contract_type = contract_type_raw.upper() if isinstance(contract_type_raw, str) else ""
            if expected_type and contract_type != expected_type:
                errors.append(
                    f"{label} expects {expected_type}, but composition contract {composition_id!r} declares {contract_type_raw!r}"
                )

        if expected_type == "IMAGE":
            image_route_count += 1

    for contract_id, element in contract_elements.items():
        resource_id = element.get("resourceId")
        if resource_id is not None and resource_id not in manifest_ids:
            errors.append(
                f"Composition contract element {contract_id!r} references missing resourceId={resource_id!r}"
            )

    unexpected_dom_ids = sorted(set(parser.resource_nodes) - manifest_ids)
    if unexpected_dom_ids:
        errors.append(
            f"HTML contains data-resource-id values missing from the resource manifest: {unexpected_dom_ids}"
        )

    metrics.update(
        {
            "resource_manifest": str(manifest_path),
            "composition_contract": str(contract_path),
            "resource_manifest_schema_version": manifest.get("schemaVersion"),
            "resource_manifest_asset_count": len(assets),
            "resource_manifest_image_route_count": image_route_count,
            "resource_manifest_complex_route_count": complex_route_count,
        }
    )


def run(
    html_path: Path,
    offline: bool = False,
    manifest_path: Path | None = None,
    contract_path: Path | None = None,
) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, object] = {}

    if not html_path.is_file():
        return {"ok": False, "errors": [f"HTML not found: {html_path}"], "warnings": [], "metrics": {}}

    source = html_path.read_text(encoding="utf-8")
    parser = CaptureHTMLParser()
    parser.feed(source)

    if (manifest_path is None) != (contract_path is None):
        errors.append("--manifest and --contract must be provided together")
    elif manifest_path is not None and contract_path is not None:
        validate_resource_manifest(
            manifest_path,
            contract_path,
            parser,
            errors,
            warnings,
            metrics,
        )

    if offline and parser.capture_script_found:
        errors.append("Self-contained capture HTML must not statically load the official remote capture script")
    elif offline and not parser.dual_capture_loader_found:
        errors.append("Self-contained capture HTML is missing data-dual-capture-loader='ready'")
    elif not offline and not (parser.capture_script_found or parser.dual_capture_loader_found):
        errors.append(f"Missing official capture script or dual capture loader: {CAPTURE_SCRIPT}")

    if parser.dual_capture_loader_found:
        for required_fragment in (
            CAPTURE_SCRIPT,
            'window.location.protocol === "http:"',
            'hash.has("figmacapture")',
            'hash.has("figmaendpoint")',
        ):
            if required_fragment not in source:
                errors.append(
                    f"Dual capture loader is missing required conditional fragment: {required_fragment}"
                )
    if not parser.canvas_found:
        errors.append('Missing root canvas element with id="canvas"')
    elif not parser.canvas_first_child or parser.canvas_first_child[0] != "img":
        errors.append('The first direct child of #canvas must be the pure background <img>')
    else:
        bg_attrs = parser.canvas_first_child[1]
        bg_identity = " ".join(
            bg_attrs.get(key, "") for key in ("class", "alt", "name", "data-layer", "data-name")
        ).lower()
        if not any(marker in bg_identity for marker in ("背景", "background", " bg", "bg ")):
            warnings.append("The first #canvas <img> is not clearly named as the pure background layer")

    if offline:
        if parser.body_attrs.get("data-offline-capture") != "ready":
            errors.append('Self-contained HTML body must declare data-offline-capture="ready"')
        if parser.body_attrs.get("data-capture-artifact") != "dual-mode":
            errors.append('Self-contained HTML body must declare data-capture-artifact="dual-mode"')
        try:
            canvas_width = int(parser.body_attrs.get("data-canvas-width", ""))
            canvas_height = int(parser.body_attrs.get("data-canvas-height", ""))
            if canvas_width <= 0 or canvas_height <= 0:
                raise ValueError
        except ValueError:
            canvas_width = 0
            canvas_height = 0
            errors.append("Self-contained HTML body must declare positive integer canvas dimensions")

        expected_bounds_marker = f'data-offline-capture-bounds="{canvas_width}x{canvas_height}"'
        if not canvas_width or expected_bounds_marker not in source:
            errors.append("Self-contained HTML is missing the exact html/body/#canvas bounds style marker")
        expected_dual_bounds_marker = f'data-dual-capture-bounds="{canvas_width}x{canvas_height}"'
        if not canvas_width or expected_dual_bounds_marker not in source:
            errors.append("Self-contained HTML is missing the exact dual capture bounds marker")

        for tag, attr, value in parser.dependencies:
            if tag == "a" and attr == "href":
                continue
            if value.startswith(("data:", "#")):
                continue
            errors.append(
                f"Self-contained HTML contains an external/local dependency in <{tag}> {attr}: {value}"
            )

        hugeicon_hosts = sum(tag != "svg" for tag, _ in parser.icon_nodes)
        inline_hugeicon_svgs = sum(tag == "svg" for tag, _ in parser.icon_nodes)
        if hugeicon_hosts and inline_hugeicon_svgs < hugeicon_hosts:
            errors.append(
                "Self-contained HTML must pre-render every Hugeicons host as a traceable inline SVG"
            )
    else:
        canvas_width = 0
        canvas_height = 0

    layout_version = parser.canvas_attrs.get("data-figma-layout-version", "").strip()
    if layout_version and layout_version != "2":
        errors.append(f"Unsupported data-figma-layout-version={layout_version!r}; expected '2'")
    if layout_version == "2":
        if manifest_path is None or contract_path is None:
            errors.append(
                "V2 pages require --manifest resource-manifest.json and --contract composition-contract.json"
            )
        if parser.canvas_attrs.get("data-figma-layout", "").strip().lower() != "viewport":
            errors.append('V2 #canvas must declare data-figma-layout="viewport"')
        if parser.canvas_first_child:
            bg_classes = set(parser.canvas_first_child[1].get("class", "").split())
            if "f-bg-layer" not in bg_classes:
                errors.append("V2 pure background <img> must use class f-bg-layer")

        for tag, attrs in parser.layout_nodes:
            label = element_label(tag, attrs)
            layout = attrs.get("data-figma-layout", "").strip().lower()
            width_mode = attrs.get("data-figma-width", "").strip().lower()
            height_mode = attrs.get("data-figma-height", "").strip().lower()
            classes = set(attrs.get("class", "").split())

            if layout not in LAYOUT_VALUES:
                errors.append(f"{label} has invalid data-figma-layout={layout!r}")
                continue
            expected_class = LAYOUT_CLASSES[layout]
            if expected_class not in classes:
                errors.append(f"{label} layout={layout!r} must use class {expected_class}")
            if width_mode not in SIZING_VALUES:
                errors.append(
                    f"{label} must declare data-figma-width as fixed/hug/fill"
                )
            if height_mode not in SIZING_VALUES:
                errors.append(
                    f"{label} must declare data-figma-height as fixed/hug/fill"
                )

        flow_layout_count = sum(
            attrs.get("data-figma-layout", "").strip().lower() in {"row", "column", "wrap"}
            for _, attrs in parser.layout_nodes
        )
        if flow_layout_count == 0:
            warnings.append("V2 page has no row/column/wrap containers; confirm the page is intentionally layered")

        for tag, attrs in parser.icon_nodes:
            classes = set(attrs.get("class", "").split())
            if "f-icon" not in classes and not has_inline_size(attrs):
                errors.append(
                    f"{element_label(tag, attrs)} V2 icon must use class f-icon or explicit width/height"
                )
    elif parser.layout_nodes:
        warnings.append(
            "Layout semantics are present without data-figma-layout-version=2; V2 checks were skipped"
        )

    errors.extend(parser.icon_errors)
    errors.extend(parser.rectangle_errors)
    errors.extend(parser.node_type_errors)

    checked: set[Path] = set()
    css_sources: list[tuple[str, Path | None, str]] = [("inline CSS", html_path.parent, "\n".join(parser.inline_css))]
    for tag, _attr, value in parser.dependencies:
        local_path = resolve_local(html_path.parent, value)
        if local_path is None:
            continue
        if local_path in checked:
            continue
        checked.add(local_path)
        if not local_path.exists():
            errors.append(f"Missing local dependency from <{tag}>: {value} -> {local_path}")
            continue
        if local_path.suffix.lower() == ".css":
            css_sources.append((str(local_path), local_path.parent, local_path.read_text(encoding="utf-8")))

    for label, base, css in css_sources:
        for asset in inspect_css(label, css, warnings, metrics):
            if offline and asset and not asset.startswith(("data:", "#")):
                errors.append(f"Self-contained CSS dependency from {label} is not embedded: {asset}")
                continue
            if base is None:
                continue
            local_asset = resolve_local(base, asset)
            if local_asset is not None and not local_asset.exists():
                errors.append(f"Missing CSS dependency from {label}: {asset} -> {local_asset}")

    metrics.update(
        {
            "html": str(html_path),
            "capture_mode": (
                "dual-mode-file-or-plugin"
                if offline and parser.dual_capture_loader_found
                else "offline-plugin"
                if offline
                else "dual-mode-http"
                if parser.dual_capture_loader_found
                else "official-http"
            ),
            "offline_canvas": (
                {"width": canvas_width, "height": canvas_height} if offline else None
            ),
            "figma_layout_version": layout_version or "legacy",
            "semantic_layout_marker_count": len(parser.layout_nodes),
            "semantic_layout_counts": {
                layout: sum(
                    attrs.get("data-figma-layout", "").strip().lower() == layout
                    for _, attrs in parser.layout_nodes
                )
                for layout in sorted(LAYOUT_VALUES)
            },
            "local_dependency_count": len(checked),
            "icon_library_marker_count": parser.icon_count,
            "rectangle_semantic_marker_count": parser.rectangle_count,
            "figma_node_type_counts": dict(sorted(parser.node_type_counts.items())),
        }
    )
    return {"ok": not errors, "errors": errors, "warnings": warnings, "metrics": metrics}


def main() -> int:
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("html", type=Path, help="Absolute or relative path to the final HTML")
    arg_parser.add_argument(
        "--offline",
        action="store_true",
        help="Validate the self-contained/file-plugin mode of a dual capture artifact",
    )
    arg_parser.add_argument(
        "--manifest",
        type=Path,
        help="Validate a schema v3 resource-manifest.json against the HTML",
    )
    arg_parser.add_argument(
        "--contract",
        type=Path,
        help="Validate the matching composition-contract.json against the resource manifest",
    )
    args = arg_parser.parse_args()
    result = run(
        args.html.expanduser().resolve(),
        offline=args.offline,
        manifest_path=args.manifest.expanduser().resolve() if args.manifest else None,
        contract_path=args.contract.expanduser().resolve() if args.contract else None,
    )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
