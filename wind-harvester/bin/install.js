#!/usr/bin/env node

const fs = require("fs");
const os = require("os");
const path = require("path");
const readline = require("readline/promises");
const { stdin, stdout, argv, exit } = require("process");

const PACKAGE_ROOT = path.resolve(__dirname, "..");
const SOURCE_ROOT = path.join(PACKAGE_ROOT, "src");
const COMPONENTS = {
  command: {
    label: "commands",
    source: path.join(SOURCE_ROOT, "command"),
    destination: "command",
  },
  skills: {
    label: "skills",
    source: path.join(SOURCE_ROOT, "skills"),
    destination: "skills",
  },
  windmill: {
    label: "windmill",
    source: path.join(SOURCE_ROOT, "windmill"),
    destination: "windmill",
  },
};

main().catch((error) => {
  console.error(`Install failed: ${error.message}`);
  exit(1);
});

async function main() {
  const options = parseArgs(argv.slice(2));
  if (options.help) {
    printHelp();
    return;
  }

  const resolvedTarget = options.target || (await promptForTarget());
  const targetRoot = resolveTargetRoot(resolvedTarget, options.cwd || process.cwd());
  const scopes = options.scope || (await promptForScope());
  const overwrite = options.force || (await promptForOverwrite());
  const operations = buildOperations(targetRoot, scopes);

  printPlan(targetRoot, scopes, overwrite, operations);

  if (!options.yes) {
    const confirmed = await promptYesNo("Proceed with install?", false);
    if (!confirmed) {
      console.log("Install cancelled.");
      return;
    }
  }

  for (const operation of operations) {
    if (!overwrite && fs.existsSync(operation.destination)) {
      console.log(`Skip existing file: ${operation.destination}`);
      continue;
    }

    fs.mkdirSync(path.dirname(operation.destination), { recursive: true });
    const contents = fs.readFileSync(operation.source, "utf8");
    fs.writeFileSync(
      operation.destination,
      rewriteContent(operation, contents),
      "utf8",
    );
    console.log(`Installed ${path.relative(targetRoot, operation.destination)}`);
  }

  console.log("\nDone.");
  console.log(`OpenCode target: ${targetRoot}`);
  console.log(`Installed scopes: ${scopes.join(", ")}`);
}

function parseArgs(args) {
  const options = { cwd: process.cwd() };

  for (let index = 0; index < args.length; index += 1) {
    const value = args[index];
    const next = args[index + 1];

    if (value === "--help" || value === "-h") {
      options.help = true;
      continue;
    }

    if (value === "--yes") {
      options.yes = true;
      continue;
    }

    if (value === "--force") {
      options.force = true;
      continue;
    }

    if (value === "--target") {
      assertValue(next, value);
      options.target = normalizeTarget(next);
      index += 1;
      continue;
    }

    if (value === "--scope") {
      assertValue(next, value);
      options.scope = normalizeScope(next);
      index += 1;
      continue;
    }

    if (value === "--cwd") {
      assertValue(next, value);
      options.cwd = path.resolve(next);
      index += 1;
      continue;
    }

    throw new Error(`Unknown argument: ${value}`);
  }

  return options;
}

function assertValue(value, flag) {
  if (!value || value.startsWith("--")) {
    throw new Error(`Missing value for ${flag}`);
  }
}

function normalizeTarget(value) {
  if (value !== "global" && value !== "local") {
    throw new Error(`Unsupported target: ${value}`);
  }
  return value;
}

function normalizeScope(value) {
  if (value === "all") {
    return Object.keys(COMPONENTS);
  }

  const scopes = value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);

  for (const scope of scopes) {
    if (!COMPONENTS[scope]) {
      throw new Error(`Unsupported scope: ${scope}`);
    }
  }

  return scopes;
}

function resolveTargetRoot(target, cwd) {
  if (target === "local") {
    return path.join(cwd, ".opencode");
  }

  const preferred = path.join(os.homedir(), ".config", "opencode");
  const legacy = path.join(os.homedir(), ".config", ".opencode");

  if (fs.existsSync(preferred) || !fs.existsSync(legacy)) {
    return preferred;
  }

  return legacy;
}

function buildOperations(targetRoot, scopes) {
  const operations = [];

  for (const scope of scopes) {
    const component = COMPONENTS[scope];
    const files = walkFiles(component.source);

    for (const filePath of files) {
      const relativePath = path.relative(component.source, filePath);
      operations.push({
        scope,
        source: filePath,
        targetRoot,
        destination: path.join(targetRoot, component.destination, relativePath),
      });
    }
  }

  return operations;
}

function walkFiles(directory) {
  const entries = fs.readdirSync(directory, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkFiles(entryPath));
    } else {
      files.push(entryPath);
    }
  }

  return files.sort();
}

function rewriteContent(operation, contents) {
  const destinationDirectory = path.dirname(operation.destination);
  const windmillRoot = path.relative(
    destinationDirectory,
    path.join(operation.targetRoot, "windmill", "harvest"),
  );
  const skillRoot = path.relative(
    destinationDirectory,
    path.join(operation.targetRoot, "skills", "harvest"),
  );

  return contents
    .replaceAll("{{WINDMILL_ROOT}}", normalizeLinkPath(windmillRoot))
    .replaceAll("{{SKILL_ROOT}}", normalizeLinkPath(skillRoot));
}

function normalizeLinkPath(value) {
  return value.split(path.sep).join("/");
}

function printPlan(targetRoot, scopes, overwrite, operations) {
  console.log("OpenCode installer\n");
  console.log(`Target: ${targetRoot}`);
  console.log(`Scopes: ${scopes.join(", ")}`);
  console.log(`Overwrite existing files: ${overwrite ? "yes" : "no"}`);
  console.log("Files:");
  for (const operation of operations) {
    console.log(`- ${operation.destination}`);
  }
  console.log("");
}

async function promptForTarget() {
  const answer = await promptText(
    [
      "Select install target:",
      "1) global (~/.config/opencode or legacy ~/.config/.opencode)",
      "2) local (./.opencode)",
    ].join("\n"),
  );

  if (answer === "1") {
    return "global";
  }
  if (answer === "2") {
    return "local";
  }
  throw new Error("Invalid target selection");
}

async function promptForScope() {
  const answer = await promptText(
    [
      "Select install scope:",
      "1) all",
      "2) commands only",
      "3) skills only",
      "4) windmill only",
      "5) commands + skills",
    ].join("\n"),
  );

  if (answer === "1") {
    return ["command", "skills", "windmill"];
  }
  if (answer === "2") {
    return ["command"];
  }
  if (answer === "3") {
    return ["skills"];
  }
  if (answer === "4") {
    return ["windmill"];
  }
  if (answer === "5") {
    return ["command", "skills"];
  }
  throw new Error("Invalid scope selection");
}

async function promptForOverwrite() {
  return promptYesNo("Overwrite existing harvest files?", false);
}

async function promptYesNo(message, defaultValue) {
  const suffix = defaultValue ? "[Y/n]" : "[y/N]";
  const answer = (await promptText(`${message} ${suffix}`)).toLowerCase();

  if (!answer) {
    return defaultValue;
  }

  return answer === "y" || answer === "yes";
}

async function promptText(message) {
  const rl = readline.createInterface({ input: stdin, output: stdout });
  try {
    return (await rl.question(`${message}\n> `)).trim();
  } finally {
    rl.close();
  }
}

function printHelp() {
  console.log(`Usage: node wind-harvester/bin/install.js [options]

Options:
  --target <global|local>   Install into the global or local OpenCode directory
  --scope <value>           Install all or a comma-separated subset of command,skills,windmill
  --force                   Overwrite existing files
  --yes                     Skip confirmation prompt
  --cwd <path>              Resolve the local install target from this directory
  --help                    Show this message`);
}
