#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import {
  cpSync, existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync,
} from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const version = readFileSync(join(packageRoot, "VERSION"), "utf8").trim();
const fix = "npx @sid-thephysicskid/agent-config@latest install";
const payload = [
  "LICENSE",
  "VERSION",
  "hooks",
  "install.sh",
  "uninstall.sh",
  "scripts/install_settings.py",
  "scripts/install_codex_hooks.py",
  "scripts/migrate-legacy.sh",
];
const installRoot = join(homedir(), ".local", "share", "agent-config");
const versionRoot = join(installRoot, version);
const skip = (name) => name === "__pycache__";

function fail(message) {
  process.stderr.write(`agent-config: ${message}\n`);
  process.exit(1);
}

function run(script, args = []) {
  execFileSync("bash", [script, ...args], { stdio: "inherit" });
}

function verify(source, target, relative) {
  const sourceStat = lstatSync(source);
  const targetStat = existsSync(target) ? lstatSync(target) : null;
  const same = targetStat && !targetStat.isSymbolicLink()
    && (sourceStat.isDirectory()
      ? targetStat.isDirectory()
      : targetStat.isFile() && readFileSync(source).equals(readFileSync(target)));
  if (!same) fail(`${versionRoot}/${relative} does not match the published package`);
  if (sourceStat.isDirectory()) {
    for (const name of readdirSync(source).filter((n) => !skip(n))) {
      verify(join(source, name), join(target, name), join(relative, name));
    }
  }
}

function verifyPayload() {
  for (const relative of payload) {
    verify(join(packageRoot, relative), join(versionRoot, relative), relative);
  }
}

// Staged under a versioned path so hooks outlive the npx cache.
function stagePayload() {
  if (existsSync(versionRoot)) return verifyPayload();
  const staging = join(installRoot, `.${version}-${process.pid}`);
  mkdirSync(staging, { recursive: true });
  try {
    for (const relative of payload) {
      mkdirSync(dirname(join(staging, relative)), { recursive: true });
      cpSync(join(packageRoot, relative), join(staging, relative), {
        recursive: true,
        filter: (path) => !skip(path.split("/").pop()),
      });
    }
    renameSync(staging, versionRoot);
  } finally {
    rmSync(staging, { recursive: true, force: true });
  }
}

function noArgs(command, args) {
  // `install guard` is what the 0.4 README told people to type.
  const rest = args.filter((arg) => arg !== "guard");
  if (rest.length) fail(`unknown ${command} option: ${rest[0]}`);
}

const commands = {
  install(args) {
    noArgs("install", args);
    stagePayload();
    run(join(versionRoot, "install.sh"));
  },
  doctor(args) {
    noArgs("doctor", args);
    if (!existsSync(versionRoot)) fail(`${version} is not installed. Run: ${fix}`);
    verifyPayload();
    try {
      run(join(versionRoot, "install.sh"), ["--check"]);
    } catch (error) {
      process.stdout.write(`Fix: ${fix}\n`);
      throw error;
    }
  },
  uninstall(args) {
    noArgs("uninstall", args);
    run(join(packageRoot, "uninstall.sh"));
  },
};

const [command = "--help", ...args] = process.argv.slice(2);
try {
  if (process.platform === "win32") fail("Windows is not supported. Use macOS, Linux, or WSL");
  if (command === "--help" || command === "-h" || command === "help") {
    process.stdout.write(`agent-config ${version}\n\nUsage:\n`
      + "  agent-config install     install or repair the guard\n"
      + "  agent-config doctor      check the guard is wired and deciding\n"
      + "  agent-config uninstall   remove it\n"
      + "  agent-config --version\n");
  } else if (command === "--version" || command === "-v") {
    process.stdout.write(`${version}\n`);
  } else if (Object.hasOwn(commands, command)) {
    commands[command](args);
  } else {
    fail(`unknown command: ${command}`);
  }
} catch (error) {
  if (error && typeof error.status === "number") process.exit(error.status || 1);
  fail(error instanceof Error ? error.message : String(error));
}
