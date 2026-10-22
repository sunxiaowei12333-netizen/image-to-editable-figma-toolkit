import tempfile
import unittest
from pathlib import Path
from PIL import Image, PngImagePlugin
from compare_rgba import compare

class ComparePixels(unittest.TestCase):
    def test_encoding_difference_is_not_visual_failure(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a.png',Path(d)/'b.png'
            im=Image.new('RGBA',(8,8),(23,45,67,255));im.save(a,compress_level=0)
            meta=PngImagePlugin.PngInfo();meta.add_text('export','different metadata')
            im.save(b,compress_level=9,pnginfo=meta)
            self.assertNotEqual(a.read_bytes(),b.read_bytes())
            self.assertTrue(compare(a,b)['exactPixels'])
    def test_actual_drift_outside_frozen_region_fails(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a.png',Path(d)/'b.png'
            im=Image.new('RGBA',(8,8),'white');im.save(a)
            im.putpixel((5,5),(0,0,0,255));im.save(b)
            self.assertFalse(compare(a,b,[[0,0,4,4]])['pass'])
            self.assertTrue(compare(a,b,[[5,5,1,1]])['pass'])
    def test_dimensions_and_alpha_are_checked(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a.png',Path(d)/'b.png'
            Image.new('RGBA',(8,8),(0,0,0,0)).save(a)
            Image.new('RGBA',(8,8),(0,0,0,1)).save(b)
            self.assertFalse(compare(a,b)['pass'])
            Image.new('RGBA',(9,8)).save(b)
            self.assertEqual(compare(a,b)['reason'],'dimensions-changed')

if __name__=='__main__':unittest.main()
