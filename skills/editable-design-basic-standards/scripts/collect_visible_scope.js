/* Paste into use_figma after loading figma-use. No mutations or deep findAll.
 * Conservative rectangle filtering; exact masks/occlusion remain visual checks.
 * Returns node objects locally. Return only IDs/counts or bounded detail batches.
 */
function collectVisibleScope(root) {
  const details = new Map(), dependencies = new Map();
  const stats = { visited: 0, hiddenSubtrees: 0, clippedSubtrees: 0 };
  function rect(r) {
    return r && [r.x, r.y, r.width, r.height].every(Number.isFinite)
      && r.width >= 0 && r.height >= 0 ? r : null;
  }
  function overlap(a, b) {
    if (!a || !b) return a || b; // Unknown bounds never justify exclusion.
    const x = Math.max(a.x, b.x), y = Math.max(a.y, b.y);
    const right = Math.min(a.x + a.width, b.x + b.width);
    const bottom = Math.min(a.y + a.height, b.y + b.height);
    return right > x && bottom > y
      ? { x, y, width: right - x, height: bottom - y } : null;
  }
  function visit(n, clip) {
    stats.visited++;
    if (n.visible === false) { stats.hiddenSubtrees++; return false; }
    const geometry = rect(n.absoluteBoundingBox);
    const render = rect("absoluteRenderBounds" in n ? n.absoluteRenderBounds : null);
    // Figma returns null render bounds for fully clipped nodes. Geometry is
    // sufficient only when no visible effect can extend it; otherwise include.
    const effectsMayExtend = "effects" in n && n.effects.some(e => e.visible !== false);
    const bounds = render || (!effectsMayExtend ? geometry : null);
    const hit = !bounds || !clip || !!overlap(bounds, clip);
    if (hit) details.set(n.id, n);
    let next = clip;
    if ("clipsContent" in n && n.clipsContent && geometry && clip) {
      next = overlap(geometry, clip);
      if (!next) {
        stats.clippedSubtrees++;
        return hit; // The container's shadow can still be visible.
      }
    }
    const children = "children" in n ? n.children : [];
    let relevant = hit;
    for (const child of children) relevant = visit(child, next) || relevant;
    if (relevant && children.length) {
      dependencies.set(n.id, n);
      if ("layoutMode" in n && n.layoutMode !== "NONE") {
        // Off-crop siblings can move visible content via flow/SPACE_BETWEEN.
        for (const child of children) {
          if (child.visible !== false) dependencies.set(child.id, child);
        }
      }
    }
    return relevant;
  }
  for (let parent = root.parent; parent; parent = parent.parent) {
    if ("visible" in parent && parent.visible === false) {
      return { details: [], dependencies: [], stats: { ...stats, hiddenSubtrees: 1 } };
    }
  }
  let clip = rect(root.absoluteBoundingBox);
  for (let parent = root.parent; parent; parent = parent.parent) {
    if ("clipsContent" in parent && parent.clipsContent) {
      const bound = rect(parent.absoluteBoundingBox);
      if (clip && bound) {
        clip = overlap(clip, bound);
        if (!clip) return { details: [], dependencies: [], stats: { ...stats, clippedSubtrees: 1 } };
      }
    }
  }
  if (visit(root, clip)) {
    for (let parent = root.parent; parent; parent = parent.parent) {
      if ("visible" in parent) dependencies.set(parent.id, parent);
    }
  }
  return { details: [...details.values()], dependencies: [...dependencies.values()], stats };
}

if (typeof module !== "undefined") module.exports = { collectVisibleScope };
