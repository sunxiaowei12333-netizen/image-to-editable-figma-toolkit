"""Fixed text-edge-v1 policy. Diagnostic limits, not proof of visual quality.

Uses isolated, transparent, SCALE=1 text PNGs in their root pixel coordinates.
Never applies to source protection, safe-copy baseline or non-text differences.
"""
from PIL import Image, ImageChops, ImageFilter

PROFILE = "text-edge-v1"


def inspect_text_pair(before, after):
    a, b = before.convert("RGBA"), after.convert("RGBA")
    if a.size != b.size:
        return None, {"accepted": False, "reason": "text export dimensions changed"}
    aa, ba = a.getchannel("A"), b.getchannel("A")
    x, y = list(aa.getdata()), list(ba.getdata())
    mass_a, mass_b = sum(x), sum(y)
    if not mass_a or not mass_b:
        return None, {"accepted": False, "reason": "empty/missing text ink"}
    relative_alpha_error = sum(abs(i-j) for i,j in zip(x,y)) / max(mass_a,mass_b)
    mass_change = abs(mass_a-mass_b) / max(mass_a,mass_b)
    ax, bx = [v >= 128 for v in x], [v >= 128 for v in y]
    union = sum(i or j for i,j in zip(ax,bx))
    iou = sum(i and j for i,j in zip(ax,bx)) / union if union else 0
    # Weighted RGB rejects a color shift hidden behind a similar alpha mask.
    rgb_error = sum(min(pa[3],pb[3])*sum(abs(pa[k]-pb[k]) for k in range(3))
                    for pa,pb in zip(a.getdata(),b.getdata())) / (3*255*max(mass_a,mass_b))
    stats = {"profile": PROFILE, "relativeAlphaError": relative_alpha_error,
             "inkMassChange": mass_change, "inkIoU": iou, "weightedRgbError": rgb_error}
    if relative_alpha_error > .06 or mass_change > .03 or iou < .95 or rgb_error > .005:
        return None, dict(stats, accepted=False, reason="glyph/weight/color change exceeds fixed minor limits")
    masks=[]
    for alpha in (aa,ba):
        hard=alpha.point(lambda v: 255 if v >= 128 else 0)
        # One pixel either side of a glyph contour; interiors are excluded.
        contour=ImageChops.subtract(hard.filter(ImageFilter.MaxFilter(3)),
                                   hard.filter(ImageFilter.MinFilter(3)))
        partial=alpha.point(lambda v: 255 if 0 < v < 255 else 0)
        masks.append(ImageChops.lighter(contour,partial))
    edge=ImageChops.lighter(*masks)
    return edge, dict(stats, accepted=True)


def covered_difference_count(a, b, allowed):
    diff=ImageChops.difference(a.convert("RGBA"),b.convert("RGBA"))
    return sum(any(px) and not mask for px,mask in zip(diff.getdata(),allowed.getdata()))
