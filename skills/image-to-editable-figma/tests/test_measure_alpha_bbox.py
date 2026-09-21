import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'measure_alpha_bbox.py'


class FrozenGeometryTests(unittest.TestCase):
    def measure(self, visible, target, extra=()):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / 'asset.png'
            Image.new('RGBA', visible, (60, 40, 30, 255)).save(image)
            plan = root / 'plan.json'
            plan.write_text(json.dumps({'assets': [{
                'assetId': 'panel', 'referenceBounds': dict(x=10, y=20, width=target[0], height=target[1]),
                'geometryPolicy': {'lockAxis': 'width'}
            }]}))
            before = plan.read_bytes()
            result = subprocess.run([sys.executable, str(SCRIPT), str(image), '--plan', str(plan),
                                     '--asset-id', 'panel', *extra], capture_output=True, text=True)
            self.assertEqual(plan.read_bytes(), before)
            return result, hashlib.sha256(before).hexdigest()

    def test_large_panel_small_percentage_still_gets_attention(self):
        result, digest = self.measure((1000, 960), (500, 500))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        comparison = report['target_comparison']
        self.assertEqual(comparison['height_delta_px'], -20)
        self.assertEqual(comparison['max_size_delta_percent'], 4)
        self.assertTrue(comparison['needs_visual_attention'])
        self.assertEqual(comparison['visual_status'], 'pending')
        self.assertEqual(report['frozen_plan']['sha256'], digest)
        self.assertEqual(report['frozen_plan']['referenceBounds']['height'], 500)

    def test_shallow_strip_percent_does_not_automatically_fail(self):
        result, _ = self.measure((1000, 126), (500, 60))
        comparison = json.loads(result.stdout)['target_comparison']
        self.assertEqual(comparison['height_delta_px'], 3)
        self.assertEqual(comparison['visual_status'], 'pending')
        self.assertFalse(comparison['nonuniform_scaling'])

    def test_cannot_override_frozen_target_or_axis(self):
        for extra in [('--target-height', '475'), ('--preserve-aspect', 'height')]:
            with self.subTest(extra=extra):
                result, _ = self.measure((1000, 950), (500, 500), extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('cannot be overridden', result.stderr)


if __name__ == '__main__':
    unittest.main()
