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
const TOOLING_DIR = path.join(SKILL_ROOT, "tooling");
const LOCAL_STATE_PATH = path.join(TOOLING_DIR, ".local-state.json");
const HUGEICONS_RELATIVE_DIR = path.join(
  "node_modules",
  "@hugeicons",
  "core-free-icons",
  "dist",
  "esm",
);
const FIGMA_EXTENSION = {
  name: "Figma",
  chromeWebStoreUrl:
    "https://chromewebstore.google.com/detail/figma/fkmaohpngenfoccdgceedjkfhkdcohmg",
  extensionId: "fkmaohpngenfoccdgceedjkfhkdcohmg",
  publisher: "Figma, Inc.",
  required: false,
};
const EXTENSION_ONBOARDING_STATUSES = new Set(["prompted", "installed", "skipped"]);

async function isDirectory(candidate) {
  try {
    return (await fs.stat(candidate)).isDirectory();
  } catch {
    return false;
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

async function getExtensionOnboardingStatus() {
  const state = await readLocalState();
  const onboarding = state.figmaBrowserExtensionOnboarding;
  const status = EXTENSION_ONBOARDING_STATUSES.has(onboarding?.status)
    ? onboarding.status
    : null;
  return {
    ...FIGMA_EXTENSION,
    detection: "manual",
    stateFile: LOCAL_STATE_PATH,
    status,
    shouldPrompt: status === null,
    detail: "This optional state only controls whether first-use guidance is repeated.",
  };
}

async function markExtensionOnboarding(status) {
  if (!EXTENSION_ONBOARDING_STATUSES.has(status)) {
    throw new Error(
      `Extension onboarding status must be one of: ${[...EXTENSION_ONBOARDING_STATUSES].join(", ")}.`,
    );
  }
  const state = await readLocalState();
  state.figmaBrowserExtensionOnboarding = {
    status,
    updatedAt: new Date().toISOString(),
  };
  await writeLocalState(state);
  return getExtensionOnboardingStatus();
}

async function findTaskHugeiconsDir(startDir) {
  let current = path.resolve(startDir);
  while (true) {
    const candidate = path.join(current, HUGEICONS_RELATIVE_DIR);
    if (await isDirectory(candidate)) return candidate;
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return null;
}

export async function findHugeiconsDir(startDir, explicitDir) {
  if (explicitDir) {
    const candidate = path.resolve(explicitDir);
    if (!(await isDirectory(candidate))) {
      throw new Error(`Explicit Hugeicons directory does not exist: ${candidate}`);
    }
    return { dir: candidate, source: "explicit" };
  }

  const taskDir = await findTaskHugeiconsDir(startDir);
  if (taskDir) return { dir: taskDir, source: "task" };

  const skillDir = path.join(TOOLING_DIR, HUGEICONS_RELATIVE_DIR);
  if (await isDirectory(skillDir)) return { dir: skillDir, source: "skill-tooling" };
  return null;
}

async function installSkillHugeicons() {
  await fs.mkdir(TOOLING_DIR, { recursive: true });
  const npmExecutable = process.platform === "win32" ? "npm.cmd" : "npm";
  try {
    await execFileAsync(
      npmExecutable,
      [
        "install",
        "--omit=dev",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
        "--package-lock=false",
      ],
      {
        cwd: TOOLING_DIR,
        timeout: 120_000,
        maxBuffer: 4 * 1024 * 1024,
      },
    );
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(
      `Hugeicons one-time initialization failed: ${detail}\n` +
        `Run manually: cd "${TOOLING_DIR}" && npm install --omit=dev --ignore-scripts --package-lock=false`,
    );
  }
}

export async function ensureHugeiconsDir(startDir, explicitDir) {
  const existing = await findHugeiconsDir(startDir, explicitDir);
  if (existing) return existing;

  console.error(
    "Hugeicons is not available in the task or skill tooling; running one-time skill-local initialization.",
  );
  await installSkillHugeicons();
  const initialized = await findHugeiconsDir(startDir, explicitDir);
  if (!initialized) {
    throw new Error(
      `Hugeicons initialization completed but the expected package directory is missing under ${TOOLING_DIR}.`,
    );
  }
  return { ...initialized, initialized: true };
}

async function commandStatus(command, args) {
  try {
    const { stdout } = await execFileAsync(command, args, {
      timeout: 10_000,
      maxBuffer: 1024 * 1024,
    });
    return { available: true, detail: stdout.trim() };
  } catch (error) {
    return {
      available: false,
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}

async function chromeStatus() {
  const candidates =
    process.platform === "darwin"
      ? [
          "/Applications/Google Chrome.app",
          path.join(process.env.HOME ?? "", "Applications/Google Chrome.app"),
        ]
      : process.platform === "win32"
        ? [
            path.join(process.env.PROGRAMFILES ?? "", "Google/Chrome/Application/chrome.exe"),
            path.join(process.env["PROGRAMFILES(X86)"] ?? "", "Google/Chrome/Application/chrome.exe"),
          ]
        : ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium"];

  for (const candidate of candidates) {
    if (candidate && (await isDirectory(candidate))) {
      return { available: true, detail: candidate };
    }
    try {
      if (candidate && (await fs.stat(candidate)).isFile()) {
        return { available: true, detail: candidate };
      }
    } catch {
      // Try the next common installation path.
    }
  }
  return { available: false, detail: "Google Chrome was not found in common installation paths." };
}

function parseCliArgs(argv) {
  const options = { mode: "check", sourceDir: process.cwd(), onboardingStatus: null };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--check") {
      options.mode = "check";
    } else if (argument === "--ensure-hugeicons") {
      options.mode = "ensure-hugeicons";
    } else if (argument === "--extension-onboarding-status") {
      options.mode = "extension-onboarding-status";
    } else if (argument === "--mark-extension-onboarding") {
      const value = argv[index + 1];
      if (!value) throw new Error("--mark-extension-onboarding requires prompted, installed, or skipped.");
      options.mode = "mark-extension-onboarding";
      options.onboardingStatus = value;
      index += 1;
    } else if (argument === "--source-dir") {
      const value = argv[index + 1];
      if (!value) throw new Error("--source-dir requires a path.");
      options.sourceDir = path.resolve(value);
      index += 1;
    } else {
      throw new Error(`Unknown option: ${argument}`);
    }
  }
  return options;
}

async function runCheck(sourceDir) {
  const [npm, python, pillow, chrome, hugeicons] = await Promise.all([
    commandStatus(process.platform === "win32" ? "npm.cmd" : "npm", ["--version"]),
    commandStatus("python3", ["--version"]),
    commandStatus("python3", ["-c", "import PIL; print(PIL.__version__)"]),
    chromeStatus(),
    findHugeiconsDir(sourceDir),
  ]);
  const required = {
    node: { available: true, detail: process.version },
    npm,
    python,
    pillow,
    chrome,
    hugeicons: hugeicons
      ? { available: true, detail: hugeicons.dir, source: hugeicons.source }
      : {
          available: false,
          detail: "Run this script with --ensure-hugeicons, or let the Capture builder initialize it when first needed.",
        },
  };
  const ok = Object.values(required).every((item) => item.available);
  console.log(
    JSON.stringify(
      {
        ok,
        mode: "read-only-check",
        required,
        figmaMcp: {
          check: "deferred",
          detail: "Codex verifies Figma MCP availability when the approved Figma stage begins.",
        },
        figmaBrowserExtension: {
          ...(await getExtensionOnboardingStatus()),
          detail: "The extension is optional and is not a blocker for the official Capture flow.",
        },
      },
      null,
      2,
    ),
  );
  process.exitCode = ok ? 0 : 1;
}

async function main() {
  const options = parseCliArgs(process.argv.slice(2));
  if (options.mode === "extension-onboarding-status") {
    console.log(JSON.stringify(await getExtensionOnboardingStatus(), null, 2));
    return;
  }
  if (options.mode === "mark-extension-onboarding") {
    console.log(
      JSON.stringify(await markExtensionOnboarding(options.onboardingStatus), null, 2),
    );
    return;
  }
  if (options.mode === "ensure-hugeicons") {
    const result = await ensureHugeiconsDir(options.sourceDir);
    console.log(JSON.stringify({ ok: true, hugeicons: result }, null, 2));
    return;
  }
  await runCheck(options.sourceDir);
}

if (process.argv[1] && path.resolve(process.argv[1]) === SCRIPT_PATH) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
