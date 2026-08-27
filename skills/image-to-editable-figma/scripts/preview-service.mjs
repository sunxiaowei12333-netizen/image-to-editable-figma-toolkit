#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import { execFile } from "node:child_process";
import {
  access,
  mkdir,
  mkdtemp,
  open,
  readFile,
  realpath,
  rename,
  rm,
  stat,
  symlink,
  truncate,
  writeFile,
} from "node:fs/promises";
import { createServer as createHttpServer, request as httpRequest } from "node:http";
import { homedir, platform, tmpdir } from "node:os";
import path from "node:path";
import process from "node:process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

import {
  DEFAULT_HOST,
  DEFAULT_PORT,
  PROTOCOL_VERSION,
  SERVICE_NAME,
  defaultStateDir,
  readConfig,
  startPreviewServer,
} from "./preview-server.mjs";

const execFileAsync = promisify(execFile);
const SCRIPT_PATH = fileURLToPath(import.meta.url);
const SCRIPT_DIR = path.dirname(SCRIPT_PATH);
const SKILL_ROOT = path.dirname(SCRIPT_DIR);
const SERVER_PATH = path.join(SCRIPT_DIR, "preview-server.mjs");
const TEMPLATE_PATH = path.join(SKILL_ROOT, "assets", "launchd-preview-service.plist.template");
const LAUNCHD_LABEL = "com.openai.codex.image-to-editable-figma-preview";
const ID_PATTERN = /^[a-z0-9][a-z0-9._-]{0,127}$/i;

function print(payload) {
  process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
}

function parseArgs(argv) {
  const result = { _: [], stateDir: defaultStateDir(), flags: new Set(), values: {} };
  const valueOptions = new Set([
    "--capture",
    "--dir",
    "--port",
    "--state-dir",
    "--task-id",
    "--version",
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (!item.startsWith("--")) {
      result._.push(item);
      continue;
    }
    if (valueOptions.has(item)) {
      const value = argv[++index];
      if (value === undefined) throw new Error(`${item} requires a value`);
      if (item === "--state-dir") result.stateDir = path.resolve(value);
      else result.values[item.slice(2)] = value;
    } else {
      result.flags.add(item.slice(2));
    }
  }
  return result;
}

function assertSafeId(value, label) {
  if (!value || !ID_PATTERN.test(value)) {
    throw new Error(`${label} must match ${ID_PATTERN}`);
  }
}

function isWithin(parent, candidate) {
  return candidate === parent || candidate.startsWith(`${parent}${path.sep}`);
}

async function exists(target) {
  try {
    await access(target);
    return true;
  } catch {
    return false;
  }
}

async function atomicWriteJson(target, payload) {
  await mkdir(path.dirname(target), { recursive: true, mode: 0o700 });
  const temporary = `${target}.${process.pid}.${randomUUID()}.tmp`;
  await writeFile(temporary, `${JSON.stringify(payload, null, 2)}\n`, { mode: 0o600 });
  await rename(temporary, target);
}

async function sha256File(target) {
  const body = await readFile(target);
  return createHash("sha256").update(body).digest("hex");
}

function routePath(stateDir, taskId, version) {
  return path.join(stateDir, "routes", `${taskId}--${version}.json`);
}

async function withRouteLock(stateDir, taskId, version, action) {
  const target = routePath(stateDir, taskId, version);
  const lockPath = target.replace(/\.json$/, ".lock");
  await mkdir(path.dirname(lockPath), { recursive: true, mode: 0o700 });
  const deadline = Date.now() + 2500;
  let handle;
  while (!handle && Date.now() < deadline) {
    try {
      handle = await open(lockPath, "wx", 0o600);
      await handle.writeFile(`${JSON.stringify({ pid: process.pid, createdAt: new Date().toISOString() })}\n`);
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
      try {
        const lockStat = await stat(lockPath);
        if (Date.now() - lockStat.mtimeMs > 30_000) {
          await rm(lockPath);
          continue;
        }
      } catch (lockError) {
        if (lockError.code === "ENOENT") continue;
        throw lockError;
      }
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
  }
  if (!handle) throw new Error(`Timed out waiting for route lock: ${taskId}/${version}`);
  try {
    return await action(target);
  } finally {
    await handle.close();
    await rm(lockPath, { force: true });
  }
}

async function requestBuffer(url, { method = "GET", timeoutMs = 1500 } = {}) {
  return await new Promise((resolve, reject) => {
    const request = httpRequest(url, { method }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => resolve({
        body: Buffer.concat(chunks),
        headers: response.headers,
        statusCode: response.statusCode,
      }));
    });
    request.setTimeout(timeoutMs, () => request.destroy(new Error("request-timeout")));
    request.on("error", reject);
    request.end();
  });
}

async function probeIdentity(host, port, expectedInstallationId) {
  const url = `http://${host}:${port}/.well-known/image-to-editable-figma-preview.json`;
  try {
    const response = await requestBuffer(url, { timeoutMs: 800 });
    let identity;
    try {
      identity = JSON.parse(response.body.toString("utf8"));
    } catch {
      return { status: "unknown-service", url };
    }
    const identityMatches =
      response.statusCode === 200 &&
      identity.service === SERVICE_NAME &&
      identity.protocolVersion === PROTOCOL_VERSION &&
      (!expectedInstallationId || identity.installationId === expectedInstallationId);
    return identityMatches
      ? { status: "running", url, identity }
      : { status: "unknown-service", url, identity };
  } catch (error) {
    if (["ECONNREFUSED", "EHOSTUNREACH", "ENETUNREACH"].includes(error.code)) {
      return { status: "stopped", url };
    }
    return { status: "unreachable", url, message: error.message };
  }
}

function xmlEscape(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

async function renderLaunchdPlist({ stateDir }) {
  const template = await readFile(TEMPLATE_PATH, "utf8");
  const replacements = {
    "{{LABEL}}": LAUNCHD_LABEL,
    "{{NODE_PATH}}": process.execPath,
    "{{SERVER_PATH}}": SERVER_PATH,
    "{{STATE_DIR}}": stateDir,
  };
  let rendered = template;
  for (const [marker, value] of Object.entries(replacements)) {
    rendered = rendered.replaceAll(marker, xmlEscape(value));
  }
  return rendered;
}

function launchdPlistPath() {
  return path.join(homedir(), "Library", "LaunchAgents", `${LAUNCHD_LABEL}.plist`);
}

async function install(args) {
  if (!args.flags.has("confirm-persistent-install") && !args.flags.has("dry-run")) {
    throw new Error("install requires --confirm-persistent-install after explicit user authorization");
  }
  const stateDir = path.resolve(args.stateDir);
  if (isWithin(SKILL_ROOT, stateDir)) {
    throw new Error("Persistent preview state must be outside the Skill directory");
  }

  const configPath = path.join(stateDir, "config.json");
  const requestedPort = args.values.port === undefined ? undefined : Number(args.values.port);
  if (requestedPort !== undefined && (!Number.isInteger(requestedPort) || requestedPort < 1024 || requestedPort > 65535)) {
    throw new Error("--port must be an integer between 1024 and 65535");
  }

  let config;
  if (await exists(configPath)) {
    config = await readConfig(stateDir);
    if (requestedPort !== undefined && requestedPort !== config.port) {
      throw new Error(`Port is already fixed at ${config.port}; refusing silent port migration`);
    }
  } else {
    config = {
      service: SERVICE_NAME,
      protocolVersion: PROTOCOL_VERSION,
      installationId: randomUUID(),
      host: DEFAULT_HOST,
      port: requestedPort ?? DEFAULT_PORT,
      createdAt: new Date().toISOString(),
    };
  }

  const probe = await probeIdentity(config.host, config.port, config.installationId);
  if (probe.status === "unknown-service" || probe.status === "unreachable") {
    throw new Error(`Port ${config.port} is occupied or cannot be verified (${probe.status}); no fallback port was selected`);
  }

  const useLaunchd = platform() === "darwin" && !args.flags.has("no-launchd");
  const plist = useLaunchd ? await renderLaunchdPlist({ stateDir }) : undefined;
  const plan = {
    action: "install",
    dryRun: args.flags.has("dry-run"),
    stateDir,
    host: config.host,
    port: config.port,
    launchd: useLaunchd,
    plistPath: useLaunchd ? launchdPlistPath() : undefined,
    note: useLaunchd
      ? "macOS user LaunchAgent; routes remain outside the Skill directory"
      : "configuration only; run preview-service.mjs serve under a platform service manager",
  };
  if (args.flags.has("dry-run")) return plan;

  await mkdir(path.join(stateDir, "routes"), { recursive: true, mode: 0o700 });
  await mkdir(path.join(stateDir, "logs"), { recursive: true, mode: 0o700 });
  await atomicWriteJson(configPath, config);
  if (useLaunchd) {
    const plistPath = launchdPlistPath();
    await mkdir(path.dirname(plistPath), { recursive: true });
    const temporary = `${plistPath}.${process.pid}.tmp`;
    await writeFile(temporary, plist, { mode: 0o600 });
    await rename(temporary, plistPath);
    await startLaunchd();
  }
  return { ...plan, dryRun: false, status: useLaunchd ? "started" : "configured" };
}

async function startLaunchd() {
  if (platform() !== "darwin") throw new Error("start is only implemented for the optional macOS launchd wrapper");
  const domain = `gui/${process.getuid()}`;
  const plistPath = launchdPlistPath();
  if (!(await exists(plistPath))) throw new Error(`LaunchAgent is not installed: ${plistPath}`);
  try {
    await execFileAsync("launchctl", ["bootstrap", domain, plistPath]);
  } catch {
    await execFileAsync("launchctl", ["kickstart", "-k", `${domain}/${LAUNCHD_LABEL}`]);
  }
  return { action: "start", status: "requested", plistPath };
}

async function stopLaunchd() {
  if (platform() !== "darwin") throw new Error("stop is only implemented for the optional macOS launchd wrapper");
  const domain = `gui/${process.getuid()}`;
  try {
    await execFileAsync("launchctl", ["bootout", `${domain}/${LAUNCHD_LABEL}`]);
    return { action: "stop", status: "stopped" };
  } catch (error) {
    return { action: "stop", status: "already-stopped", message: error.stderr?.trim() || error.message };
  }
}

async function uninstall() {
  const stopped = platform() === "darwin" ? await stopLaunchd() : { status: "not-applicable" };
  const plistPath = launchdPlistPath();
  if (platform() === "darwin" && await exists(plistPath)) await rm(plistPath);
  return {
    action: "uninstall",
    status: "uninstalled",
    stopped,
    preserved: ["config.json", "routes/", "task HTML", "images", "fonts", "approval fingerprints"],
    warning: "Historical URLs are offline until the service is reinstalled or served manually; route mappings were not deleted.",
  };
}

async function cleanLogs(stateDir) {
  const logs = [
    path.join(stateDir, "logs", "service.log"),
    path.join(stateDir, "logs", "service.log.1"),
    path.join(stateDir, "logs", "preview.out.log"),
    path.join(stateDir, "logs", "preview.err.log"),
  ];
  const cleaned = [];
  for (const log of logs) {
    if (await exists(log)) {
      await truncate(log, 0);
      cleaned.push(log);
    }
  }
  return { action: "clean-logs", cleaned };
}

async function registerRoute({ stateDir, taskId, version, directory, captureFile }) {
  assertSafeId(taskId, "task-id");
  assertSafeId(version, "version");
  if (!captureFile || path.basename(captureFile) !== captureFile) {
    throw new Error("capture must be a filename directly inside the registered version directory");
  }

  const config = await readConfig(stateDir);
  const resolvedDirectory = await realpath(path.resolve(directory));
  if (
    path.basename(resolvedDirectory) !== version ||
    path.basename(path.dirname(resolvedDirectory)) !== taskId
  ) {
    throw new Error("Registered directory must be <task-id>/<version>; refusing a broader or unrelated root");
  }
  const capturePath = await realpath(path.join(resolvedDirectory, captureFile));
  if (!isWithin(resolvedDirectory, capturePath)) throw new Error("Capture file resolves outside the version directory");
  if (!(await stat(capturePath)).isFile()) throw new Error("Capture path is not a file");

  return await withRouteLock(stateDir, taskId, version, async (target) => {
    const previous = await exists(target) ? JSON.parse(await readFile(target, "utf8")) : undefined;
    const prefix = `/image-to-editable-figma/${taskId}/${version}/`;
    if (previous && (
      previous.prefix !== prefix ||
      previous.directory !== resolvedDirectory ||
      previous.captureFile !== captureFile
    )) {
      throw new Error("Existing task/version route points elsewhere; refusing silent remap");
    }

    const now = new Date().toISOString();
    const registration = {
      schemaVersion: 1,
      taskId,
      version,
      prefix,
      directory: resolvedDirectory,
      captureFile,
      captureSha256: await sha256File(capturePath),
      registeredAt: previous?.registeredAt ?? now,
      updatedAt: now,
      lastVerifiedAt: previous?.lastVerifiedAt ?? null,
    };
    await atomicWriteJson(target, registration);
    return {
      ...registration,
      url: `http://${config.host}:${config.port}${prefix}${encodeURIComponent(captureFile)}`,
    };
  });
}

async function verifyRoute({ stateDir, taskId, version }) {
  assertSafeId(taskId, "task-id");
  assertSafeId(version, "version");
  const config = await readConfig(stateDir);
  return await withRouteLock(stateDir, taskId, version, async (target) => {
    const route = JSON.parse(await readFile(target, "utf8"));
    const identity = await probeIdentity(config.host, config.port, config.installationId);
    if (identity.status !== "running") throw new Error(`Preview service identity check failed: ${identity.status}`);

    const capturePath = await realpath(path.join(route.directory, route.captureFile));
    if (!isWithin(await realpath(route.directory), capturePath)) throw new Error("Capture file escaped the registered directory");
    const diskSha256 = await sha256File(capturePath);
    if (diskSha256 !== route.captureSha256) {
      throw new Error("Capture changed after registration; register the current version again before delivery");
    }

    const url = `http://${config.host}:${config.port}${route.prefix}${encodeURIComponent(route.captureFile)}`;
    const response = await requestBuffer(url, { timeoutMs: 5000 });
    if (response.statusCode !== 200) throw new Error(`Preview URL returned HTTP ${response.statusCode}`);
    const httpSha256 = createHash("sha256").update(response.body).digest("hex");
    if (httpSha256 !== diskSha256) throw new Error("HTTP response bytes do not match the disk Capture HTML");

    route.lastVerifiedAt = new Date().toISOString();
    await atomicWriteJson(target, route);
    return {
      status: "verified",
      url,
      taskId,
      version,
      diskSha256,
      httpSha256,
      cacheControl: response.headers["cache-control"],
      contentType: response.headers["content-type"],
    };
  });
}

async function statusReport(stateDir) {
  try {
    const config = await readConfig(stateDir);
    const probe = await probeIdentity(config.host, config.port, config.installationId);
    return { ...probe, stateDir, configuredPort: config.port };
  } catch (error) {
    if (error.code === "ENOENT") return { status: "not-installed", stateDir };
    throw error;
  }
}

async function rawRequest({ host, port, requestPath, method = "GET" }) {
  return await new Promise((resolve, reject) => {
    const request = httpRequest({ host, port, path: requestPath, method }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => resolve({ statusCode: response.statusCode, body: Buffer.concat(chunks) }));
    });
    request.on("error", reject);
    request.end();
  });
}

async function selfTest() {
  const stateDir = await mkdtemp(path.join(tmpdir(), "editable-figma-preview-test-"));
  const fixtureDir = path.join(stateDir, "fixture", "self-test", "v001");
  const parallelADir = path.join(stateDir, "workspace-a", "parallel-a", "v001");
  const parallelBDir = path.join(stateDir, "workspace-b", "parallel-b", "v001");
  const raceADir = path.join(stateDir, "workspace-c", "race", "v001");
  const raceBDir = path.join(stateDir, "workspace-d", "race", "v001");
  const outsidePath = path.join(stateDir, "outside.txt");
  const captureFile = "fixture-v001-capture.html";
  const captureBody = Buffer.from("<!doctype html><title>preview self test</title><main>ok</main>");
  const parallelABody = Buffer.from("<!doctype html><title>parallel a</title>");
  const parallelBBody = Buffer.from("<!doctype html><title>parallel b</title>");
  let server;
  let restarted;
  let dummy;
  try {
    await mkdir(path.join(stateDir, "routes"), { recursive: true });
    await mkdir(fixtureDir, { recursive: true });
    await mkdir(parallelADir, { recursive: true });
    await mkdir(parallelBDir, { recursive: true });
    await mkdir(raceADir, { recursive: true });
    await mkdir(raceBDir, { recursive: true });
    await writeFile(path.join(fixtureDir, captureFile), captureBody);
    await writeFile(path.join(parallelADir, "a-capture.html"), parallelABody);
    await writeFile(path.join(parallelBDir, "b-capture.html"), parallelBBody);
    await writeFile(path.join(raceADir, "race-capture.html"), "race-a");
    await writeFile(path.join(raceBDir, "race-capture.html"), "race-b");
    await writeFile(outsidePath, "secret");
    await symlink(outsidePath, path.join(fixtureDir, "outside-link.txt"));
    await atomicWriteJson(path.join(stateDir, "config.json"), {
      service: SERVICE_NAME,
      protocolVersion: PROTOCOL_VERSION,
      installationId: randomUUID(),
      host: DEFAULT_HOST,
      port: 0,
      createdAt: new Date().toISOString(),
    });
    const registration = await registerRoute({
      stateDir,
      taskId: "self-test",
      version: "v001",
      directory: fixtureDir,
      captureFile,
    });
    const [parallelA, parallelB] = await Promise.all([
      registerRoute({
        stateDir,
        taskId: "parallel-a",
        version: "v001",
        directory: parallelADir,
        captureFile: "a-capture.html",
      }),
      registerRoute({
        stateDir,
        taskId: "parallel-b",
        version: "v001",
        directory: parallelBDir,
        captureFile: "b-capture.html",
      }),
    ]);
    const race = await Promise.allSettled([
      registerRoute({ stateDir, taskId: "race", version: "v001", directory: raceADir, captureFile: "race-capture.html" }),
      registerRoute({ stateDir, taskId: "race", version: "v001", directory: raceBDir, captureFile: "race-capture.html" }),
    ]);
    if (race.filter((result) => result.status === "fulfilled").length !== 1) {
      throw new Error("same-route lock/remap self-test failed");
    }

    server = await startPreviewServer({ stateDir, port: 0 });
    const address = server.address();
    const port = address.port;
    const installedConfig = await readConfig(stateDir);
    await atomicWriteJson(path.join(stateDir, "config.json"), { ...installedConfig, port });
    const base = `http://${DEFAULT_HOST}:${port}`;
    const captureUrl = `${base}${new URL(registration.url).pathname}`;
    const identity = await requestBuffer(`${base}/.well-known/image-to-editable-figma-preview.json`);
    const get = await requestBuffer(captureUrl);
    const head = await requestBuffer(captureUrl, { method: "HEAD" });
    const directory = await requestBuffer(`${base}/image-to-editable-figma/self-test/v001/`);
    const traversal = await rawRequest({
      host: DEFAULT_HOST,
      port,
      requestPath: "/image-to-editable-figma/self-test/v001/%252e%252e/outside.txt",
    });
    const symlinkEscape = await requestBuffer(`${base}/image-to-editable-figma/self-test/v001/outside-link.txt`);
    const parallelAResponse = await requestBuffer(`${base}${new URL(parallelA.url).pathname}`);
    const parallelBResponse = await requestBuffer(`${base}${new URL(parallelB.url).pathname}`);
    if (identity.statusCode !== 200 || get.statusCode !== 200 || !get.body.equals(captureBody)) throw new Error("identity/get self-test failed");
    if (head.statusCode !== 200 || head.body.length !== 0) throw new Error("HEAD self-test failed");
    if (directory.statusCode !== 404 || traversal.statusCode !== 400 || symlinkEscape.statusCode !== 403) {
      throw new Error("route isolation self-test failed");
    }
    if (!parallelAResponse.body.equals(parallelABody) || !parallelBResponse.body.equals(parallelBBody)) {
      throw new Error("concurrent route registration self-test failed");
    }
    const verified = await verifyRoute({ stateDir, taskId: "self-test", version: "v001" });
    if (verified.diskSha256 !== verified.httpSha256) throw new Error("disk/http verification self-test failed");

    await new Promise((resolve) => server.close(resolve));
    server = undefined;
    restarted = await startPreviewServer({ stateDir });
    const restartedPort = restarted.address().port;
    const persisted = await requestBuffer(`http://${DEFAULT_HOST}:${restartedPort}${new URL(registration.url).pathname}`);
    if (persisted.statusCode !== 200 || !persisted.body.equals(captureBody)) throw new Error("restart persistence self-test failed");

    dummy = createHttpServer((_request, response) => response.end("not this service"));
    await new Promise((resolve, reject) => {
      dummy.once("error", reject);
      dummy.listen(0, DEFAULT_HOST, resolve);
    });
    const conflict = await probeIdentity(DEFAULT_HOST, dummy.address().port, "expected-id");
    if (conflict.status !== "unknown-service") throw new Error("unknown port owner self-test failed");

    return {
      status: "passed",
      checks: [
        "identity",
        "GET and HEAD",
        "no directory listing",
        "double-decoding rejection",
        "symlink escape rejection",
        "concurrent multi-task route isolation",
        "same-route lock and silent-remap rejection",
        "disk/HTTP byte verification",
        "route persistence after restart",
        "unknown port owner rejection",
      ],
    };
  } finally {
    if (server) await new Promise((resolve) => server.close(resolve));
    if (restarted) await new Promise((resolve) => restarted.close(resolve));
    if (dummy) await new Promise((resolve) => dummy.close(resolve));
    await rm(stateDir, { recursive: true, force: true });
  }
}

function help() {
  return {
    usage: "node scripts/preview-service.mjs <command> [options]",
    commands: {
      install: "install [--port 41972] [--no-launchd] --confirm-persistent-install",
      status: "status",
      serve: "serve (cross-platform foreground service)",
      start: "start (macOS launchd wrapper)",
      stop: "stop (macOS launchd wrapper)",
      restart: "restart (macOS launchd wrapper)",
      register: "register --task-id <id> --version <v001> --dir <absolute-dir> --capture <file>",
      verify: "verify --task-id <id> --version <v001>",
      uninstall: "uninstall (preserves routes and task files)",
      "clean-logs": "clean-logs",
      "self-test": "self-test",
    },
    commonOption: "--state-dir <absolute-dir>",
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const command = args._[0] ?? "help";
  if (command === "help" || command === "--help") return print(help());
  if (command === "install") return print(await install(args));
  if (command === "status") return print(await statusReport(args.stateDir));
  if (command === "serve") {
    const server = await startPreviewServer({ stateDir: args.stateDir });
    print({ status: "running", address: server.address(), stateDir: args.stateDir });
    const shutdown = () => server.close(() => process.exit(0));
    process.on("SIGINT", shutdown);
    process.on("SIGTERM", shutdown);
    return;
  }
  if (command === "start") return print(await startLaunchd());
  if (command === "stop") return print(await stopLaunchd());
  if (command === "restart") {
    await stopLaunchd();
    return print(await startLaunchd());
  }
  if (command === "uninstall") return print(await uninstall());
  if (command === "clean-logs") return print(await cleanLogs(args.stateDir));
  if (command === "register") return print(await registerRoute({
    stateDir: args.stateDir,
    taskId: args.values["task-id"],
    version: args.values.version,
    directory: args.values.dir,
    captureFile: args.values.capture,
  }));
  if (command === "verify") return print(await verifyRoute({
    stateDir: args.stateDir,
    taskId: args.values["task-id"],
    version: args.values.version,
  }));
  if (command === "self-test") return print(await selfTest());
  throw new Error(`Unknown command: ${command}`);
}

if (path.resolve(process.argv[1] ?? "") === SCRIPT_PATH) {
  main().catch((error) => {
    process.stderr.write(`${JSON.stringify({ status: "error", message: error.message })}\n`);
    process.exitCode = 1;
  });
}
