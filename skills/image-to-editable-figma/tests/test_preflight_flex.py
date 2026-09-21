import unittest

from scripts.preflight_html import CaptureHTMLParser


class FixedFlexPreflightTests(unittest.TestCase):
    def parse(self, body: str) -> CaptureHTMLParser:
        parser = CaptureHTMLParser()
        parser.feed(body)
        return parser

    def test_column_fixed_height_requires_f_fixed(self):
        parser = self.parse(
            '<div class="f-column" data-figma-layout="column">'
            '<button class="f-row" data-figma-layout="row" '
            'data-figma-width="fixed" data-figma-height="fixed"></button>'
            '</div>'
        )
        self.assertEqual(parser.fixed_flex_checked_count, 1)
        self.assertEqual(len(parser.fixed_flex_errors), 1)
        self.assertIn("must use class f-fixed", parser.fixed_flex_errors[0])

    def test_canonical_f_fixed_passes(self):
        parser = self.parse(
            '<div class="f-column" data-figma-layout="column">'
            '<button class="f-row f-fixed" data-figma-layout="row" '
            'data-figma-width="fixed" data-figma-height="fixed"></button>'
            '</div>'
        )
        self.assertEqual(parser.fixed_flex_checked_count, 1)
        self.assertEqual(parser.fixed_flex_errors, [])

    def test_cross_axis_fixed_does_not_require_f_fixed(self):
        parser = self.parse(
            '<div class="f-column" data-figma-layout="column">'
            '<div data-figma-width="fixed" data-figma-height="hug"></div>'
            '</div>'
        )
        self.assertEqual(parser.fixed_flex_checked_count, 0)
        self.assertEqual(parser.fixed_flex_errors, [])


if __name__ == "__main__":
    unittest.main()
