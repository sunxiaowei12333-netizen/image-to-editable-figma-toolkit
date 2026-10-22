"""Behavioral regression tests for evidence gates, using actual PNG decoding."""
import hashlib
import json
import tempfile
import unittest
import copy
from pathlib import Path

from PIL import Image, ImageDraw
from verify_component_evidence import validate

RUN = "01a15767-9659-77d0-babe-302c9eedf22f"


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        Image.new("RGBA", (4, 4), (255, 255, 255, 255)).save(self.root / "before.png")
        Image.new("RGBA", (4, 4), (255, 255, 255, 255)).save(self.root / "after.png")
        self.inventory = {"runId": RUN, "families": [
            {"id": "button", "required": True, "sourceNodeIds": ["s-text"],
             "initialDisposition": "required", "rationale": "two equivalent buttons"}]}
        self.outcomes = {"runId": RUN, "families": [{"id": "button", "status": "componentized"}]}
        roots = [{"id": k, "width": 4, "height": 4, "clipsContent": True,
                  "overflowDirection": "NONE"} for k in ("source", "copy")]
        text = {"characters": "领取", "fontName": {"family": "F", "style": "R"},
                "fontSize": 16, "lineHeight": {"unit": "AUTO"},
                "letterSpacing": {"unit": "PIXELS", "value": 0},
                "textStyleId": "", "fillStyleId": "", "fills": [], "boundVariables": {},
                "geometry": {"width": 32, "height": 22}}
        self.before = {"runId": RUN, "roots": roots, "nodes": [
            {"id": "old", "kind": "TEXT", "preserved": copy.deepcopy(text)}]}
        self.after = {"runId": RUN, "roots": roots, "nodes": [
            {"id": "new", "kind": "TEXT", "preserved": copy.deepcopy(text)}]}
        self.data = {"schemaVersion": 2, "runId": RUN,
                     "rootMappings": [{"sourceId": "source", "copyId": "copy"}],
                     "nodeMappings": [{"beforeId": "old", "afterId": "new"}]}
        self.write()

    def ref(self, name):
        return {"path": name, "sha256": hashlib.sha256((self.root / name).read_bytes()).hexdigest()}

    def write(self):
        for name in ("inventory", "outcomes", "before", "after"):
            (self.root / f"{name}.json").write_text(json.dumps(getattr(self, name)))
            self.data[name] = self.ref(f"{name}.json")
        roles = ("final",) if self.data.get("editMode") == "in-place" else ("source", "baseline", "final")
        self.data["images"] = [
            {**root, "role": role,
             "before": self.ref("before.png"), "after": self.ref("after.png")}
            for root in self.data["rootMappings"] for role in roles]
        self.flush()

    def use_in_place(self, target="target"):
        self.data["editMode"] = "in-place"
        self.data["rootMappings"] = [{"sourceId": target, "copyId": target}]
        for offset, snapshot in enumerate((self.before, self.after)):
            snapshot.update(baselineId="baseline-1", capturedAt=1792470000000 + offset)
            root = copy.deepcopy(snapshot["roots"][0])
            root.update(id=target, parentId="page", index=0, x=10, y=20)
            snapshot["roots"] = [root]
        self.write()

    def flush(self):
        (self.root / "evidence.json").write_text(json.dumps(self.data))

    def check(self):
        return validate(self.root / "evidence.json")

    def test_identical_actual_evidence_passes(self):
        self.assertEqual(self.check()["status"], "complete")

    def test_in_place_passes_without_copy_or_source_images(self):
        self.use_in_place()
        result = self.check()
        self.assertEqual(result["status"], "complete", result)
        self.assertEqual(len(result["comparisons"]), 1)

    def test_in_place_does_not_waive_visual_or_property_checks(self):
        self.use_in_place()
        im = Image.open(self.root / "after.png")
        im.putpixel((1, 1), (0, 0, 0, 255))
        im.save(self.root / "after.png")
        self.write()
        self.assertEqual(self.check()["status"], "incomplete")
        Image.new("RGBA", (4, 4), "white").save(self.root / "after.png")
        self.after["nodes"][0]["preserved"]["fontName"]["style"] = "Bold"
        self.write()
        self.assertEqual(self.check()["status"], "incomplete")

    def test_in_place_rejects_missing_or_mismatched_identity_and_time(self):
        for field, value in (("baselineId", ""), ("baselineId", "other"),
                             ("capturedAt", None), ("capturedAt", True),
                             ("capturedAt", float("nan")), ("capturedAt", 1)):
            with self.subTest(field=field, value=value):
                self.use_in_place()
                self.after[field] = value
                self.write()
                self.assertEqual(self.check()["status"], "invalid")

    def test_in_place_rejects_duplicate_target_or_missing_final_image(self):
        self.use_in_place()
        self.data["rootMappings"] *= 2
        self.write()
        self.assertEqual(self.check()["status"], "invalid")
        self.use_in_place()
        self.data["images"] = []
        self.flush()
        self.assertEqual(self.check()["status"], "invalid")

    def test_in_place_rejects_root_replacement_and_reparenting(self):
        self.use_in_place()
        self.data["rootMappings"][0]["copyId"] = "replacement"
        self.flush()
        self.assertEqual(self.check()["status"], "invalid")
        for field, value in (("parentId", "other-page"), ("index", 2),
                             ("x", 20), ("width", 5), ("clipsContent", False)):
            with self.subTest(field=field):
                self.use_in_place()
                self.after["roots"][0][field] = value
                self.write()
                self.assertEqual(self.check()["status"], "incomplete")

    def test_safe_copy_cannot_claim_same_root_as_independent_copy(self):
        self.use_in_place()
        self.data["editMode"] = "safe-copy"
        self.write()
        self.assertEqual(self.check()["status"], "invalid")

    def test_one_changed_pixel_cannot_be_reported_as_antialias_pass(self):
        im = Image.open(self.root / "after.png")
        im.putpixel((1, 1), (254, 255, 255, 255))
        im.save(self.root / "after.png")
        self.write()
        self.assertEqual(self.check()["status"], "incomplete")
        self.assertEqual(self.check()["comparisons"][0]["differentPixels"], 1)

    def test_required_failure_cannot_disappear_as_skip(self):
        self.outcomes["families"][0].update(status="not-applicable", reason="render failed")
        self.write()
        self.assertNotEqual(self.check()["status"], "complete")

    def test_omitted_candidate_is_invalid(self):
        self.outcomes["families"] = []
        self.write()
        self.assertEqual(self.check()["status"], "invalid")

    def test_rollback_does_not_complete_required_work(self):
        self.outcomes["families"][0]["status"] = "blocked"
        self.write()
        self.assertEqual(self.check()["status"], "incomplete")

    def test_font_change_blocks_even_with_identical_png(self):
        self.after["nodes"][0]["preserved"]["fontName"]["style"] = "Bold"
        self.write()
        self.assertEqual(self.check()["status"], "incomplete")

    def test_unmapped_new_master_text_is_invalid(self):
        self.after["nodes"].append({"id": "master-text", "preserved": {"characters": "领取"}})
        self.write()
        self.assertEqual(self.check()["status"], "invalid")

    def test_changed_file_without_new_hash_is_invalid(self):
        (self.root / "after.json").write_text("{}")
        self.assertEqual(self.check()["status"], "invalid")

    def test_other_run_evidence_rejected(self):
        self.outcomes["runId"] = "01a1585d-8947-7873-9afb-f5dc26fc6533"
        self.write()
        self.assertEqual(self.check()["status"], "invalid")

    def test_missing_source_protection_comparison_rejected(self):
        self.data["images"] = self.data["images"][1:]
        self.flush()
        self.assertEqual(self.check()["status"], "invalid")

    def test_alpha_only_difference_is_detected(self):
        im = Image.open(self.root / "after.png")
        im.putpixel((1, 1), (255, 255, 255, 254))
        im.save(self.root / "after.png")
        self.write()
        self.assertEqual(self.check()["comparisons"][0]["differentPixels"], 1)

    def test_self_reported_unchanged_is_not_a_property_snapshot(self):
        for snapshot in (self.before, self.after):
            snapshot["nodes"][0]["preserved"] = {"unchanged": True}
        self.write()
        self.assertEqual(self.check()["status"], "invalid")


    def minor_fixture(self):
        size=(64,24)
        ta=Image.new("RGBA",size,(0,0,0,0))
        ImageDraw.Draw(ta).rectangle((5,6,58,17),fill=(0,0,0,255))
        tb=ta.copy();tb.putpixel((5,8),(0,0,0,240))
        ta.save(self.root/"ink-before.png");tb.save(self.root/"ink-after.png")
        bg=Image.new("RGBA",size,"white")
        Image.alpha_composite(bg,ta).save(self.root/"before.png")
        Image.alpha_composite(bg,tb).save(self.root/"after.png")
        for snap in (self.before,self.after):
            for r in snap["roots"]:r.update(width=64,height=24)
            snap["nodes"][0]["preserved"]["geometry"]={"width":64,"height":24,"rootX":0,"rootY":0}
        self.data["visualPolicy"]="text-edge-v1"
        self.write()
        for image in self.data["images"]:
            if image["role"]!="final": image["after"]=self.ref("before.png")
            else: image["textRegions"]=[{"beforeId":"old","afterId":"new",
                "rect":{"x":0,"y":0,"width":64,"height":24},
                "before":self.ref("ink-before.png"),"after":self.ref("ink-after.png")}]
        self.flush()

    def test_minor_text_edge_continues_with_warning(self):
        self.minor_fixture();r=self.check()
        self.assertEqual(r["status"],"complete")
        self.assertEqual(len(r["warnings"]),1)
        self.assertTrue(r["comparisons"][-1]["acceptedMinorTextDifference"])

    def test_minor_policy_never_hides_source_mutation(self):
        self.minor_fixture()
        self.data["images"][0]["after"]=self.ref("after.png");self.flush()
        self.assertEqual(self.check()["status"],"incomplete")

    def test_minor_policy_never_hides_safe_copy_mutation(self):
        self.minor_fixture()
        self.data["images"][1]["after"]=self.ref("after.png");self.flush()
        self.assertEqual(self.check()["status"],"incomplete")

    def test_background_pixel_inside_text_rectangle_is_rejected(self):
        self.minor_fixture();im=Image.open(self.root/"after.png")
        im.putpixel((1,1),(254,255,255,255));im.save(self.root/"after.png")
        self.data["images"][-1]["after"]=self.ref("after.png");self.flush()
        self.assertEqual(self.check()["status"],"incomplete")

    def test_minor_policy_cannot_hide_font_change(self):
        self.minor_fixture();self.after["nodes"][0]["preserved"]["fontName"]["style"]="Bold"
        (self.root/"after.json").write_text(json.dumps(self.after));self.data["after"]=self.ref("after.json");self.flush()
        self.assertNotEqual(self.check()["status"],"complete")

    def test_minor_policy_cannot_hide_position_change(self):
        self.minor_fixture();self.after["nodes"][0]["preserved"]["geometry"]["rootX"]=1
        (self.root/"after.json").write_text(json.dumps(self.after));self.data["after"]=self.ref("after.json");self.flush()
        self.assertNotEqual(self.check()["status"],"complete")

    def test_protected_fonts_are_not_auto_accepted(self):
        self.minor_fixture();self.before["nodes"][0]["protectedFont"]=True
        (self.root/"before.json").write_text(json.dumps(self.before));self.data["before"]=self.ref("before.json");self.flush()
        self.assertNotEqual(self.check()["status"],"complete")

    def test_large_ink_change_rejected(self):
        from text_edge_policy import inspect_text_pair
        a=Image.new("RGBA",(64,24),(0,0,0,0));b=a.copy()
        ImageDraw.Draw(a).rectangle((5,6,58,17),fill=(0,0,0,255))
        ImageDraw.Draw(b).rectangle((3,4,60,19),fill=(0,0,0,255))
        self.assertFalse(inspect_text_pair(a,b)[1]["accepted"])

    def test_same_shape_color_change_rejected(self):
        from text_edge_policy import inspect_text_pair
        a=Image.new("RGBA",(64,24),(0,0,0,0));b=a.copy()
        ImageDraw.Draw(a).rectangle((5,6,58,17),fill=(0,0,0,255))
        ImageDraw.Draw(b).rectangle((5,6,58,17),fill=(255,0,0,255))
        self.assertFalse(inspect_text_pair(a,b)[1]["accepted"])


    def add_master_fixture(self):
        layout={"geometry":{"width":4,"height":4},"layoutMode":"NONE","clipsContent":False}
        self.before["nodes"].append({"id":"old-layout","kind":"LAYOUT","nodeType":"FRAME","preserved":copy.deepcopy(layout)})
        self.after["nodes"].append({"id":"master","kind":"LAYOUT","nodeType":"COMPONENT","preserved":copy.deepcopy(layout)})
        text=copy.deepcopy(self.after["nodes"][0]);text["id"]="master-text"
        text["preserved"]["geometry"].update(rootX=20,rootY=30)
        self.after["nodes"].append(text)
        self.after["componentAssets"]=[{"id":"master","descendantIds":["master-text"]}]
        self.data["nodeMappings"] += [
            {"beforeId":"old-layout","afterId":"master","role":"master-preview"},
            {"beforeId":"old","afterId":"master-text","role":"master-preview"}]
        self.write()

    def test_master_text_snapshot_required(self):
        self.add_master_fixture()
        self.after["nodes"]=[n for n in self.after["nodes"] if n["id"]!="master-text"]
        self.data["nodeMappings"]=[m for m in self.data["nodeMappings"] if m["afterId"]!="master-text"]
        self.write()
        self.assertEqual(self.check()["status"],"invalid")

    def test_preview_relocation_does_not_fail_text_preservation(self):
        self.add_master_fixture()
        self.assertEqual(self.check()["status"],"complete")

    def test_preview_cannot_hide_master_font_change(self):
        self.add_master_fixture()
        self.after["nodes"][-1]["preserved"]["fontName"]["style"]="Bold";self.write()
        self.assertEqual(self.check()["status"],"incomplete")

    def test_page_instance_cannot_claim_preview_role(self):
        self.data["nodeMappings"][0]["role"]="master-preview";self.write()
        self.assertEqual(self.check()["status"],"invalid")


if __name__ == "__main__":
    unittest.main()
