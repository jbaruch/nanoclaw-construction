import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import { test } from "node:test";
const WRAPPER = fileURLToPath(
  new URL(
    "../skills/construction-costs/scripts/construction-journal-callback-v1.mjs",
    import.meta.url,
  ),
);
const ID = "A".repeat(22);
const RESULT = { status: "applied", text: "Synthetic confirmed callback" };
function fixture(
  t,
  source = `export async function runConstructionJournalCallbackV1(id){return ${JSON.stringify(RESULT)}}`,
) {
  const root = fs.realpathSync(
    fs.mkdtempSync(path.join(os.tmpdir(), "construction-wrapper-")),
  );
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const host = path.join(root, "host");
  fs.mkdirSync(path.join(host, "dist"), { recursive: true });
  fs.writeFileSync(path.join(host, "package.json"), '{"type":"module"}');
  const entry = path.join(host, "dist/construction-journal-callback-cli.js");
  fs.writeFileSync(entry, source);
  const env = {
    PATH: process.env.PATH,
    NANOCLAW_CALLBACK_HOST_ROOT: host,
    NANOCLAW_CALLBACK_NODE: process.execPath,
    NANOCLAW_CALLBACK_MAIN_GROUP: "main",
    NANOCLAW_CALLBACK_MAIN_CHAT: "tg:100",
  };
  function run(args = [ID], change = {}, command = WRAPPER) {
    return spawnSync(process.execPath, [command, ...args], {
      env: { ...env, ...change },
      cwd: root,
      encoding: "utf8",
      timeout: 10000,
      maxBuffer: 65536,
    });
  }
  return { root, host, entry, env, run };
}
function rejected(result) {
  assert.equal(result.signal, null);
  assert.equal(result.status, 1);
  assert.equal(result.stdout, "");
  assert.match(result.stderr, /Restore the published construction callback/);
  assert.ok(Buffer.byteLength(result.stderr) < 512);
}
test("uses a real isolated worker and selects trusted cwd before imports, invokes once with only opaque ID", (t) => {
  const f = fixture(
    t,
    `import fs from 'node:fs';import {isMainThread} from 'node:worker_threads';const cwdAtImport=process.cwd();export async function runConstructionJournalCallbackV1(id){if(isMainThread||id!==${JSON.stringify(ID)}||cwdAtImport!==process.env.NANOCLAW_CALLBACK_HOST_ROOT)throw new Error('Synthetic boundary failed');fs.appendFileSync('once.txt',id+'\\n');return ${JSON.stringify(RESULT)}}`,
  );
  const result = f.run();
  assert.equal(result.status, 0);
  assert.equal(result.stdout, JSON.stringify(RESULT) + "\n");
  assert.equal(result.stderr, "");
  assert.equal(
    fs.readFileSync(path.join(f.host, "once.txt"), "utf8"),
    ID + "\n",
  );
});
for (const args of [
  [],
  [ID, "extra"],
  ["../not-an-id"],
  ["A".repeat(21)],
  ["A".repeat(23)],
  ["A".repeat(21) + " "],
])
  test(`rejects invalid argv ${JSON.stringify(args)} before import`, (t) => {
    const f = fixture(
      t,
      `import fs from 'node:fs';fs.writeFileSync('imported.txt','bad');export async function runConstructionJournalCallbackV1(){return ${JSON.stringify(RESULT)}}`,
    );
    rejected(f.run(args));
    assert.equal(fs.existsSync(path.join(f.host, "imported.txt")), false);
  });
for (const change of [
  { NANOCLAW_CALLBACK_HOST_ROOT: "" },
  { NANOCLAW_CALLBACK_HOST_ROOT: "relative" },
  { NANOCLAW_CALLBACK_NODE: "" },
  { NANOCLAW_CALLBACK_NODE: "/not-node" },
  { NANOCLAW_CALLBACK_MAIN_GROUP: "../main" },
  { NANOCLAW_CALLBACK_MAIN_CHAT: "tg:0" },
])
  test(`rejects invalid fixed host environment ${Object.keys(change)[0]}`, (t) => {
    const f = fixture(t);
    rejected(f.run([ID], change));
  });
for (const kind of [
  "missing-module",
  "module-directory",
  "module-symlink",
  "dist-escape",
  "missing-export",
])
  test(`rejects ${kind} fixed host lookup`, (t) => {
    const f = fixture(t);
    if (kind === "missing-module") fs.unlinkSync(f.entry);
    if (kind === "module-directory") {
      fs.unlinkSync(f.entry);
      fs.mkdirSync(f.entry);
    }
    if (kind === "module-symlink") {
      const outside = path.join(f.root, "outside.mjs");
      fs.renameSync(f.entry, outside);
      fs.symlinkSync(outside, f.entry);
    }
    if (kind === "dist-escape") {
      const outside = path.join(f.root, "outside-dist");
      fs.renameSync(path.join(f.host, "dist"), outside);
      fs.symlinkSync(outside, path.join(f.host, "dist"));
    }
    if (kind === "missing-export")
      fs.writeFileSync(f.entry, "export const incompatible=true;");
    rejected(f.run());
  });
for (const value of [
  null,
  { status: "approved", text: "Synthetic" },
  { status: "applied", text: "Synthetic", approved: true },
  { status: "applied", text: "x".repeat(201) },
  { status: "applied", text: "\ud800" },
  { status: "applied", text: "\ufffd" },
  "Synthetic",
])
  test(`rejects unsupported result ${JSON.stringify(value).slice(0, 80)}`, (t) => {
    const f = fixture(
      t,
      `export async function runConstructionJournalCallbackV1(){return ${JSON.stringify(value)}}`,
    );
    rejected(f.run());
  });
for (const status of ["applied", "rejected", "stale", "failed"])
  test(`preserves handled native ${status} result`, (t) => {
    const result = { status, text: "👷".repeat(200) },
      f = fixture(
        t,
        `export async function runConstructionJournalCallbackV1(){return ${JSON.stringify(result)}}`,
      ),
      run = f.run();
    assert.equal(run.status, 0);
    assert.deepEqual(JSON.parse(run.stdout), result);
    assert.ok(Buffer.byteLength(run.stdout) <= 2048);
    assert.equal(run.stderr, "");
  });
test("keeps host module stdout/stderr private while returning only the strict result", (t) => {
  const f = fixture(
      t,
      `console.log('PRIVATE_SYNTHETIC_SOURCE');console.error('PRIVATE_SYNTHETIC_PROVIDER');export async function runConstructionJournalCallbackV1(){console.log('PRIVATE_SYNTHETIC_BODY');return ${JSON.stringify(RESULT)}}`,
    ),
    result = f.run();
  assert.equal(result.status, 0);
  assert.equal(result.stdout, JSON.stringify(RESULT) + "\n");
  assert.equal(result.stderr, "");
});
test("refuses excessive private host output without forwarding bytes or claiming success", (t) => {
  const f = fixture(
    t,
    `console.error('PRIVATE_SYNTHETIC_'+ 'x'.repeat(9000));export async function runConstructionJournalCallbackV1(){return ${JSON.stringify(RESULT)}}`,
  );
  const result = f.run();
  rejected(result);
  assert.doesNotMatch(result.stderr, /PRIVATE_SYNTHETIC/);
});
for (const kind of ["import", "call", "primitive"])
  test(`redacts ${kind} host failure`, (t) => {
    const body =
      kind === "import"
        ? `throw new Error('PRIVATE_SYNTHETIC_IMPORT');`
        : kind === "call"
          ? `export async function runConstructionJournalCallbackV1(){throw new Error('PRIVATE_SYNTHETIC_PROVIDER')}`
          : `export async function runConstructionJournalCallbackV1(){throw 'PRIVATE_SYNTHETIC_PRIMITIVE'}`;
    const f = fixture(t, body),
      result = f.run();
    rejected(result);
    assert.doesNotMatch(result.stderr, /PRIVATE_SYNTHETIC/);
  });
test("ordinary imports remain inert and a native skill-entrypoint symlink still resolves direct invocation", async (t) => {
  const f = fixture(t),
    link = path.join(f.root, "installed-entrypoint.mjs");
  fs.symlinkSync(WRAPPER, link);
  assert.equal(f.run([ID], {}, link).status, 0);
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "-e",
      `await import(${JSON.stringify(pathToFileURL(WRAPPER).href)});`,
    ],
    { encoding: "utf8", env: { PATH: process.env.PATH }, timeout: 10000 },
  );
  assert.equal(result.status, 0);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr, "");
});

test("ordinary imports inside another worker remain inert", () => {
  const source = `import {Worker} from 'node:worker_threads';const worker=new Worker(new URL('data:text/javascript,'+encodeURIComponent(${JSON.stringify("await import(" + JSON.stringify(pathToFileURL(WRAPPER).href) + ");")})));worker.once('error',()=>{process.exitCode=1});await new Promise(resolve=>worker.once('exit',resolve));`;
  const result = spawnSync(
    process.execPath,
    ["--input-type=module", "-e", source],
    { encoding: "utf8", env: { PATH: process.env.PATH }, timeout: 10000 },
  );
  assert.equal(result.status, 0);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr, "");
});

test("host exceptions take the private worker boundary without uncaught-exception teardown", (t) => {
  const f = fixture(
    t,
    `import fs from 'node:fs';process.once('uncaughtException',()=>fs.writeFileSync('uncaught.txt','bad'));export async function runConstructionJournalCallbackV1(){throw new Error('PRIVATE_SYNTHETIC_NATIVE_FAILURE')}`,
  );
  const result = f.run();
  rejected(result);
  assert.equal(fs.existsSync(path.join(f.host, "uncaught.txt")), false);
  assert.doesNotMatch(result.stderr, /PRIVATE_SYNTHETIC_NATIVE_FAILURE/);
});
