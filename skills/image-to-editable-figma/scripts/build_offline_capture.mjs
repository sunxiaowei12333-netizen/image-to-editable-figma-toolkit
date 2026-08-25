#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { ensureHugeiconsDir } from "./bootstrap.mjs";

const CAPTURE_SCRIPT = "https://mcp.figma.com/mcp/html-to-design/capture.js";
const PAYLOAD_SAFE_LIMIT_BYTES = 45 * 1024 * 1024;
const DATA_URL_SERIALIZATION_MULTIPLIER = 2.5;
const MIME_TYPES = new Map([
  [".avif", "image/avif"],
  [".gif", "image/gif"],
  [".jpeg", "image/jpeg"],
  [".jpg", "image/jpeg"],
  [".otf", "font/otf"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".ttf", "font/ttf"],
  [".webp", "image/webp"],
  [".woff", "font/woff"],
  [".woff2", "font/woff2"],
]);
const ATTRIBUTE_NAMES = {
  className: "class",
  fillRule: "fill-rule",
  clipRule: "clip-rule",
  strokeLinecap: "stroke-linecap",
  strokeLinejoin: "stroke-linejoin",
  strokeWidth: "stroke-width",
};

function usage(message) {
  if (message) console.error(message);
  console.error(
    "Usage: node build_offline_capture.mjs <source.html> --width <px> --height <px> [--output <capture.html>] [--hugeicons-dir <dir>] [--asset-mode inline|external]",
  );
  process.exit(2);
}

function parseArgs(argv) {
  if (!argv.length || argv[0].startsWith("--")) usage("Missing source HTML.");
  const options = { source: argv[0], "asset-mode": "inline" };
  for (let index = 1; index < argv.length; index += 1) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!["--width", "--height", "--output", "--hugeicons-dir", "--asset-mode"].includes(key)) {
      usage(`Unknown option: ${key}`);
    }
    if (!value) usage(`Missing value for ${key}`);
    options[key.slice(2)] = value;
    index += 1;
  }

  options.width = Number(options.width);
  options.height = Number(options.height);
  if (!Number.isInteger(options.width) || options.width <= 0) {
    usage("--width must be a positive integer.");
  }
  if (!Number.isInteger(options.height) || options.height <= 0) {
    usage("--height must be a positive integer.");
  }
  if (!["inline", "external"].includes(options["asset-mode"])) {
    usage("--asset-mode must be inline or external.");
  }
  return options;
}

function getAttribute(tag, name) {
  const match = tag.match(
    new RegExp(`\\b${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)'|([^\\s>]+))`, "i"),
  );
  return match ? (match[1] ?? match[2] ?? match[3] ?? "") : null;
}

function removeAttribute(tag, name) {
  return tag.replace(
    new RegExp(`\\s+${name}\\s*=\\s*(?:"[^"]*"|'[^']*'|[^\\s>]+)`, "i"),
    "",
  );
}

function setAttribute(tag, name, value) {
  const escapedValue = escapeAttribute(value);
  const pattern = new RegExp(
    `(\\b${name}\\s*=\\s*)(?:"[^"]*"|'[^']*'|[^\\s>]+)`,
    "i",
  );
  if (pattern.test(tag)) return tag.replace(pattern, `$1"${escapedValue}"`);
  return tag.replace(/>$/, ` ${name}="${escapedValue}">`);
}

function escapeAttribute(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function replaceAsync(source, expression, replacer) {
  let output = "";
  let lastIndex = 0;
  for (const match of source.matchAll(expression)) {
    output += source.slice(lastIndex, match.index);
    output += await replacer(...match);
    lastIndex = match.index + match[0].length;
  }
  return output + source.slice(lastIndex);
}

function classifyReference(reference) {
  const trimmed = reference.trim();
  if (trimmed.startsWith("data:")) return "data";
  if (trimmed.startsWith("#")) return "fragment";
  if (trimmed.startsWith("//") || /^[a-z][a-z0-9+.-]*:/i.test(trimmed)) {
    return trimmed.startsWith("file:") ? "file" : "remote";
  }
  return "local";
}

function resolveLocal(baseDir, reference) {
  const cleanReference = reference.split("#", 1)[0].split("?", 1)[0];
  if (cleanReference.startsWith("file:")) return fileURLToPath(cleanReference);
  const decoded = decodeURIComponent(cleanReference);
  return path.isAbsolute(decoded) ? decoded : path.resolve(baseDir, decoded);
}

async function toDataUrl(filePath) {
  const bytes = await fs.readFile(filePath);
  const mime = MIME_TYPES.get(path.extname(filePath).toLowerCase()) ?? "application/octet-stream";
  return `data:${mime};base64,${bytes.toString("base64")}`;
}

function toLocalWebReference(outputDir, filePath) {
  const relative = path.relative(outputDir, filePath);
  if (!relative || path.isAbsolute(relative)) {
    throw new Error(`Cannot create a relative local asset URL for: ${filePath}`);
  }
  return relative
    .split(path.sep)
    .map((segment) => (segment === ".." ? segment : encodeURIComponent(segment)))
    .join("/");
}

async function processCss(css, baseDir, label, assetMode, outputDir) {
  if (/\@import\b/i.test(css)) {
    throw new Error(`${label}: @import is not supported in a capture file.`);
  }
  return replaceAsync(
    css,
    /url\(\s*(['"]?)(.*?)\1\s*\)/gi,
    async (fullMatch, _quote, reference) => {
      const kind = classifyReference(reference);
      if (kind === "data" || kind === "fragment") return fullMatch;
      if (kind === "remote") {
        throw new Error(`${label}: remote CSS dependency is not capture-safe: ${reference}`);
      }
      const filePath = resolveLocal(baseDir, reference);
      const nextReference =
        assetMode === "inline"
          ? await toDataUrl(filePath)
          : toLocalWebReference(outputDir, filePath);
      return `url("${nextReference}")`;
    },
  );
}

async function renderHugeicon(name, iconDir) {
  if (!iconDir) {
    throw new Error(
      `Hugeicons marker ${name} was found, but @hugeicons/core-free-icons is unavailable.`,
    );
  }
  const modulePath = path.join(iconDir, `${name}.js`);
  const definition = (await import(pathToFileURL(modulePath).href)).default;
  const children = definition
    .map(([tag, attributes]) => {
      const serialized = Object.entries(attributes)
        .filter(([key]) => key !== "key")
        .map(([key, value]) => {
          const attributeName = ATTRIBUTE_NAMES[key] ?? key;
          return `${attributeName}="${escapeAttribute(value)}"`;
        })
        .join(" ");
      return `<${tag} ${serialized}></${tag}>`;
    })
    .join("");

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="100%" height="100%" fill="none" aria-hidden="true" data-icon-library="Hugeicons" data-icon-name="${escapeAttribute(name)}">${children}</svg>`;
}

function collectHugeiconNames(html) {
  const names = new Set();
  for (const match of html.matchAll(/<[a-z][^>]*data-icon-library\s*=\s*["']Hugeicons["'][^>]*>/gi)) {
    const name = getAttribute(match[0], "data-icon-name");
    if (name) names.add(name);
  }
  return [...names];
}

async function inlineHugeicons(html, sourceDir, explicitIconDir) {
  const names = collectHugeiconNames(html);
  if (!names.length) return { html, names };
  const iconResolution = await ensureHugeiconsDir(sourceDir, explicitIconDir);
  const iconDir = iconResolution.dir;

  for (const name of names) {
    const svg = await renderHugeicon(name, iconDir);
    const escapedName = escapeRegExp(name);
    const hostPattern = new RegExp(
      `(<([a-z][\\w:-]*)\\b(?=[^>]*data-icon-library\\s*=\\s*["']Hugeicons["'])(?=[^>]*data-icon-name\\s*=\\s*["']${escapedName}["'])[^>]*>)([\\s\\S]*?)(<\\/\\2>)`,
      "gi",
    );
    html = html.replace(hostPattern, (fullMatch, opening, tag, _content, closing) => {
      if (tag.toLowerCase() === "svg") return fullMatch;
      return `${opening}${svg}${closing}`;
    });
  }
  return { html, names };
}

async function inlineStyles(html, sourceDir, assetMode, outputDir) {
  html = await replaceAsync(
    html,
    /<style\b([^>]*)>([\s\S]*?)<\/style>/gi,
    async (_fullMatch, attributes, css) =>
      `<style${attributes}>${await processCss(css, sourceDir, "inline CSS", assetMode, outputDir)}</style>`,
  );

  return replaceAsync(html, /<link\b[^>]*>/gi, async (tag) => {
    const rel = (getAttribute(tag, "rel") ?? "").toLowerCase().split(/\s+/);
    if (!rel.includes("stylesheet")) return "";
    const href = getAttribute(tag, "href");
    if (!href) throw new Error("Stylesheet link is missing href.");
    const kind = classifyReference(href);
    if (kind === "remote" || kind === "data" || kind === "fragment") {
      throw new Error(`Stylesheet is not a local file: ${href}`);
    }
    const cssPath = resolveLocal(sourceDir, href);
    const css = await fs.readFile(cssPath, "utf8");
    const inlined = await processCss(css, path.dirname(cssPath), cssPath, assetMode, outputDir);
    return `<style data-capture-source="${escapeAttribute(path.basename(cssPath))}" data-capture-asset-mode="${assetMode}">${inlined}</style>`;
  });
}

async function inlineScripts(html, sourceDir) {
  return replaceAsync(
    html,
    /<script\b[^>]*\bsrc\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)[^>]*>[\s\S]*?<\/script>/gi,
    async (tag) => {
      const src = getAttribute(tag, "src");
      if (!src) return tag;
      if (src.split("?", 1)[0] === CAPTURE_SCRIPT) return "";
      const kind = classifyReference(src);
      if (kind === "data") return tag;
      if (kind === "remote" || kind === "fragment") {
        throw new Error(`Remote script is not capture-safe: ${src}`);
      }
      const scriptPath = resolveLocal(sourceDir, src);
      const script = await fs.readFile(scriptPath, "utf8");
      if (script.includes("@hugeicons/core-free-icons")) return "";
      if (/^\s*(?:import|export)\b/m.test(script)) {
        throw new Error(`Module imports must be bundled before self-contained capture: ${scriptPath}`);
      }
      const opening = removeAttribute(tag.match(/^<script\b[^>]*>/i)[0], "src");
      return `${opening}${script.replaceAll("</script>", "<\\/script>")}</script>`;
    },
  );
}

async function processMedia(html, sourceDir, assetMode, outputDir) {
  html = await replaceAsync(
    html,
    /<(?:img|source|video|audio|image)\b[^>]*>/gi,
    async (tag) => {
      let output = tag;
      for (const attribute of ["src", "poster", "href"]) {
        const reference = getAttribute(output, attribute);
        if (!reference) continue;
        const kind = classifyReference(reference);
        if (kind === "data" || kind === "fragment") continue;
        if (kind === "remote") {
          throw new Error(`Remote media is not capture-safe: ${reference}`);
        }
        const filePath = resolveLocal(sourceDir, reference);
        output = setAttribute(
          output,
          attribute,
          assetMode === "inline"
            ? await toDataUrl(filePath)
            : toLocalWebReference(outputDir, filePath),
        );
      }
      const srcset = getAttribute(output, "srcset");
      if (srcset && !srcset.trim().startsWith("data:")) {
        throw new Error("Local/remote srcset is unsupported; use a single src before self-contained capture.");
      }
      return output;
    },
  );

  let unresolvedMedia = null;
  for (const match of html.matchAll(/<(?:img|source|video|audio|image)\b[^>]*>/gi)) {
    for (const attribute of ["src", "poster", "href"]) {
      const reference = getAttribute(match[0], attribute);
      if (!reference) continue;
      const kind = classifyReference(reference);
      const invalid =
        assetMode === "inline"
          ? kind !== "data" && kind !== "fragment"
          : kind === "remote" || kind === "file";
      if (invalid) {
        unresolvedMedia = { attribute, reference };
        break;
      }
    }
    if (unresolvedMedia) break;
  }
  if (unresolvedMedia) {
    throw new Error(
      `Unresolved media ${unresolvedMedia.attribute} remains after bundling: ${unresolvedMedia.reference}`,
    );
  }
  return html;
}

function addDualCaptureLoader(html) {
  const loader = `<script data-dual-capture-loader="ready">
(() => {
  const hash = new URLSearchParams(window.location.hash.slice(1));
  const isHttp = window.location.protocol === "http:" || window.location.protocol === "https:";
  const isOfficialCapture = isHttp && hash.has("figmacapture") && hash.has("figmaendpoint");
  document.documentElement.dataset.captureMode = isOfficialCapture ? "official-http" : "preview-or-plugin";
  if (!isOfficialCapture || document.querySelector("script[data-official-figma-capture]")) return;
  const script = document.createElement("script");
  script.src = "${CAPTURE_SCRIPT}";
  script.async = true;
  script.dataset.officialFigmaCapture = "true";
  script.onerror = () => {
    document.documentElement.dataset.captureLoaderError = "official-script-failed";
  };
  document.head.append(script);
})();
</script>`;
  return html.replace(/<\/body>/i, `${loader}\n</body>`);
}

function addCaptureBounds(html, width, height, assetMode) {
  const boundsCss = `
/* Single-file preview, browser-plugin, and official HTTP Capture bounds. */
html,
body {
  width: ${width}px !important;
  height: ${height}px !important;
  min-width: ${width}px !important;
  min-height: ${height}px !important;
  max-width: ${width}px !important;
  max-height: ${height}px !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: hidden !important;
}

body {
  display: block !important;
  position: relative;
}

#canvas {
  position: absolute;
  inset: 0;
  width: ${width}px !important;
  height: ${height}px !important;
}
`;

  html = html.replace(
    /<\/head>/i,
    `<style data-offline-capture-bounds="${width}x${height}" data-dual-capture-bounds="${width}x${height}">${boundsCss}</style>\n</head>`,
  );
  html = html.replace(/<body\b[^>]*>/i, (tag) => {
    let output = setAttribute(tag, "data-offline-capture", "ready");
    output = setAttribute(output, "data-capture-artifact", "dual-mode");
    output = setAttribute(output, "data-capture-asset-mode", assetMode);
    output = setAttribute(output, "data-canvas-width", width);
    return setAttribute(output, "data-canvas-height", height);
  });
  html = html.replace(/<meta\b[^>]*name\s*=\s*["']viewport["'][^>]*>/i, (tag) =>
    setAttribute(tag, "content", `width=${width}, initial-scale=1`),
  );
  html = html.replace(/<title>([\s\S]*?)<\/title>/i, (_match, title) =>
    `<title>${title.includes("dual capture") ? title : `${title} · dual capture`}</title>`,
  );
  return html;
}

function getDataUrlCharacters(html) {
  let characters = 0;
  for (const match of html.matchAll(/data:[a-z0-9.+-]+\/[a-z0-9.+-]+(?:;[^,\s"')>]*)?,[a-z0-9+/=_-]+/gi)) {
    characters += match[0].length;
  }
  return characters;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const sourcePath = path.resolve(options.source);
  const sourceDir = path.dirname(sourcePath);
  const parsed = path.parse(sourcePath);
  const outputPath = path.resolve(
    options.output ?? path.join(parsed.dir, `${parsed.name}-capture${parsed.ext}`),
  );
  const outputDir = path.dirname(outputPath);
  const assetMode = options["asset-mode"];
  if (outputPath === sourcePath) throw new Error("Capture output must not overwrite the source HTML.");

  let html = await fs.readFile(sourcePath, "utf8");
  html = await inlineStyles(html, sourceDir, assetMode, outputDir);
  const iconResult = await inlineHugeicons(html, sourceDir, options["hugeicons-dir"]);
  html = iconResult.html;
  html = await inlineScripts(html, sourceDir);
  html = await processMedia(html, sourceDir, assetMode, outputDir);
  html = addCaptureBounds(html, options.width, options.height, assetMode);
  html = addDualCaptureLoader(html);
  await fs.writeFile(outputPath, html, "utf8");

  const outputStat = await fs.stat(outputPath);
  const dataUrlCharacters = getDataUrlCharacters(html);
  const estimatedSerializedBytes =
    outputStat.size + Math.round(dataUrlCharacters * DATA_URL_SERIALIZATION_MULTIPLIER);
  const officialPayloadRisk =
    assetMode === "inline" && estimatedSerializedBytes > PAYLOAD_SAFE_LIMIT_BYTES;
  console.log(
    JSON.stringify(
      {
        ok: true,
        source: sourcePath,
        output: outputPath,
        width: options.width,
        height: options.height,
        mode: "dual-capture",
        assetMode,
        hugeicons: iconResult.names,
        bytes: outputStat.size,
        dataUrlCharacters,
        estimatedSerializedBytes,
        payloadSafeLimitBytes: PAYLOAD_SAFE_LIMIT_BYTES,
        officialPayloadRisk,
        recommendedAssetMode: officialPayloadRisk ? "external" : assetMode,
      },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
