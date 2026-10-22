const assert = require('node:assert/strict');
const { collectVisibleScope } = require('./collect_visible_scope.js');
const box = (x, y, width, height) => ({ x, y, width, height });
function node(id, bounds, children = [], extras = {}) {
  return { id, visible: true, absoluteBoundingBox: bounds,
    absoluteRenderBounds: bounds, children, ...extras };
}
const screen = (...children) => node('root', box(0, 0, 100, 100), children, { clipsContent: true });
const ids = list => list.map(n => n.id);
let tests = 0;
function test(fn) { fn(); tests++; }
test(() => {
  const page = new Proxy({ id: 'page', parent: null }, {
    get(target, key) {
      if (!(key in target)) throw Error('unsupported PAGE property: ' + key);
      return target[key];
    }
  });
  const root = screen(); root.parent = page;
  assert.equal(collectVisibleScope(root).details.length, 1);
});
test(() => {
  const child = node('component', box(24, 24, 80, 40));
  const section = new Proxy({
    id: 'section', visible: true, parent: null,
    absoluteBoundingBox: box(0, 0, 200, 100), children: [child]
  }, {
    get(target, key) {
      if (!(key in target)) throw Error('unsupported SECTION property: ' + key);
      return target[key];
    }
  });
  child.parent = section;
  assert.deepEqual(ids(collectVisibleScope(section).details), ['section', 'component']);
  assert.deepEqual(ids(collectVisibleScope(section).dependencies), ['section']);
});
test(() => {
  const hidden = node('hidden', box(0, 0, 10, 10), [], { visible: false });
  Object.defineProperty(hidden, 'children', { get() { throw Error('hidden subtree expanded'); } });
  assert.deepEqual(ids(collectVisibleScope(screen(hidden)).details), ['root']);
});
test(() => {
  const clipped = node('clipped', box(0, 200, 100, 100), [], { clipsContent: true });
  Object.defineProperty(clipped, 'children', { get() { throw Error('clipped subtree expanded'); } });
  assert.equal(collectVisibleScope(screen(clipped)).stats.clippedSubtrees, 1);
});
test(() => {
  const child = node('overflow', box(0, 20, 10, 10));
  const outside = node('outside', box(0, 200, 20, 20), [child]);
  const result = collectVisibleScope(screen(outside));
  assert(ids(result.details).includes('overflow'));
  assert(ids(result.dependencies).includes('outside'));
});
test(() => {
  const partial = node('partial', box(0, 90, 20, 20));
  const offscreen = node('flowSibling', box(0, 150, 20, 20));
  const flow = node('flow', box(0, 0, 100, 200), [partial, offscreen], { layoutMode: 'VERTICAL' });
  const result = collectVisibleScope(screen(flow));
  assert(ids(result.details).includes('partial'));
  assert(!ids(result.details).includes('flowSibling'));
  assert(ids(result.dependencies).includes('flowSibling'));
});
test(() => {
  const shadow = node('shadow', box(110, 0, 20, 20), [], { absoluteRenderBounds: box(90, 0, 40, 20) });
  assert(ids(collectVisibleScope(screen(shadow)).details).includes('shadow'));
});
test(() => {
  const unknown = node('unknown', null);
  assert(ids(collectVisibleScope(screen(unknown)).details).includes('unknown'));
});
test(() => {
  const clipped = node('clipped', box(0, 200, 20, 20), [], { absoluteRenderBounds: null, effects: [] });
  assert(!ids(collectVisibleScope(screen(clipped)).details).includes('clipped'));
  clipped.effects = [{ visible: true, type: 'DROP_SHADOW' }];
  assert(ids(collectVisibleScope(screen(clipped)).details).includes('clipped'));
});
test(() => {
  const root = screen(node('item', box(0, 70, 20, 20)));
  root.parent = node('parent', box(0, 0, 100, 50), [], { clipsContent: true });
  const result = collectVisibleScope(root);
  assert(!ids(result.details).includes('item'));
  assert(ids(result.dependencies).includes('parent'));
});
test(() => {
  const root = screen(); root.parent = { visible: false };
  assert.equal(collectVisibleScope(root).details.length, 0);
});
test(() => {
  const first = node('first', box(0, 0, 100, 80));
  const second = node('second', box(0, 80, 100, 80));
  const root = screen(node('flow', box(0, 0, 100, 160), [first, second], { layoutMode: 'VERTICAL' }));
  const before = ids(collectVisibleScope(root).details);
  second.absoluteRenderBounds = second.absoluteBoundingBox = box(0, 100, 100, 80);
  const after = ids(collectVisibleScope(root).details);
  assert(before.includes('second')); assert(!after.includes('second'));
  assert(new Set([...before, ...after]).has('second'));
});
console.log(JSON.stringify({ passed: tests }));
