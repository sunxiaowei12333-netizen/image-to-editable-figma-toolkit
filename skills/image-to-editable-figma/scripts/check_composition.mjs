#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const FIGMA_TYPES = new Set([
  "IMAGE",
  "RECTANGLE",
  "ELLIPSE",
  "VECTOR",
  "LINE",
  "TEXT",
  "INSTANCE",
  "FRAME",
  "GROUP",
]);
const HORIZONTAL_ANCHORS = new Set(["left", "center", "right"]);
const VERTICAL_ANCHORS = new Set(["top", "center", "bottom"]);

function usage() {
  return `Usage:
  node scripts/check_composition.mjs <url-or-html> <composition-contract.json> [--output <report.json>] [--chrome <path>] [--timeout <ms>]
  node scripts/check_composition.mjs --self-test`;
}

function parseArgs(argv) {
  if (argv.includes("--self-test")) return { selfTest: true };
  const positional = [];
  const options = { timeout: 15000 };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--output" || value === "--chrome" || value === "--timeout") {
      const next = argv[index + 1];
      if (!next) throw new Error(`Missing value for ${value}`);
      if (value === "--output") options.output = next;
      if (value === "--chrome") options.chrome = next;
      if (value === "--timeout") options.timeout = Number(next);
      index += 1;
    } else if (value.startsWith("--")) {
      throw new Error(`Unknown option: ${value}`);
    } else {
      positional.push(value);
    }
  }
  if (positional.length !== 2) throw new Error(usage());
  if (!Number.isFinite(options.timeout) || options.timeout < 1000) {
    throw new Error("--timeout must be at least 1000ms");
  }
  return { target: positional[0], contractPath: positional[1], ...options };
}

function finitePositive(value) {
  return Number.isFinite(value) && value > 0;
}

function validateContract(contract) {
  const errors = [];
  if (!contract || typeof contract !== "object" || Array.isArray(contract)) {
    return ["Contract root must be an object"];
  }
  const canvas = contract.canvas;
  if (!canvas || typeof canvas !== "object") errors.push("canvas must be an object");
  if (!canvas?.selector || typeof canvas.selector !== "string") {
    errors.push("canvas.selector must be a non-empty string");
  }
  if (!finitePositive(canvas?.width) || !finitePositive(canvas?.height)) {
    errors.push("canvas.width and canvas.height must be positive numbers");
  }
  if (!Array.isArray(contract.elements) || contract.elements.length === 0) {
    errors.push("elements must be a non-empty array");
    return errors;
  }
  const ids = new Set();
  for (const [index, item] of contract.elements.entries()) {
    const prefix = `elements[${index}]`;
    if (!item || typeof item !== "object") {
      errors.push(`${prefix} must be an object`);
      continue;
    }
    if (!item.id || typeof item.id !== "string") errors.push(`${prefix}.id is required`);
    else if (ids.has(item.id)) errors.push(`${prefix}.id must be unique: ${item.id}`);
    else ids.add(item.id);
    if (!item.selector || typeof item.selector !== "string") {
      errors.push(`${prefix}.selector is required`);
    }
    if (!Number.isInteger(item.count) || item.count < 0) {
      errors.push(`${prefix}.count must be a non-negative integer`);
    }
    if (item.bounds) {
      for (const key of ["x", "y", "width", "height"]) {
        if (!Number.isFinite(item.bounds[key])) errors.push(`${prefix}.bounds.${key} must be numeric`);
      }
    }
    if (item.anchor?.horizontal && !HORIZONTAL_ANCHORS.has(item.anchor.horizontal)) {
      errors.push(`${prefix}.anchor.horizontal must be left/center/right`);
    }
    if (item.anchor?.vertical && !VERTICAL_ANCHORS.has(item.anchor.vertical)) {
      errors.push(`${prefix}.anchor.vertical must be top/center/bottom`);
    }
    if (item.aspectPolicy && !["intrinsic", "locked", "flexible"].includes(item.aspectPolicy)) {
      errors.push(`${prefix}.aspectPolicy must be intrinsic/locked/flexible`);
    }
    if (item.figmaType && !FIGMA_TYPES.has(String(item.figmaType).toUpperCase())) {
      errors.push(`${prefix}.figmaType is unsupported: ${item.figmaType}`);
    }
    if (item.attributes && (typeof item.attributes !== "object" || Array.isArray(item.attributes))) {
      errors.push(`${prefix}.attributes must be an object`);
    }
  }
  return errors;
}

function resolveTarget(value) {
  if (/^(https?|file):\/\//i.test(value)) return value;
  return pathToFileURL(path.resolve(value)).href;
}

function findExecutable(command) {
  const result = spawnSync(process.platform === "win32" ? "where" : "which", [command], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  });
  if (result.status !== 0) return null;
  return result.stdout.split(/\r?\n/).map((line) => line.trim()).find(Boolean) || null;
}

function findChrome(explicitPath) {
  const candidates = [
    explicitPath,
    process.env.CHROME_BIN,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, "Google/Chrome/Application/chrome.exe"),
    process.env["PROGRAMFILES(X86)"] && path.join(process.env["PROGRAMFILES(X86)"], "Google/Chrome/Application/chrome.exe"),
    findExecutable("google-chrome"),
    findExecutable("google-chrome-stable"),
    findExecutable("chromium"),
    findExecutable("chromium-browser"),
  ].filter(Boolean);
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) throw new Error("Google Chrome/Chromium not found; pass --chrome <absolute-path>");
  return found;
}

async function freePort() {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

async function waitForPageTarget(port, timeout) {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/list`);
      if (response.ok) {
        const targets = await response.json();
        const page = targets.find((target) => target.type === "page" && target.webSocketDebuggerUrl);
        if (page) return page;
      }
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Chrome DevTools target did not start${lastError ? `: ${lastError.message}` : ""}`);
}

async function connectCDP(url) {
  if (typeof WebSocket !== "function") throw new Error("This script requires Node.js with global WebSocket support");
  const socket = new WebSocket(url);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", () => reject(new Error("Failed to connect to Chrome DevTools")), { once: true });
  });
  let nextId = 1;
  const pending = new Map();
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(String(event.data));
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message || JSON.stringify(message.error)));
    else resolve(message.result || {});
  });
  socket.addEventListener("close", () => {
    for (const { reject } of pending.values()) reject(new Error("Chrome DevTools connection closed"));
    pending.clear();
  });
  return {
    send(method, params = {}) {
      const id = nextId;
      nextId += 1;
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        socket.send(JSON.stringify({ id, method, params }));
      });
    },
    close() {
      socket.close();
    },
  };
}

function browserCheck(contract) {
  const isFinitePositive = (value) => Number.isFinite(value) && value > 0;
  const errors = [];
  const warnings = [];
  const metrics = { canvas: null, elements: [] };
  const defaults = {
    canvasTolerancePx: 1,
    boundsTolerancePx: 4,
    anchorTolerancePx: 4,
    aspectRatioTolerance: 0.01,
    ...(contract.defaults || {}),
  };
  const canvasNodes = document.querySelectorAll(contract.canvas.selector);
  if (canvasNodes.length !== 1) {
    errors.push(`Canvas selector ${contract.canvas.selector} matched ${canvasNodes.length}, expected 1`);
    return { ok: false, errors, warnings, metrics };
  }
  const canvas = canvasNodes[0];
  const canvasRect = canvas.getBoundingClientRect();
  metrics.canvas = {
    selector: contract.canvas.selector,
    x: canvasRect.x,
    y: canvasRect.y,
    width: canvasRect.width,
    height: canvasRect.height,
  };
  for (const key of ["width", "height"]) {
    const delta = Math.abs(canvasRect[key] - contract.canvas[key]);
    if (delta > defaults.canvasTolerancePx) {
      errors.push(`Canvas ${key}=${canvasRect[key]} differs from ${contract.canvas[key]} by ${delta}px`);
    }
  }

  const relativeRect = (node) => {
    const rect = node.getBoundingClientRect();
    return {
      x: rect.left - canvasRect.left,
      y: rect.top - canvasRect.top,
      width: rect.width,
      height: rect.height,
    };
  };
  const compare = (id, label, actual, expected, tolerance) => {
    const delta = Math.abs(actual - expected);
    if (delta > tolerance) errors.push(`${id} ${label}=${actual} differs from ${expected} by ${delta}px (tolerance ${tolerance}px)`);
  };

  for (const item of contract.elements) {
    let nodes;
    try {
      nodes = [...document.querySelectorAll(item.selector)];
    } catch (error) {
      errors.push(`${item.id} has invalid selector ${item.selector}: ${error.message}`);
      continue;
    }
    const entry = {
      id: item.id,
      selector: item.selector,
      expectedCount: item.count,
      actualCount: nodes.length,
      figmaType: item.figmaType || null,
      nodes: [],
    };
    metrics.elements.push(entry);
    if (nodes.length !== item.count) {
      errors.push(`${item.id} matched ${nodes.length}, expected ${item.count}`);
    }
    for (const node of nodes) {
      const style = getComputedStyle(node);
      const rect = relativeRect(node);
      entry.nodes.push({
        tag: node.tagName,
        rect,
        display: style.display,
        visibility: style.visibility,
        opacity: Number(style.opacity),
        zIndex: style.zIndex,
      });
      if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) <= 0 || rect.width <= 0 || rect.height <= 0) {
        errors.push(`${item.id} is not visibly rendered`);
      }
    }
    if (nodes.length !== 1) continue;
    const node = nodes[0];
    const rect = relativeRect(node);
    const boundsTolerance = item.boundsTolerancePx ?? defaults.boundsTolerancePx;
    if (item.bounds) {
      for (const key of ["x", "y", "width", "height"]) {
        compare(item.id, key, rect[key], item.bounds[key], boundsTolerance);
      }
    }

    const anchorTolerance = item.anchorTolerancePx ?? defaults.anchorTolerancePx;
    const anchor = item.anchor || {};
    if (anchor.horizontal) {
      const actual = anchor.horizontal === "left"
        ? rect.x
        : anchor.horizontal === "right"
          ? contract.canvas.width - (rect.x + rect.width)
          : rect.x + rect.width / 2 - contract.canvas.width / 2;
      const expected = Number.isFinite(anchor.offsetX)
        ? anchor.offsetX
        : item.bounds
          ? anchor.horizontal === "left"
            ? item.bounds.x
            : anchor.horizontal === "right"
              ? contract.canvas.width - (item.bounds.x + item.bounds.width)
              : item.bounds.x + item.bounds.width / 2 - contract.canvas.width / 2
          : 0;
      compare(item.id, `${anchor.horizontal} anchor`, actual, expected, anchorTolerance);
    }
    if (anchor.vertical) {
      const actual = anchor.vertical === "top"
        ? rect.y
        : anchor.vertical === "bottom"
          ? contract.canvas.height - (rect.y + rect.height)
          : rect.y + rect.height / 2 - contract.canvas.height / 2;
      const expected = Number.isFinite(anchor.offsetY)
        ? anchor.offsetY
        : item.bounds
          ? anchor.vertical === "top"
            ? item.bounds.y
            : anchor.vertical === "bottom"
              ? contract.canvas.height - (item.bounds.y + item.bounds.height)
              : item.bounds.y + item.bounds.height / 2 - contract.canvas.height / 2
          : 0;
      compare(item.id, `${anchor.vertical} anchor`, actual, expected, anchorTolerance);
    }

    if (item.aspectPolicy && item.aspectPolicy !== "flexible") {
      const actualRatio = rect.height ? rect.width / rect.height : 0;
      let expectedRatio = Number(item.expectedAspectRatio);
      if (!isFinitePositive(expectedRatio) && item.aspectPolicy === "intrinsic" && node instanceof HTMLImageElement && node.naturalWidth && node.naturalHeight) {
        expectedRatio = node.naturalWidth / node.naturalHeight;
      }
      if (!isFinitePositive(expectedRatio) && item.bounds?.height) expectedRatio = item.bounds.width / item.bounds.height;
      if (!isFinitePositive(expectedRatio)) {
        warnings.push(`${item.id} cannot resolve an expected aspect ratio`);
      } else {
        const relativeDelta = Math.abs(actualRatio - expectedRatio) / expectedRatio;
        const tolerance = item.aspectRatioTolerance ?? defaults.aspectRatioTolerance;
        if (relativeDelta > tolerance) {
          errors.push(`${item.id} aspect ratio=${actualRatio} differs from ${expectedRatio} by ${(relativeDelta * 100).toFixed(2)}% (tolerance ${(tolerance * 100).toFixed(2)}%)`);
        }
      }
    }

    if (item.attributes) {
      for (const [name, expected] of Object.entries(item.attributes)) {
        const actual = node.getAttribute(name);
        if (actual !== String(expected)) errors.push(`${item.id} attribute ${name}=${JSON.stringify(actual)}, expected ${JSON.stringify(String(expected))}`);
      }
    }
    if (item.zIndex !== undefined) {
      const actual = getComputedStyle(node).zIndex;
      if (actual !== String(item.zIndex)) errors.push(`${item.id} z-index=${actual}, expected ${item.zIndex}`);
    }
  }
  return { ok: errors.length === 0, errors, warnings, metrics };
}

async function waitForDocument(client, timeout) {
  const deadline = Date.now() + timeout;
  let complete = false;
  while (Date.now() < deadline) {
    const response = await client.send("Runtime.evaluate", {
      expression: "document.readyState",
      returnByValue: true,
    });
    if (response.result?.value === "complete") {
      complete = true;
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  if (!complete) throw new Error(`Document did not reach readyState=complete within ${timeout}ms`);
  const assetTimeout = Math.max(1000, Math.min(timeout, 15000));
  const response = await client.send("Runtime.evaluate", {
    expression: `(async () => {
      const assets = Promise.all([
        document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve(),
        Promise.all([...document.images].map((image) => image.complete
          ? Promise.resolve()
          : new Promise((resolve) => {
              image.addEventListener('load', resolve, {once: true});
              image.addEventListener('error', resolve, {once: true});
            }))),
      ]);
      const status = await Promise.race([
        assets.then(() => 'loaded'),
        new Promise((resolve) => setTimeout(() => resolve('timeout'), ${assetTimeout})),
      ]);
      return {
        readyState: document.readyState,
        fonts: document.fonts ? document.fonts.status : 'unsupported',
        assets: status,
      };
    })()`,
    awaitPromise: true,
    returnByValue: true,
  });
  const readiness = response.result?.value;
  if (readiness?.assets !== "loaded") {
    throw new Error(`Images/fonts did not finish loading within ${assetTimeout}ms`);
  }
  return readiness;
}

async function runBrowserCheck(target, contract, options = {}) {
  const chrome = findChrome(options.chrome);
  const port = await freePort();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "figma-composition-check-"));
  const child = spawn(chrome, [
    "--headless=new",
    `--remote-debugging-port=${port}`,
    "--remote-debugging-address=127.0.0.1",
    "--remote-allow-origins=*",
    `--user-data-dir=${profile}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-sync",
    "--disable-extensions",
    "--disable-gpu",
    "--hide-scrollbars",
    "--allow-file-access-from-files",
    `--window-size=${Math.ceil(contract.canvas.width)},${Math.ceil(contract.canvas.height)}`,
    "about:blank",
  ], { stdio: "ignore" });
  let client;
  try {
    const page = await waitForPageTarget(port, options.timeout || 15000);
    client = await connectCDP(page.webSocketDebuggerUrl);
    await client.send("Page.enable");
    await client.send("Runtime.enable");
    await client.send("Emulation.setDeviceMetricsOverride", {
      width: Math.ceil(contract.canvas.width),
      height: Math.ceil(contract.canvas.height),
      deviceScaleFactor: 1,
      mobile: false,
    });
    await client.send("Page.navigate", { url: resolveTarget(target) });
    const readiness = await waitForDocument(client, options.timeout || 15000);
    const response = await client.send("Runtime.evaluate", {
      expression: `(${browserCheck.toString()})(${JSON.stringify(contract)})`,
      returnByValue: true,
    });
    if (response.exceptionDetails) throw new Error(response.exceptionDetails.text || "Browser evaluation failed");
    return {
      ...response.result.value,
      target: resolveTarget(target),
      readiness,
      chrome,
    };
  } finally {
    try { client?.close(); } catch {}
    try { child.kill("SIGKILL"); } catch { try { child.kill(); } catch {} }
    if (child.exitCode === null && child.signalCode === null) {
      await Promise.race([
        new Promise((resolve) => child.once("exit", resolve)),
        new Promise((resolve) => setTimeout(resolve, 1000)),
      ]);
    }
    fs.rmSync(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  }
}

async function selfTest() {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "figma-composition-self-test-"));
  const htmlPath = path.join(directory, "fixture.html");
  fs.writeFileSync(htmlPath, `<!doctype html><html><head><style>
    html,body{margin:0;width:320px;height:200px;overflow:hidden}
    #canvas{position:relative;width:320px;height:200px}
    .panel{position:absolute;left:80px;top:50px;width:160px;height:100px}
    .person{position:absolute;left:8px;top:100px;width:40px;height:120px}
  </style></head><body><main id="canvas">
    <div class="panel" data-figma-node-type="RECTANGLE"></div>
    <div class="person"></div>
  </main></body></html>`);
  const contract = {
    canvas: { selector: "#canvas", width: 320, height: 200 },
    elements: [
      {
        id: "panel",
        selector: ".panel",
        count: 1,
        bounds: { x: 80, y: 50, width: 160, height: 100 },
        anchor: { horizontal: "center", vertical: "center" },
        aspectPolicy: "locked",
        expectedAspectRatio: 1.6,
        attributes: { "data-figma-node-type": "RECTANGLE" },
        figmaType: "RECTANGLE",
      },
      {
        id: "person",
        selector: ".person",
        count: 1,
        bounds: { x: 8, y: 100, width: 40, height: 120 },
        anchor: { horizontal: "left", vertical: "bottom" },
        aspectPolicy: "locked",
        expectedAspectRatio: 1 / 3,
        figmaType: "IMAGE",
      },
    ],
  };
  try {
    const result = await runBrowserCheck(htmlPath, contract, { timeout: 15000 });
    if (!result.ok) throw new Error(`Self-test failed: ${JSON.stringify(result.errors)}`);
    const rejectedContract = structuredClone(contract);
    rejectedContract.elements[1].count = 2;
    const rejected = await runBrowserCheck(htmlPath, rejectedContract, { timeout: 15000 });
    if (rejected.ok || !rejected.errors.some((message) => message.includes("matched 1, expected 2"))) {
      throw new Error(`Self-test failed to reject a subject-count mismatch: ${JSON.stringify(rejected.errors)}`);
    }
    return {
      ok: true,
      selfTest: true,
      metrics: result.metrics,
      rejectedFixtureErrors: rejected.errors,
    };
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

async function main() {
  try {
    const args = parseArgs(process.argv.slice(2));
    let result;
    if (args.selfTest) {
      result = await selfTest();
    } else {
      const contractPath = path.resolve(args.contractPath);
      const contract = JSON.parse(fs.readFileSync(contractPath, "utf8"));
      const contractErrors = validateContract(contract);
      if (contractErrors.length) {
        result = { ok: false, errors: contractErrors, warnings: [], metrics: {}, contract: contractPath };
      } else {
        result = await runBrowserCheck(args.target, contract, args);
        result.contract = contractPath;
      }
      if (args.output) {
        const output = path.resolve(args.output);
        fs.mkdirSync(path.dirname(output), { recursive: true });
        fs.writeFileSync(output, `${JSON.stringify(result, null, 2)}\n`);
      }
    }
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    process.exitCode = result.ok ? 0 : 1;
  } catch (error) {
    process.stderr.write(`${error.message}\n${usage()}\n`);
    process.exitCode = 1;
  }
}

await main();
