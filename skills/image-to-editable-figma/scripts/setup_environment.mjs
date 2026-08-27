#!/usr/bin/env node

import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
const SCRIPT_PATH = fileURLToPath(import.meta.url);
const SKILL_ROOT = path.resolve(path.dirname(SCRIPT_PATH), "..");
const BOOTSTRAP_PATH = path.join(SKILL_ROOT, "scripts", "bootstrap.mjs");
const TOOLING_DIR = path.join(SKILL_ROOT, "tooling");
const LOCAL_STATE_PATH = path.join(TOOLING_DIR, ".local-state.json");
const SETUP_VERSION = 1;

const REQUIRED_RUNTIME_CAPABILITIES = [
  "figma-codex-plugin",
  "figma-connector-auth",
  "chrome-codex-plugin",
  "chatgpt-browser-extension",
  "computer-use-plugin",
  "macos-accessibility",
  "macos-screen-recording",
  "figma-browser-extension",
];

const INSTALL_PATHS = {
  chrome: "https://www.google.com/chrome/",
  node: "https://nodejs.org/en/download",
  python: "https://www.python.org/downloads/",
  pillow: "python3 -m pip install Pillow",
  numpy: "python3 -m pip install numpy",
  opencv: "python3 -m pip install opencv-python",
  figmaCodexPlugin: "Codex → 设置 → 插件 → Figma",
  chromeCodexPlugin: "Codex → 设置 → 插件 → Chrome",
  chatgptBrowserExtension: "Codex → 设置 → Computer use → 安装 Chrome 扩展",
  computerUsePlugin: "Codex → 设置 → 插件 → Computer Use",
  macosAccessibility: "系统设置 → 隐私与安全性 → 辅助功能",
  macosScreenRecording: "系统设置 → 隐私与安全性 → 屏幕与系统音频录制",
  figmaBrowserExtension:
    "https://chromewebstore.google.com/detail/figma/fkmaohpngenfoccdgceedjkfhkdcohmg",
};

function parseJson(text, label) {
  try {
    return JSON.parse(text);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`${label} did not return valid JSON: ${detail}`);
  }
}

async function readLocalState() {
  try {
    const raw = await fs.readFile(LOCAL_STATE_PATH, "utf8");
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ENOENT") return {};
    if (error instanceof SyntaxError) return {};
    throw error;
  }
}

async function writeLocalState(state) {
  await fs.mkdir(TOOLING_DIR, { recursive: true });
  const temporaryPath = `${LOCAL_STATE_PATH}.${process.pid}.tmp`;
  await fs.writeFile(temporaryPath, `${JSON.stringify(state, null, 2)}\n`, "utf8");
  await fs.rename(temporaryPath, LOCAL_STATE_PATH);
}

async function runBootstrap(args) {
  try {
    const { stdout } = await execFileAsync(process.execPath, [BOOTSTRAP_PATH, ...args], {
      cwd: SKILL_ROOT,
      timeout: 180_000,
      maxBuffer: 4 * 1024 * 1024,
    });
    return parseJson(stdout.trim(), `bootstrap ${args.join(" ")}`);
  } catch (error) {
    const stdout =
      error && typeof error === "object" && typeof error.stdout === "string"
        ? error.stdout.trim()
        : "";
    if (stdout) return parseJson(stdout, `bootstrap ${args.join(" ")}`);
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`bootstrap ${args.join(" ")} failed: ${detail}`);
  }
}

async function prepareLocalEnvironment() {
  let local = await runBootstrap(["--check", "--source-dir", process.cwd()]);
  const autoFixed = [];

  if (!local.required?.hugeicons?.available) {
    await runBootstrap(["--ensure-hugeicons", "--source-dir", process.cwd()]);
    autoFixed.push("hugeicons");
    local = await runBootstrap(["--check", "--source-dir", process.cwd()]);
  }

  const required = local.required ?? {};
  const missingLocal = Object.entries(required)
    .filter(([, value]) => !value?.available)
    .map(([name]) => ({
      name,
      installPath: INSTALL_PATHS[name] ?? null,
      detail: required[name]?.detail ?? "Unavailable",
    }));

  const runtimeRequirements = [
    {
      capability: "figma-codex-plugin",
      check: "Codex runtime tool discovery",
      authorization: "Forward the real Figma connector Connect/Authorize button when returned.",
      installPath: INSTALL_PATHS.figmaCodexPlugin,
    },
    {
      capability: "figma-connector-auth",
      check: "Minimal read-only Figma identity or plan query",
      authorization: "Forward the real connector authorization UI; never invent a button.",
      installPath: INSTALL_PATHS.figmaCodexPlugin,
    },
    {
      capability: "chrome-codex-plugin",
      check: "Codex runtime tool discovery and connection-only Chrome probe",
      installPath: INSTALL_PATHS.chromeCodexPlugin,
    },
    {
      capability: "chatgpt-browser-extension",
      check: "Chrome connection succeeds without reading tabs or profile data",
      installPath: INSTALL_PATHS.chatgptBrowserExtension,
    },
    {
      capability: "computer-use-plugin",
      check: "Codex runtime tool discovery and harmless read-only app-state probe",
      installPath: INSTALL_PATHS.computerUsePlugin,
    },
    {
      capability: "macos-accessibility",
      check: "Computer Use read-only probe succeeds",
      authorization: "Use the real macOS permission button when shown.",
      installPath: INSTALL_PATHS.macosAccessibility,
    },
    {
      capability: "macos-screen-recording",
      check: "Computer Use returns an app screenshot when needed",
      authorization: "Use the real macOS permission button when shown.",
      installPath: INSTALL_PATHS.macosScreenRecording,
    },
    {
      capability: "figma-browser-extension",
      check: "Visible extension state or user-confirmed installation; never scan Chrome profiles",
      installPath: INSTALL_PATHS.figmaBrowserExtension,
    },
  ];

  const result = {
    setupVersion: SETUP_VERSION,
    status: missingLocal.length === 0 ? "local-ready" : "needs-local-setup",
    local: {
      ok: missingLocal.length === 0,
      required,
      figmaMcp: local.figmaMcp ?? null,
    },
    autoFixed,
    missingLocal,
    runtimeRequirements,
    manualActions: runtimeRequirements.map(({ capability, installPath }) => ({
      capability,
      installPath,
    })),
    note:
      "Run Codex runtime checks from references/first-install-setup.md. Normal image conversion tasks must not read this setup state.",
  };

  const state = await readLocalState();
  state.firstInstallEnvironmentSetup = {
    setupVersion: SETUP_VERSION,
    status: result.status,
    preparedAt: new Date().toISOString(),
    autoFixed,
    missingLocal: missingLocal.map((item) => item.name),
  };
  await writeLocalState(state);
  return result;
}

function parseArgs(argv) {
  const options = { mode: null, verifiedCapabilities: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--prepare") {
      options.mode = "prepare";
    } else if (argument === "--status") {
      options.mode = "status";
    } else if (argument === "--mark-complete") {
      options.mode = "mark-complete";
    } else if (argument === "--verified-capabilities") {
      const value = argv[index + 1];
      if (!value) throw new Error("--verified-capabilities requires a comma-separated value.");
      options.verifiedCapabilities = value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      index += 1;
    } else {
      throw new Error(`Unknown option: ${argument}`);
    }
  }
  if (!options.mode) {
    throw new Error("Choose one mode: --prepare, --status, or --mark-complete.");
  }
  return options;
}

async function getStatus() {
  const state = await readLocalState();
  return {
    setupVersion: SETUP_VERSION,
    stateFile: LOCAL_STATE_PATH,
    setup: state.firstInstallEnvironmentSetup ?? {
      setupVersion: SETUP_VERSION,
      status: "not-initialized",
    },
    note: "This state is installation-only. Normal image conversion tasks must not read it.",
  };
}

async function markComplete(verifiedCapabilities) {
  const unique = [...new Set(verifiedCapabilities)].sort();
  const required = [...REQUIRED_RUNTIME_CAPABILITIES].sort();
  const missing = required.filter((item) => !unique.includes(item));
  const unknown = unique.filter((item) => !required.includes(item));
  if (missing.length || unknown.length) {
    throw new Error(
      `Cannot mark setup complete. Missing: ${missing.join(", ") || "none"}. ` +
        `Unknown: ${unknown.join(", ") || "none"}.`,
    );
  }

  const state = await readLocalState();
  const prepared = state.firstInstallEnvironmentSetup;
  if (!prepared || prepared.setupVersion !== SETUP_VERSION) {
    throw new Error("Run --prepare successfully before --mark-complete.");
  }
  if (prepared.status !== "local-ready" && prepared.status !== "all-path-ready") {
    throw new Error(
      `Local environment is not ready (current status: ${prepared.status}). Re-run --prepare after fixing local requirements.`,
    );
  }

  state.firstInstallEnvironmentSetup = {
    ...prepared,
    setupVersion: SETUP_VERSION,
    status: "all-path-ready",
    completedAt: new Date().toISOString(),
    verifiedCapabilities: required,
  };
  await writeLocalState(state);
  return getStatus();
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.mode === "prepare") {
    console.log(JSON.stringify(await prepareLocalEnvironment(), null, 2));
    return;
  }
  if (options.mode === "status") {
    console.log(JSON.stringify(await getStatus(), null, 2));
    return;
  }
  console.log(JSON.stringify(await markComplete(options.verifiedCapabilities), null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
