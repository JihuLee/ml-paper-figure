#!/usr/bin/env node
// Installs the ml-paper-figure agent skill by copying it into an agent's skills folder.
// Usage: npx github:JihuLee/ml-paper-figure [--global | --project | --agents | --dir <path>] [--force]
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');

const SKILL = 'ml-paper-figure';
const SRC = path.join(__dirname, '..', '.claude', 'skills', SKILL);
const PKG = require('../package.json');
const MARKER = '.install.json';
const SKIP = new Set(['__pycache__', '.DS_Store', MARKER]);

const HELP = `${SKILL} ${PKG.version}: install the ML paper Figure 1 skill

Usage
  npx github:JihuLee/${SKILL} [target] [options]

Targets (default: --global)
  -g, --global      ~/.claude/skills/${SKILL}   Claude Code, every project
  -p, --project     ./.claude/skills/${SKILL}   Claude Code, this project only
  -a, --agents      ./.agents/skills/${SKILL}   agents that read .agents/skills
      --dir <path>  <path>/${SKILL}

Options
  -f, --force       replace an existing install (use this to update)
      --uninstall   remove the skill from the target
      --dry-run     show what would happen, change nothing
  -h, --help        show this help
  -v, --version     print the version
`;

function parse(argv) {
  const o = { target: 'global', dir: null, force: false, uninstall: false, dryRun: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-g' || a === '--global') o.target = 'global';
    else if (a === '-p' || a === '--project') o.target = 'project';
    else if (a === '-a' || a === '--agents') o.target = 'agents';
    else if (a === '--dir') {
      if (!argv[i + 1]) fail('--dir needs a path');
      o.target = 'dir'; o.dir = argv[++i];
    } else if (a.startsWith('--dir=')) { o.target = 'dir'; o.dir = a.slice(6); }
    else if (a === '-f' || a === '--force') o.force = true;
    else if (a === '--uninstall') o.uninstall = true;
    else if (a === '--dry-run') o.dryRun = true;
    else if (a === '-h' || a === '--help') { process.stdout.write(HELP); process.exit(0); }
    else if (a === '-v' || a === '--version') { console.log(PKG.version); process.exit(0); }
    else fail(`unknown option ${a}\n\n${HELP}`);
  }
  return o;
}

function fail(msg) {
  console.error(`error: ${msg}`);
  process.exit(1);
}

function skillsRoot(o) {
  switch (o.target) {
    case 'project': return path.resolve('.claude', 'skills');
    case 'agents': return path.resolve('.agents', 'skills');
    case 'dir': return path.resolve(o.dir.replace(/^~(?=$|[\\/])/, os.homedir()));
    default: return path.join(os.homedir(), '.claude', 'skills');
  }
}

function copyDir(src, dst, files) {
  fs.mkdirSync(dst, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    if (SKIP.has(entry.name) || entry.name.endsWith('.pyc')) continue;
    const s = path.join(src, entry.name);
    const d = path.join(dst, entry.name);
    if (entry.isDirectory()) copyDir(s, d, files);
    else {
      fs.copyFileSync(s, d);
      if (entry.name.endsWith('.py')) fs.chmodSync(d, 0o755);
      files.push(d);
    }
  }
}

function installedVersion(dest) {
  try { return JSON.parse(fs.readFileSync(path.join(dest, MARKER), 'utf8')).version; } catch (e) { return null; }
}

function main() {
  const o = parse(process.argv.slice(2));
  if (!fs.existsSync(path.join(SRC, 'SKILL.md'))) fail(`skill files not found at ${SRC}`);
  const dest = path.join(skillsRoot(o), SKILL);
  const exists = fs.existsSync(dest);
  const tag = o.dryRun ? '[dry-run] ' : '';

  if (o.uninstall) {
    if (!exists) { console.log(`nothing to remove at ${dest}`); return; }
    if (!o.dryRun) fs.rmSync(dest, { recursive: true, force: true });
    console.log(`${tag}removed ${dest}`);
    return;
  }

  if (exists && !o.force) {
    const v = installedVersion(dest);
    if (v === PKG.version) { console.log(`${SKILL} ${v} is already installed at ${dest}`); return; }
    fail(`${dest} already exists${v ? ` (version ${v})` : ''}. Re-run with --force to replace it.`);
  }

  if (o.dryRun) {
    console.log(`${tag}would ${exists ? 'replace' : 'create'} ${dest}`);
    return;
  }
  if (exists) fs.rmSync(dest, { recursive: true, force: true });
  const files = [];
  copyDir(SRC, dest, files);
  fs.writeFileSync(path.join(dest, MARKER), JSON.stringify({ version: PKG.version, installedAt: new Date().toISOString() }, null, 2) + '\n');

  const py = process.platform === 'win32' ? 'python' : 'python3';
  console.log(`installed ${SKILL} ${PKG.version} (${files.length} files) to ${dest}

Next
  1. Check which renderers are available:
       ${py} "${path.join(dest, 'scripts', 'render_svg.py')}" --list-backends
     For exact layout checks, install Playwright + Chromium:
       pip install playwright && ${py} -m playwright install chromium
  2. Start a new agent session and ask for a figure, e.g.
       "Make Figure 1 for my NeurIPS paper from Section 3".`);
}

main();
