#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import {
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readlinkSync,
  readdirSync,
  renameSync,
  rmSync,
} from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const packageJson = JSON.parse(readFileSync(join(packageRoot, "package.json"), "utf8"));
const version = readFileSync(join(packageRoot, "VERSION"), "utf8").trim();

if (packageJson.version !== version) {
  fail(`package.json is ${packageJson.version}, but VERSION is ${version}`);
}

const payload = [
  "AGENTS.md",
  "LICENSE",
  "THIRD-PARTY-NOTICES.md",
  "VERSION",
  "hooks",
  "install.sh",
  "operator-profiles",
  "operator-skills",
  "output-styles",
  "scripts",
  "skills",
  "templates",
  "uninstall.sh",
];

const profiles = new Set(["guard", "workflow", "operator", "full", "standard"]);
const installRoot = join(homedir(), ".local", "share", "agent-config");
const versionRoot = join(installRoot, version);

function fail(message) {
  process.stderr.write(`agent-config: ${message}\n`);
  process.exit(1);
}

function help() {
  process.stdout.write(`agent-config ${version}\n\n`);
  process.stdout.write("Usage:\n");
  process.stdout.write("  agent-config install [--extras] [--keep-existing|--replace-conflicts]\n");
  process.stdout.write("  agent-config doctor [--extras]\n");
  process.stdout.write("  agent-config init\n");
  process.stdout.write("  agent-config uninstall\n\n");
  process.stdout.write("Install adds guardrails, 13 workflow skills, and automatic routing.\n");
  process.stdout.write("Use --extras to add research, wizard, handoff, and output styles.\n");
}

function assertPlatform() {
  if (process.platform === "win32") {
    fail("native Windows is not supported. Use macOS or Linux");
  }
}

function run(script, args, cwd = process.cwd(), extraEnv = {}) {
  execFileSync("bash", [script, ...args], {
    cwd,
    env: { ...process.env, ...extraEnv },
    stdio: "inherit",
  });
}

function verifyPayload(source, target, relative) {
  if (!existsSync(target)) {
    fail(`${versionRoot} is missing ${relative}`);
  }
  const sourceStat = lstatSync(source);
  const targetStat = lstatSync(target);
  if (sourceStat.isSymbolicLink() || targetStat.isSymbolicLink()) {
    fail(`${versionRoot}/${relative} must not be a symlink`);
  }
  if (sourceStat.isDirectory()) {
    if (!targetStat.isDirectory()) {
      fail(`${versionRoot}/${relative} does not match the published package`);
    }
    for (const name of readdirSync(source)) {
      verifyPayload(join(source, name), join(target, name), join(relative, name));
    }
    return;
  }
  if (!sourceStat.isFile() || !targetStat.isFile()
      || !readFileSync(source).equals(readFileSync(target))) {
    fail(`${versionRoot}/${relative} does not match the published package`);
  }
}

function stagePayload() {
  if (existsSync(versionRoot)) {
    if (!existsSync(join(versionRoot, "VERSION"))) {
      fail(`${versionRoot} exists but is not a valid ${version} installation`);
    }
    const installedVersion = readFileSync(join(versionRoot, "VERSION"), "utf8").trim();
    if (installedVersion !== version || !existsSync(join(versionRoot, "install.sh"))) {
      fail(`${versionRoot} exists but is not a valid ${version} installation`);
    }
    for (const relative of payload) {
      verifyPayload(join(packageRoot, relative), join(versionRoot, relative), relative);
    }
    return versionRoot;
  }

  mkdirSync(installRoot, { recursive: true });
  const staging = join(installRoot, `.${version}-${process.pid}`);
  if (existsSync(staging)) {
    fail(`temporary installation path already exists: ${staging}`);
  }

  mkdirSync(staging);
  try {
    for (const relative of payload) {
      const source = join(packageRoot, relative);
      if (!existsSync(source)) {
        fail(`published package is missing ${relative}`);
      }
      cpSync(source, join(staging, relative), { recursive: true, errorOnExist: true });
    }
    renameSync(staging, versionRoot);
  } catch (error) {
    if (existsSync(staging)) {
      rmSync(staging, { recursive: true, force: true });
    }
    throw error;
  }
  return versionRoot;
}

function parseProfile(args, fallback) {
  const profile = args[0] && profiles.has(args[0]) ? args.shift() : fallback;
  return profile;
}

function installedRoot() {
  const candidates = [versionRoot];
  const claudeRoot = process.env.CLAUDE_CONFIG_DIR || join(homedir(), ".claude");
  const origins = join(claudeRoot, ".agent-config-origins");
  if (existsSync(origins)) {
    candidates.push(...readFileSync(origins, "utf8").split(/\r?\n/).filter(Boolean).reverse());
  }
  return candidates.find((candidate) =>
    existsSync(join(candidate, "VERSION")) && existsSync(join(candidate, "install.sh"))
  );
}

function extrasInstalled() {
  const claudeRoot = process.env.CLAUDE_CONFIG_DIR || join(homedir(), ".claude");
  const candidates = [
    ...["research", "wizard", "handoff"].map((name) =>
      join(claudeRoot, "skills", name)),
    join(claudeRoot, "output-styles", "terse.md"),
  ];
  return candidates.some((candidate) => {
    try {
      return lstatSync(candidate).isSymbolicLink()
        && /\/(operator-skills|output-styles)\//.test(readlinkSync(candidate));
    } catch {
      return false;
    }
  });
}

function install(args) {
  assertPlatform();
  const legacyProfile = args[0] && profiles.has(args[0]);
  let profile = parseProfile(args, "standard");
  if (args.includes("--extras")) {
    if (legacyProfile) fail("--extras cannot be combined with a legacy install profile");
    profile = "full";
    args = args.filter((arg) => arg !== "--extras");
  }
  for (const arg of args) {
    if (!["--baseline", "--skills-only", "--keep-existing", "--replace-conflicts"].includes(arg)) {
      fail(`unknown install option: ${arg}`);
    }
  }
  const root = stagePayload();
  run(join(root, "install.sh"), [profile, ...args], process.cwd(),
      { AGENT_CONFIG_COMPACT: "1" });
}

function doctor(args) {
  assertPlatform();
  const explicitProfile = args[0] && profiles.has(args[0]);
  let profile = parseProfile(args, extrasInstalled() ? "full" : "standard");
  if (args[0] === "--extras") {
    profile = "full";
    args.shift();
  }
  if (explicitProfile && args[0] === "--extras") {
    fail("--extras cannot be combined with a legacy doctor profile");
  }
  if (args.length) {
    fail(`unknown doctor option: ${args[0]}`);
  }
  const root = installedRoot();
  if (!root) {
    fail("no installed payload found. Run install first");
  }
  run(join(root, "install.sh"), [profile, "--check"], process.cwd(),
      { AGENT_CONFIG_COMPACT: "1" });
}

function init(args) {
  assertPlatform();
  if (args.length) {
    fail(`init takes no arguments: ${args[0]}`);
  }
  run(join(packageRoot, "scripts", "agent-init"), [], process.cwd());
}

function uninstall(args) {
  assertPlatform();
  const profile = parseProfile(args, "full");
  if (args.length) {
    fail(`unknown uninstall option: ${args[0]}`);
  }
  const root = installedRoot();
  if (!root) {
    fail("no installed payload found");
  }
  run(join(root, "uninstall.sh"), [profile]);
}

const [command = "help", ...args] = process.argv.slice(2);

try {
  if (command === "help" || command === "--help" || command === "-h") help();
  else if (command === "--version" || command === "-v") process.stdout.write(`${version}\n`);
  else if (command === "install") install(args);
  else if (command === "doctor" || command === "check") doctor(args);
  else if (command === "init") init(args);
  else if (command === "uninstall") uninstall(args);
  else fail(`unknown command: ${command}`);
} catch (error) {
  if (error && typeof error.status === "number") {
    process.exit(error.status || 1);
  }
  fail(error instanceof Error ? error.message : String(error));
}
