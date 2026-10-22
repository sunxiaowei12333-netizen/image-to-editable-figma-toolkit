#!/usr/bin/env python3
"""Compare decoded PNG pixels. Optional frozen repair regions are [x,y,w,h]."""
import argparse
import json
import math
from PIL import Image, ImageChops, ImageDraw

def compare(before, after, regions=None):
    a, b = Image.open(before).convert('RGBA'), Image.open(after).convert('RGBA')
    if a.size != b.size:
        return {'pass': False, 'reason': 'dimensions-changed', 'before': a.size, 'after': b.size}
    diff = ImageChops.difference(a, b)
    changed = Image.new('L', a.size)
    for channel in diff.split():
        changed = ImageChops.lighter(changed, channel.point(lambda x: 255 if x else 0))
    total = changed.histogram()[255]
    outside = changed.copy()
    if regions is not None:
        draw = ImageDraw.Draw(outside)
        for x, y, w, h in regions:
            if w < 0 or h < 0:
                raise ValueError('negative repair region')
            draw.rectangle((math.floor(x), math.floor(y), math.ceil(x+w)-1, math.ceil(y+h)-1), fill=0)
    unplanned = outside.histogram()[255]
    return {'pass': unplanned == 0, 'size': a.size, 'changedPixels': total,
            'outsideDeclaredRegions': unplanned, 'exactPixels': total == 0}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before'); parser.add_argument('after')
    parser.add_argument('--regions', help='Frozen JSON array of [x,y,w,h], saved BEFORE the repair')
    args = parser.parse_args()
    regions = json.load(open(args.regions)) if args.regions else None
    result = compare(args.before, args.after, regions)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['pass'] else 2)
