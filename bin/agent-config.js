#!/usr/bin/env node

import { execFileSync, spawnSync } from "node:child_process";
import {
  chmodSync, cpSync, existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, realpathSync, renameSync,
  rmSync, writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const version = readFileSync(join(packageRoot, "VERSION"), "utf8").trim();
const fix = "npx @sid-thephysicskid/agent-config@latest install";
const payload = [
  "LICENSE",
  "VERSION",
  ...readdirSync(join(packageRoot, "hooks")).filter((n) => /^guard.*\.py$/.test(n)).map((n) => `hooks/${n}`),
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

async function readValue(name) {
  if (!process.stdin.isTTY) return readFileSync(0, "utf8").replace(/\r?\n$/, "");
  const { stdin, stderr } = process;
  stderr.write(`${name}: `);
  stdin.setRawMode(true);
  stdin.setEncoding("utf8");
  let value = "";
  const result = await new Promise((done) => {
    stdin.on("data", (chunk) => {
      for (const ch of chunk) {
        if (ch === "\u0003") return done("");
        if (ch === "\r" || ch === "\n" || ch === "\u0004") return done(value);
        if (ch === "\u007f" || ch === "\b") value = value.slice(0, -1);
        else if (ch >= " ") value += ch;
      }
    });
    stdin.resume();
  });
  stdin.setRawMode(false);
  stdin.pause();
  stderr.write("\n");
  return result;
}

// Single quotes are literal in shells and dotenv parsers; double quotes only when the value has one.
function envValue(value) {
  if (!/[\s#'"\\$`]/.test(value)) return value;
  if (!value.includes("'")) return `'${value}'`;
  return `"${value.replace(/[\\"$`]/g, "\\$&")}"`;
}

function writeEnv(file, name, value) {
  const target = existsSync(file) ? realpathSync(file) : file;
  // latin1 maps bytes 1:1, so every other byte of the file survives untouched.
  const old = existsSync(target) ? readFileSync(target).toString("latin1") : "";
  const quoted = Buffer.from(envValue(value)).toString("latin1");
  const key = new RegExp(`^(\\s*(?:export\\s+)?${name}\\s*=)[^\\r]*`);
  let found = false;
  let text = old.split("\n").map((line) => line.replace(key, (_, lead) => {
    found = true;
    return lead + quoted;
  })).join("\n");
  if (!found) text += `${text && !text.endsWith("\n") ? "\n" : ""}${name}=${quoted}\n`;
  const tmp = join(dirname(target), `.${basename(target)}.agent-config-${process.pid}`);
  try {
    writeFileSync(tmp, Buffer.from(text, "latin1"), { mode: 0o600, flag: "wx" });
    chmodSync(tmp, 0o600);
    renameSync(tmp, target);
  } finally {
    rmSync(tmp, { force: true });
  }
  process.stdout.write(`wrote ${name} to ${file}\n`);
  const git = spawnSync("git", ["check-ignore", "-q", resolve(file)], { cwd: dirname(resolve(file)), stdio: "ignore" });
  if (git.status === 1) process.stderr.write(`agent-config: ${file} is not gitignored. Add it to .gitignore before you commit.\n`);
}

function setGithubSecret(name, value, repo) {
  const gh = spawnSync("gh", ["secret", "set", name, ...(repo ? ["--repo", repo] : [])],
    { input: value, stdio: ["pipe", "inherit", "inherit"] });
  if (gh.error?.code === "ENOENT") fail("gh is not installed. Get it from https://cli.github.com");
  if (gh.error) throw gh.error;
  if (gh.status) process.exit(gh.status);
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
  async secret(args) {
    let name; let file; let github = false; let repo;
    for (let i = 0; i < args.length; i += 1) {
      if (args[i] === "--env" && args[i + 1]) file = args[++i];
      else if (args[i] === "--github") {
        github = true;
        if (/^[\w.-]+\/[\w.-]+$/.test(args[i + 1] ?? "")) repo = args[++i];
      } else if (!name && !args[i].startsWith("-")) name = args[i];
      else fail(`unknown secret option: ${args[i]}`);
    }
    if (!/^[A-Z_][A-Z0-9_]*$/.test(name ?? "")) {
      fail("usage: agent-config secret NAME [--env FILE] [--github [OWNER/REPO]], NAME like OPENAI_API_KEY");
    }
    const value = await readValue(name);
    if (!value) fail("no value entered. Nothing was written.");
    if (github) setGithubSecret(name, value, repo);
    if (file || !github) writeEnv(file ?? ".env", name, value);
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
      + "  agent-config secret NAME [--env FILE] [--github [OWNER/REPO]]\n"
      + "                           save a secret to .env (or GitHub) without pasting it into chat\n"
      + "  agent-config --version\n");
  } else if (command === "--version" || command === "-v") {
    process.stdout.write(`${version}\n`);
  } else if (Object.hasOwn(commands, command)) {
    await commands[command](args);
  } else {
    fail(`unknown command: ${command}`);
  }
} catch (error) {
  if (error && typeof error.status === "number") process.exit(error.status || 1);
  fail(error instanceof Error ? error.message : String(error));
}
