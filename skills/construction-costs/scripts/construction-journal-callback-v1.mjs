#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import {
  Worker,
  isMainThread,
  parentPort,
  workerData,
} from "node:worker_threads";

const DIAGNOSTIC =
  "Restore the published construction callback and compatible host adapter. Inspect the protected proposal and live journal before another action; never replay an uncertain append.\n";
const MAX_OUTPUT_BYTES = 2048;
const MAX_PRIVATE_BYTES = 8192;
const ID = /^[A-Za-z0-9_-]{22}$/;
class ConstructionCallbackError extends Error {}
/** @returns {never} */
function refuse() {
  throw new ConstructionCallbackError(DIAGNOSTIC.trim());
}
/** @typedef {{status:'applied'|'rejected'|'stale'|'failed',text:string}} CallbackResult */
/** @param {unknown} value @returns {value is CallbackResult} */
function validResult(value) {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.keys(value).sort().join(",") !== "status,text"
  )
    return false;
  const row = /** @type {Record<string,unknown>} */ (value);
  return (
    typeof row.status === "string" &&
    ["applied", "rejected", "stale", "failed"].includes(row.status) &&
    typeof row.text === "string" &&
    Array.from(row.text).length <= 200 &&
    Array.from(row.text).every((character) => {
      const code = character.codePointAt(0);
      return (
        code !== undefined &&
        !(code >= 0xd800 && code <= 0xdfff) &&
        code !== 0xfffd
      );
    }) &&
    Buffer.byteLength(JSON.stringify(value) + "\n", "utf8") <= MAX_OUTPUT_BYTES
  );
}
/** @param {string} root */
function nativeModule(root) {
  if (!path.isAbsolute(root)) refuse();
  const actual = fs.realpathSync(root);
  if (!fs.statSync(actual).isDirectory()) refuse();
  const dist = fs.realpathSync(path.join(actual, "dist"));
  if (!dist.startsWith(actual + path.sep) || !fs.statSync(dist).isDirectory())
    refuse();
  const entry = path.join(dist, "construction-journal-callback-cli.js");
  if (!fs.lstatSync(entry).isFile()) refuse();
  const resolved = fs.realpathSync(entry);
  if (!resolved.startsWith(dist + path.sep)) refuse();
  return { root: actual, entry: resolved };
}
/** @param {{root:string,entry:string,id:string}} input @returns {Promise<CallbackResult>} */
function invokeHost(input) {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL(import.meta.url), {
      workerData: input,
      stdout: true,
      stderr: true,
      execArgv: [],
    });
    /** @type {CallbackResult|undefined} */
    let result;
    let invalid = false,
      privateBytes = 0;
    worker.on("message", (message) => {
      if (result !== undefined || !validResult(message)) {
        invalid = true;
        void worker.terminate();
        return;
      }
      result = message;
    });
    // Host logs are private, never callback stdout/stderr or result evidence.
    for (const stream of [worker.stdout, worker.stderr]) {
      stream.on("data", (data) => {
        privateBytes += Buffer.byteLength(data);
        if (privateBytes > MAX_PRIVATE_BYTES) {
          invalid = true;
          void worker.terminate();
        }
      });
      stream.on("error", () => {
        invalid = true;
        void worker.terminate();
      });
    }
    worker.once("error", () => {
      invalid = true;
    });
    worker.once("exit", (code) => {
      if (code !== 0 || invalid || result === undefined)
        reject(new ConstructionCallbackError(DIAGNOSTIC.trim()));
      else resolve(result);
    });
  });
}
/** @param {string[]} argv @param {NodeJS.ProcessEnv} env @returns {Promise<CallbackResult>} */
export async function runConstructionJournalAdapterV1(
  argv = process.argv.slice(2),
  env = process.env,
) {
  const [id] = argv,
    root = env.NANOCLAW_CALLBACK_HOST_ROOT,
    node = env.NANOCLAW_CALLBACK_NODE;
  if (
    argv.length !== 1 ||
    !ID.test(id ?? "") ||
    !root ||
    !node ||
    !path.isAbsolute(node) ||
    !/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(
      env.NANOCLAW_CALLBACK_MAIN_GROUP ?? "",
    ) ||
    !/^tg:-?[1-9]\d*$/.test(env.NANOCLAW_CALLBACK_MAIN_CHAT ?? "")
  )
    refuse();
  if (
    fs.realpathSync(node) !== fs.realpathSync(process.execPath) ||
    !fs.statSync(node).isFile()
  )
    refuse();
  const selected = nativeModule(root);
  // Config/env/data imports run only after the trusted cwd is selected.
  process.chdir(selected.root);
  return invokeHost({ ...selected, id });
}
async function runPrivateWorker() {
  const input = /** @type {{root?:unknown,entry?:unknown,id?:unknown}} */ (
    workerData
  );
  if (
    !parentPort ||
    !input ||
    typeof input !== "object" ||
    Object.keys(input).sort().join(",") !== "entry,id,root" ||
    typeof input.root !== "string" ||
    typeof input.entry !== "string" ||
    typeof input.id !== "string" ||
    !ID.test(input.id)
  )
    refuse();
  const selected = nativeModule(input.root);
  if (selected.root !== process.cwd() || selected.entry !== input.entry)
    refuse();
  const module = await import(pathToFileURL(selected.entry).href);
  if (typeof module.runConstructionJournalCallbackV1 !== "function") refuse();
  const result = await module.runConstructionJournalCallbackV1(input.id);
  if (!validResult(result)) refuse();
  parentPort.postMessage(result);
}
function directInvocation() {
  return Boolean(
    process.argv[1] &&
    fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url),
  );
}
if (!isMainThread) {
  try {
    if (directInvocation()) await runPrivateWorker();
    // outer-boundary-process-contract: the parent treats an absent worker
    // result/nonzero exit as failure and emits fixed redacted diagnostics.
    // Exit naturally so native host resources finish cleanup; an uncaught
    // worker exception can crash teardown before the parent receives failure.
  } catch {
    process.exitCode = 1;
  }
} else {
  try {
    if (directInvocation()) {
      const result = await runConstructionJournalAdapterV1();
      process.stdout.write(JSON.stringify(result) + "\n");
    }
    // outer-boundary-process-contract: the host treats nonzero/invalid stdout as
    // failure; emit empty stdout and fixed recovery text. Raw import/provider
    // exceptions would leak private data and break that protocol if propagated.
  } catch {
    process.stderr.write(DIAGNOSTIC);
    process.exitCode = 1;
  }
}
