#!/usr/bin/env node

import { createReadStream } from "node:fs";
import { appendFile, lstat, mkdir, readFile, readdir, realpath, rename, rm, stat } from "node:fs/promises";
import { createServer } from "node:http";
import { homedir } from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

export const SERVICE_NAME = "image-to-editable-figma-preview";
export const PROTOCOL_VERSION = 1;
export const DEFAULT_HOST = "127.0.0.1";
export const DEFAULT_PORT = 41972;

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const MAX_LOG_BYTES = 1024 * 1024;
const MIME_TYPES = new Map([
  [".css", "text/css; charset=utf-8"],
  [".gif", "image/gif"],
  [".htm", "text/html; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".jpeg", "image/jpeg"],
  [".jpg", "image/jpeg"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".mjs", "text/javascript; charset=utf-8"],
  [".otf", "font/otf"],
  [".png", "image/png"],
  [".svg", "image/svg+xml; charset=utf-8"],
  [".ttf", "font/ttf"],
  [".webp", "image/webp"],
  [".woff", "font/woff"],
  [".woff2", "font/woff2"],
]);

export function defaultStateDir() {
  return process.env.IMAGE_TO_EDITABLE_FIGMA_PREVIEW_STATE_DIR
    ? path.resolve(process.env.IMAGE_TO_EDITABLE_FIGMA_PREVIEW_STATE_DIR)
    : path.join(homedir(), ".codex", "image-to-editable-figma-preview");
}

export function parseServerArgs(argv) {
  const parsed = { stateDir: defaultStateDir(), host: undefined, port: undefined };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--state-dir") parsed.stateDir = path.resolve(argv[++index]);
    else if (value === "--host") parsed.host = argv[++index];
    else if (value === "--port") parsed.port = Number(argv[++index]);
    else throw new Error(`Unknown argument: ${value}`);
  }
  return parsed;
}

export async function readConfig(stateDir) {
  const configPath = path.join(stateDir, "config.json");
  const config = JSON.parse(await readFile(configPath, "utf8"));
  if (config.service !== SERVICE_NAME || config.protocolVersion !== PROTOCOL_VERSION) {
    throw new Error(`Invalid preview service configuration: ${configPath}`);
  }
  if (!config.installationId || config.host !== DEFAULT_HOST || !Number.isInteger(config.port)) {
    throw new Error(`Incomplete preview service configuration: ${configPath}`);
  }
  return config;
}

async function loadRoutes(stateDir) {
  const routesDir = path.join(stateDir, "routes");
  let entries;
  try {
    entries = await readdir(routesDir, { withFileTypes: true });
  } catch (error) {
    if (error.code === "ENOENT") return [];
    throw error;
  }

  const routes = [];
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".json")) continue;
    const route = JSON.parse(await readFile(path.join(routesDir, entry.name), "utf8"));
    if (
      typeof route.prefix !== "string" ||
      typeof route.directory !== "string" ||
      typeof route.captureFile !== "string"
    ) {
      continue;
    }
    routes.push(route);
  }
  routes.sort((left, right) => right.prefix.length - left.prefix.length);
  return routes;
}

async function appendBoundedLog(stateDir, payload) {
  const logsDir = path.join(stateDir, "logs");
  const logPath = path.join(logsDir, "service.log");
  const rotatedPath = `${logPath}.1`;
  await mkdir(logsDir, { recursive: true, mode: 0o700 });
  try {
    if ((await stat(logPath)).size >= MAX_LOG_BYTES) {
      await rm(rotatedPath, { force: true });
      await rename(logPath, rotatedPath);
    }
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  const safe = {
    timestamp: new Date().toISOString(),
    level: payload.level,
    event: payload.event,
    message: payload.message ? String(payload.message).slice(0, 500) : undefined,
  };
  await appendFile(logPath, `${JSON.stringify(safe)}\n`, { mode: 0o600 });
}

function sendJson(response, statusCode, payload, headOnly = false) {
  const body = Buffer.from(`${JSON.stringify(payload)}\n`);
  response.writeHead(statusCode, {
    "Cache-Control": "no-store",
    "Content-Length": body.length,
    "Content-Type": "application/json; charset=utf-8",
    "X-Content-Type-Options": "nosniff",
  });
  response.end(headOnly ? undefined : body);
}

function reject(response, statusCode, code, headOnly = false) {
  sendJson(response, statusCode, { error: code }, headOnly);
}

function decodeSafePath(pathname) {
  let decoded;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    throw new Error("invalid-url-encoding");
  }
  if (
    decoded.includes("\\") ||
    decoded.includes("\0") ||
    /(?:^|\/)\.\.(?:\/|$)/.test(decoded) ||
    /%[0-9a-f]{2}/i.test(decoded)
  ) {
    throw new Error("unsafe-path");
  }
  return decoded;
}

function isWithin(parent, candidate) {
  return candidate === parent || candidate.startsWith(`${parent}${path.sep}`);
}

async function serveRegisteredFile({ request, response, stateDir, routes, headOnly }) {
  const requestUrl = new URL(request.url, `http://${DEFAULT_HOST}`);
  const pathname = decodeSafePath(requestUrl.pathname);
  const route = routes.find((candidate) => pathname.startsWith(candidate.prefix));
  if (!route) return reject(response, 404, "route-not-registered", headOnly);

  const relativeUrlPath = pathname.slice(route.prefix.length);
  if (!relativeUrlPath || relativeUrlPath.endsWith("/")) {
    return reject(response, 404, "directory-listing-disabled", headOnly);
  }

  const registeredRoot = await realpath(route.directory);
  const candidate = path.resolve(registeredRoot, ...relativeUrlPath.split("/"));
  if (!isWithin(registeredRoot, candidate)) {
    return reject(response, 403, "path-outside-route", headOnly);
  }

  let resolved;
  let stat;
  try {
    resolved = await realpath(candidate);
    if (!isWithin(registeredRoot, resolved)) {
      return reject(response, 403, "symlink-outside-route", headOnly);
    }
    stat = await lstat(resolved);
  } catch (error) {
    if (error.code === "ENOENT" || error.code === "ENOTDIR") {
      return reject(response, 404, "file-not-found", headOnly);
    }
    throw error;
  }

  if (!stat.isFile()) return reject(response, 404, "directory-listing-disabled", headOnly);

  response.writeHead(200, {
    "Cache-Control": "no-store",
    "Content-Length": stat.size,
    "Content-Type": MIME_TYPES.get(path.extname(resolved).toLowerCase()) ?? "application/octet-stream",
    "X-Content-Type-Options": "nosniff",
  });
  if (headOnly) return response.end();

  const stream = createReadStream(resolved);
  stream.on("error", () => {
    if (!response.headersSent) reject(response, 500, "read-failed");
    else response.destroy();
  });
  stream.pipe(response);
}

export async function startPreviewServer(options = {}) {
  const stateDir = path.resolve(options.stateDir ?? defaultStateDir());
  const config = await readConfig(stateDir);
  const host = options.host ?? config.host;
  const port = options.port ?? config.port;
  if (host !== DEFAULT_HOST) throw new Error(`Preview server must bind ${DEFAULT_HOST}`);

  const server = createServer(async (request, response) => {
    const headOnly = request.method === "HEAD";
    try {
      if (request.method !== "GET" && request.method !== "HEAD") {
        response.setHeader("Allow", "GET, HEAD");
        return reject(response, 405, "method-not-allowed");
      }
      const requestUrl = new URL(request.url, `http://${host}`);
      if (requestUrl.pathname === "/.well-known/image-to-editable-figma-preview.json") {
        const address = server.address();
        return sendJson(response, 200, {
          service: SERVICE_NAME,
          protocolVersion: PROTOCOL_VERSION,
          installationId: config.installationId,
          host,
          port: typeof address === "object" && address ? address.port : port,
        }, headOnly);
      }
      const routes = await loadRoutes(stateDir);
      return await serveRegisteredFile({ request, response, stateDir, routes, headOnly });
    } catch (error) {
      const clientError = error.message === "unsafe-path" || error.message === "invalid-url-encoding";
      reject(response, clientError ? 400 : 500, clientError ? error.message : "internal-error", headOnly);
      if (!clientError) {
        await appendBoundedLog(stateDir, { level: "error", event: "request-failed", message: error.message });
      }
    }
  });

  await new Promise((resolve, rejectPromise) => {
    server.once("error", rejectPromise);
    server.listen(port, host, () => {
      server.off("error", rejectPromise);
      resolve();
    });
  });
  await appendBoundedLog(stateDir, { level: "info", event: "server-started" });
  return server;
}

async function main() {
  const options = parseServerArgs(process.argv.slice(2));
  const server = await startPreviewServer(options);
  const address = server.address();
  process.stdout.write(`${JSON.stringify({
    status: "running",
    host: DEFAULT_HOST,
    port: typeof address === "object" && address ? address.port : options.port,
    stateDir: options.stateDir,
  })}\n`);

  const shutdown = () => server.close(() => process.exit(0));
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

if (path.resolve(process.argv[1] ?? "") === SCRIPT_PATH) {
  main().catch((error) => {
    process.stderr.write(`${JSON.stringify({ status: "error", message: error.message })}\n`);
    process.exitCode = 1;
  });
}
