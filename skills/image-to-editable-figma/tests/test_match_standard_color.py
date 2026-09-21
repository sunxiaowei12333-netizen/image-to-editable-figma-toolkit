import importlib.util
import pathlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "match_standard_color.py"
SPEC = importlib.util.spec_from_file_location("match_standard_color", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class MatchStandardColorTests(unittest.TestCase):
    def test_ciede2000_matches_published_reference_pair(self):
        delta = MODULE.delta_e_2000(
            (50.0, 2.6772, -79.7751),
            (50.0, 0.0, -82.7485),
        )
        self.assertAlmostEqual(delta, 2.0425, places=4)

    def test_exact_standard_color_is_kept_as_standard(self):
        result = MODULE.evaluate("#333333", "#FFFFFF")
        self.assertEqual(result["action"], "use-standard")
        self.assertEqual(result["targetHex"], "#333333")
        self.assertEqual(result["deltaE00"], 0.0)

    def test_close_brand_orange_maps_to_standard(self):
        result = MODULE.evaluate("#F36E00", "#FFF3EB")
        self.assertEqual(result["action"], "use-standard")
        self.assertEqual(result["nearestStandard"]["hex"], "#FF7400")

    def test_distinct_brown_red_is_preserved(self):
        result = MODULE.evaluate("#8B2E0F", "#F4D49A")
        self.assertEqual(result["action"], "preserve-reference")
        self.assertEqual(result["targetHex"], "#8B2E0F")
        self.assertEqual(result["method"], "reference-preserved")

    def test_invalid_hex_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.evaluate("not-a-color")


class BoundedMatchingTests(unittest.TestCase):
    def assert_target(self, source, target, background="#302A25"):
        result = MODULE.evaluate(source, background)
        self.assertEqual(result["targetHex"], target, result)
        return result

    def test_discussed_examples(self):
        for source, target in [("#F0E3CD", "#FFFFFF"), ("#EC9E59", "#FF7400"), ("#E5C37F", "#FFB122")]:
            with self.subTest(source=source):
                result = self.assert_target(source, target)
                self.assertEqual(result["matchedStandard"]["hex"], target)

    def test_near_black_default_includes_black_and_warm_black(self):
        for source in ["#000000", "#111111", "#222222", "#242424", "#303030", "#17130F"]:
            with self.subTest(source=source):
                self.assert_target(source, "#333333", "#BDAB90")

    def test_near_black_does_not_override_unreadable_background(self):
        result = self.assert_target("#000000", "#000000", "#222222")
        self.assertIn("contrast-drop", result["guardFailures"])

    def test_all_existing_tokens_stable_except_explicit_near_black_rule(self):
        for color in MODULE.PALETTE.values():
            with self.subTest(color=color):
                expected = "#333333" if color == "#222222" else color
                self.assert_target(color, expected, None)

    def test_gray_uses_all_eight_levels(self):
        result = MODULE.evaluate("#DDDDDD", "#222222")
        self.assertEqual(result["candidateCount"], 9)  # 8 grays + white
        self.assertEqual(result["targetHex"], "#E5E5E5")

    def test_gray_retries_other_candidates_in_same_call(self):
        result = self.assert_target("#7F7F7F", "#999999", "#222222")
        self.assertEqual(result["decisionFamily"], "neutral")
        self.assertTrue(result["contrastGuard"]["passed"])
        self.assertGreaterEqual(result["contrastGuard"]["target"], result["contrastGuard"]["reference"])

    def test_gray_midpoints_and_highlights_do_not_all_turn_white(self):
        for source, target in [("#B5B5B5", "#CCCCCC"), ("#DEDEDE", "#E5E5E5"), ("#F0F0F0", "#F4F4F4"), ("#F7F7F7", "#F8F8F8")]:
            with self.subTest(source=source): self.assert_target(source, target, "#222222")

    def test_no_forcing_brown_blue_or_unsupported_families(self):
        for source in ["#8B2E0F", "#142D50", "#758B99", "#8844BB", "#00B5C8", "#CCBCA2", "#E5D6BB", "#372314", "#101020"]:
            with self.subTest(source=source):self.assert_target(source, source)

    def test_contrast_improvement_on_light_background_allowed(self):
        # Previous timing fixture assumed preservation without a user label.
        # Actual behavior should depend on measured contrast, not the label.
        result = self.assert_target("#EC9E59", "#FF7400", "#FFFFFF")
        self.assertGreater(result["contrastGuard"]["target"], result["contrastGuard"]["reference"])

    def test_missing_background_is_not_reported_as_checked(self):
        result = self.assert_target("#EC9E59", "#FF7400", None)
        self.assertIsNone(result["contrastGuard"])
        self.assertTrue(result["requiresVisualReview"])

    def test_color_format_and_background_validation(self):
        self.assertEqual(MODULE.evaluate("fff")["targetHex"], "#FFFFFF")
        with self.assertRaises(ValueError):MODULE.evaluate("#FFFFFF", "bad-background")

    def test_selected_candidate_obeys_declared_guards_on_fixed_random_inputs(self):
        import random
        rng = random.Random(9020)
        for _ in range(500):
            source = "#{:06X}".format(rng.randrange(0x1000000))
            background = rng.choice(["#FFFFFF", "#222222", "#BDAB90"])
            result = MODULE.evaluate(source, background)
            if result["action"] == "use-standard":
                self.assertIn(result["targetHex"], MODULE.PALETTE.values())
                self.assertEqual(result["guardFailures"], [])
                self.assertTrue(result["contrastGuard"]["passed"])
                if result["decisionFamily"] not in {"near-black", "exact-standard"}:
                    self.assertLessEqual(result["lightnessDelta"], 12.0001)
                    self.assertLessEqual(result["deltaE00"], 15.0001)
            else:self.assertEqual(result["targetHex"], source)


if __name__ == "__main__":
    unittest.main()
