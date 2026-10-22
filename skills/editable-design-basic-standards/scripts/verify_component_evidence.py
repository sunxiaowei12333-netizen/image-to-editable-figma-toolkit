#!/usr/bin/env python3
"""Read actual third-stage evidence. Exit 0 pass, 1 invalid evidence, 2 blocked.

SCHEMA (all refs include path relative to manifest and SHA-256):
{
 "schemaVersion":2, "runId":"full UUID", "editMode":"in-place|safe-copy",
 "inventory":ref, "outcomes":ref, "before":ref, "after":ref,
 "rootMappings":[{"sourceId":"1:1","copyId":"2:1"}],
 "images":[{"sourceId":"1:1","copyId":"2:1","role":"source|baseline|final",
            "before":ref,"after":ref,"textRegions":[]}],
 "nodeMappings":[{"beforeId":"2:4","afterId":"3:7"}]
}
inventory: {runId, families:[{id,sourceNodeIds,required,rationale,initialDisposition}]}
outcomes: {runId, families:[{id,status,reason}]}
before/after: {runId, nodes:[{id,kind:"TEXT|LAYOUT|PAINT",preserved:{...actual fields...}}],
 roots:[{id,width,height,clipsContent,overflowDirection}]}
All snapshot nodes are the affected scope (incl. new masters and instances).
New runs explicitly set editMode. Omission supports historical safe-copy evidence.
In-place rootMappings use the same sourceId/copyId (the linked target root),
require only final images, and before/after snapshots carry the same nonempty
baselineId and increasing capturedAt (Unix milliseconds). In-place roots also
include parentId/index/x/y, which remain unchanged.
Optional manifest visualPolicy="text-edge-v1" enables fixed minor text differences
on final images only. A textRegions entry is {beforeId,afterId,rect:{x,y,width,height},
before:PNGref,after:PNGref}. Isolated transparent text PNGs are padded to the same
root-pixel rectangle, preserving their actual export offset. Snapshots must include
geometry.rootX/rootY and actual matching typography/Paint. No source/baseline tolerance.
After LAYOUT nodes include actual nodeType; after.componentAssets lists each new
component {id,descendantIds:[all actual visible descendant IDs]}. All descendants
require after snapshots and mappings. Only role="master-preview" mappings may
ignore new rootX/rootY placement; page instances never use this role.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import uuid
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops
from text_edge_policy import PROFILE, inspect_text_pair, covered_difference_count


def validate(path: Path) -> dict:
    errors, blockers, warnings = [], [], []
    result = {"errors": errors, "blockers": blockers, "warnings": warnings, "comparisons": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schemaVersion") != 2:
            raise ValueError("schemaVersion must be 2")
        run_id = data["runId"]
        uuid.UUID(run_id)
        edit_mode = data.get("editMode", "safe-copy")
        if edit_mode not in {"in-place", "safe-copy"}:
            raise ValueError("editMode must be in-place or safe-copy")
        result["editMode"] = edit_mode

        def read_ref(ref, as_json=True):
            p = (path.parent / ref["path"]).resolve()
            raw = p.read_bytes()
            if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
                raise ValueError(f"SHA-256 mismatch: {p.name}")
            if not as_json:
                return p
            obj = json.loads(raw)
            if obj.get("runId") != run_id:
                raise ValueError(f"runId mismatch: {p.name}")
            return obj

        def index(rows, label):
            if not isinstance(rows, list):
                raise ValueError(f"{label} must be an array")
            out = {}
            for row in rows:
                key = row["id"]
                if not isinstance(key, str) or not key or key in out:
                    raise ValueError(f"{label}: invalid/duplicate id")
                out[key] = row
            return out

        inventory = index(read_ref(data["inventory"])["families"], "inventory")
        outcomes = index(read_ref(data["outcomes"])["families"], "outcomes")
        if set(inventory) != set(outcomes):
            errors.append("candidate IDs differ between frozen inventory and outcomes")
        statuses = Counter()
        allowed = {"componentized", "already-componentized", "not-applicable",
                   "excluded-by-user", "blocked", "pending"}
        for key, family in inventory.items():
            if type(family.get("required")) is not bool:
                errors.append(f"{key}: required must be boolean")
            if not family.get("sourceNodeIds") or not family.get("rationale"):
                errors.append(f"{key}: missing source nodes or rationale")
            initial = family.get("initialDisposition")
            if initial not in {"required", "already-componentized", "not-applicable",
                               "excluded-by-user"}:
                errors.append(f"{key}: invalid initialDisposition")
            status = outcomes.get(key, {}).get("status")
            if status not in allowed:
                errors.append(f"{key}: invalid outcome status")
                continue
            statuses[status] += 1
            if status in {"blocked", "pending"}:
                blockers.append(f"{key}: {status}")
            if family.get("required") and status not in {"componentized", "already-componentized"}:
                blockers.append(f"{key}: required candidate is not completed")
            if status in {"not-applicable", "excluded-by-user"}:
                if initial != status or not outcomes[key].get("reason"):
                    errors.append(f"{key}: outcome exclusion not established before mutation")
        result["candidateCoverage"] = {
            "total": len(inventory), "componentized": statuses["componentized"],
            "alreadyComponentized": statuses["already-componentized"],
            "skippedWithReason": statuses["not-applicable"] + statuses["excluded-by-user"],
            "unclassified": statuses["pending"] + statuses["blocked"],
        }
        before, after = read_ref(data["before"]), read_ref(data["after"])
        if edit_mode == "in-place":
            baseline = before.get("baselineId")
            if not isinstance(baseline, str) or not baseline.strip() or after.get("baselineId") != baseline:
                errors.append("in-place snapshots require the same nonempty baselineId")
            timestamps = [snapshot.get("capturedAt") for snapshot in (before, after)]
            if any(type(t) not in (int, float) or not math.isfinite(t) or t <= 0 for t in timestamps):
                errors.append("in-place snapshots require finite positive capturedAt timestamps")
            elif timestamps[1] <= timestamps[0]:
                errors.append("in-place after.capturedAt must follow before.capturedAt")
        bn, an = index(before["nodes"], "before nodes"), index(after["nodes"], "after nodes")
        br, ar = index(before["roots"], "before roots"), index(after["roots"], "after roots")
        for phase, nodes in (("before", bn), ("after", an)):
            for node_id, node in nodes.items():
                kind, fields = node.get("kind"), node.get("preserved")
                if kind not in {"TEXT", "LAYOUT", "PAINT"} or not isinstance(fields, dict):
                    errors.append(f"{phase}/{node_id}: actual typed property snapshot required")
                    continue
                geometry = fields.get("geometry")
                if not isinstance(geometry, dict) or any(
                    type(geometry.get(k)) not in (int, float) for k in ("width", "height")
                ):
                    errors.append(f"{phase}/{node_id}: numeric width/height geometry required")
                required = {
                    "TEXT": {"characters", "fontName", "fontSize", "lineHeight", "letterSpacing",
                             "textStyleId", "fillStyleId", "fills", "boundVariables"},
                    "LAYOUT": {"layoutMode", "clipsContent"},
                    "PAINT": {"fills", "strokes", "fillStyleId", "strokeStyleId", "boundVariables"},
                }[kind]
                if not required <= set(fields):
                    errors.append(f"{phase}/{node_id}: missing raw {kind} properties")
        assets = index(after.get("componentAssets", []), "component assets")
        for node_id,node in an.items():
            if node.get("kind") == "LAYOUT" and node.get("nodeType") not in {
                "FRAME","GROUP","INSTANCE","COMPONENT","COMPONENT_SET","SECTION"
            }:
                errors.append(f"after/{node_id}: actual nodeType is required for layout snapshots")
            if node.get("nodeType") in {"COMPONENT","COMPONENT_SET"} and node_id not in assets:
                errors.append(f"{node_id}: missing component descendant inventory")
        asset_descendants=set()
        for asset_id,asset in assets.items():
            if asset_id not in an or an[asset_id].get("nodeType") not in {"COMPONENT","COMPONENT_SET"}:
                errors.append(f"{asset_id}: component asset not present as an actual component snapshot")
            descendants=asset.get("descendantIds")
            if not isinstance(descendants,list) or len(descendants)!=len(set(descendants)):
                errors.append(f"{asset_id}: descendantIds array required")
                continue
            asset_descendants.update(descendants)
            if not set(descendants)<=set(an):
                errors.append(f"{asset_id}: component descendants omitted from final snapshots")
        seen_before, seen_after = set(), set()
        pairs = set()
        for mapping in data["nodeMappings"]:
            old, new = mapping["beforeId"], mapping["afterId"]
            if (old, new) in pairs:
                errors.append("duplicate node mapping")
            pairs.add((old, new))
            seen_before.add(old)
            seen_after.add(new)
            if bn[old].get("kind") != an[new].get("kind"):
                blockers.append(f"{old}->{new}: affected object kind changed")
            a, b = bn[old].get("preserved"), an[new].get("preserved")
            if not isinstance(a, dict) or not a or not isinstance(b, dict) or not b:
                errors.append(f"{old}->{new}: missing preserved field data")
            else:
                if mapping.get("role") == "master-preview":
                    if new not in assets and new not in asset_descendants:
                        errors.append(f"{new}: preview role is not a component asset/descendant")
                    # Preview placement is new; text layout and all other values stay protected.
                    import copy
                    a,b=copy.deepcopy(a),copy.deepcopy(b)
                    for fields in (a,b):
                        if isinstance(fields.get("geometry"),dict):
                            fields["geometry"].pop("rootX",None)
                            fields["geometry"].pop("rootY",None)
                if a != b:
                    blockers.append(f"{old}->{new}: preserved values differ")
        if seen_before != set(bn) or seen_after != set(an):
            errors.append("nodeMappings do not cover affected snapshot nodes")
        result["affectedBeforeIds"] = sorted(bn)
        result["affectedAfterIds"] = sorted(an)

        roots = {(r["sourceId"], r["copyId"]) for r in data["rootMappings"]}
        if not roots or len(roots) != len(data["rootMappings"]):
            errors.append("rootMappings empty or duplicated")
        if len({s for s, _ in roots}) != len(roots) or len({c for _, c in roots}) != len(roots):
            errors.append("source/copy root mapping must be one-to-one")
        result["rootMappings"] = data["rootMappings"]
        boundary_fields = ("width", "height", "clipsContent", "overflowDirection")
        if edit_mode == "in-place":
            boundary_fields += ("parentId", "index", "x", "y")
            expected_roots = {s for s, _ in roots}
            if set(br) != expected_roots or set(ar) != expected_roots:
                errors.append("in-place snapshot roots must exactly match target roots")
        for source, copy in roots:
            if (source == copy) != (edit_mode == "in-place"):
                errors.append("in-place requires identical root IDs; safe-copy requires distinct IDs")
            for nodes, node_id in ((br, source), (br, copy), (ar, source), (ar, copy)):
                if node_id not in nodes or any(k not in nodes[node_id] for k in boundary_fields):
                    raise ValueError(f"missing root boundary: {node_id}")
                if edit_mode == "in-place":
                    row = nodes[node_id]
                    if (not isinstance(row["parentId"], str) or not row["parentId"]
                        or type(row["index"]) is not int or row["index"] < 0
                        or any(type(row[k]) not in (int, float) or not math.isfinite(row[k]) for k in ("x", "y"))):
                        errors.append(f"{node_id}: invalid parent/index/position snapshot")
            base = {k: br[source][k] for k in boundary_fields}
            for nodes, node_id in ((br, copy), (ar, source), (ar, copy)):
                if {k: nodes[node_id][k] for k in boundary_fields} != base:
                    blockers.append(f"{node_id}: root boundary changed")

        roles = ("final",) if edit_mode == "in-place" else ("source", "baseline", "final")
        seen_images = set()
        for item in data["images"]:
            source, copy, role = item["sourceId"], item["copyId"], item["role"]
            triple = (source, copy, role)
            if (source, copy) not in roots or role not in roles:
                errors.append("image comparison has unknown root/role")
            if triple in seen_images:
                errors.append("duplicate image comparison")
            seen_images.add(triple)
            ap, bp = read_ref(item["before"], False), read_ref(item["after"], False)
            with Image.open(ap) as ai, Image.open(bp) as bi:
                a, b = ai.convert("RGBA"), bi.convert("RGBA")
            dimensions = (br[source]["width"], br[source]["height"])
            # Native SCALE=1 exports of fractional roots round out to integer pixels.
            expected = tuple(math.ceil(v) for v in dimensions)
            if a.size != b.size or a.size != expected:
                blockers.append(f"{triple}: image dimensions differ from SCALE=1 root")
                continue
            diff = ImageChops.difference(a, b)
            count = sum(any(px) for px in diff.getdata())
            maximum = max(hi for _, hi in diff.getextrema())
            result["comparisons"].append({"sourceId": source, "copyId": copy, "role": role,
                                          "differentPixels": count, "maxChannelDiff": maximum})
            if count:
                accepted = False
                if role == "final" and data.get("visualPolicy") == PROFILE:
                    allowed_mask = Image.new("L", a.size, 0)
                    region_stats = []
                    for region in item.get("textRegions", []):
                        old, new = region["beforeId"], region["afterId"]
                        if (old,new) not in pairs or bn[old].get("kind") != "TEXT":
                            raise ValueError("text region is not an affected TEXT mapping")
                        old_fields, new_fields = bn[old]["preserved"], an[new]["preserved"]
                        if old_fields != new_fields or bn[old].get("protectedFont") or an[new].get("protectedFont"):
                            raise ValueError("text tolerance cannot cover property changes or protected fonts")
                        geometry = old_fields["geometry"]
                        if any(type(geometry.get(k)) not in (int,float) for k in ("rootX","rootY")):
                            raise ValueError("text tolerance needs actual root-relative text positions")
                        rect = region["rect"]
                        values = [rect[k] for k in ("x","y","width","height")]
                        if any(type(v) is not int for v in values):
                            raise ValueError("text region must use integer root pixels")
                        x,y,w,h = values
                        if w <= 0 or h <= 0 or x < 0 or y < 0 or x+w > a.width or y+h > a.height:
                            raise ValueError("text region falls outside root image")
                        # Prevent declaring an arbitrary canvas-sized text rectangle.
                        if (abs(x-geometry["rootX"]) > 2 or abs(y-geometry["rootY"]) > max(2,old_fields["fontSize"])
                            or w > geometry["width"]+4 or h > geometry["height"]+4):
                            raise ValueError("text ink rectangle does not correspond to actual text geometry")
                        with Image.open(read_ref(region["before"],False)) as im:
                            ta = im.convert("RGBA")
                        with Image.open(read_ref(region["after"],False)) as im:
                            tb = im.convert("RGBA")
                        if ta.size != (w,h) or tb.size != (w,h):
                            raise ValueError("text PNG dimensions differ from root rectangle")
                        edge, stats = inspect_text_pair(ta,tb)
                        region_stats.append(dict(stats,beforeId=old,afterId=new))
                        if edge is not None:
                            pasted = Image.new("L", a.size, 0)
                            pasted.paste(edge,(x,y))
                            allowed_mask = ImageChops.lighter(allowed_mask,pasted)
                    outside = covered_difference_count(a,b,allowed_mask)
                    accepted = outside == 0 and bool(region_stats) and all(r["accepted"] for r in region_stats)
                    result["comparisons"][-1].update(textRegions=region_stats,unexpectedPixels=outside,
                                                        acceptedMinorTextDifference=accepted)
                    if accepted:
                        warnings.append(f"{triple}: accepted {count} minor text-edge RGBA differences ({PROFILE})")
                if not accepted:
                    blockers.append(f"{triple}: {count} changed RGBA pixels not accepted as minor text edges")
        expected_images = {(s, c, role) for s, c in roots for role in roles}
        if seen_images != expected_images:
            errors.append(f"each root requires {', '.join(roles)} image comparisons for {edit_mode}")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        errors.append(str(exc))
    result["acceptedMinorTextDifferences"] = sum(c["differentPixels"] for c in result["comparisons"] if c.get("acceptedMinorTextDifference"))
    result["status"] = "invalid" if errors else "incomplete" if blockers else "complete"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate(args.manifest)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    raise SystemExit(1 if result["errors"] else 2 if result["blockers"] else 0)


if __name__ == "__main__":
    main()
