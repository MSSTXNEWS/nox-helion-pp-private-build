import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";
import {fileURLToPath} from "node:url";
import {resolve,sep} from "node:path";
const repositoryRoot=resolve(fileURLToPath(new URL("../../",import.meta.url)));
const manifest=JSON.parse(readFileSync(new URL("./SOURCE_RECEIPTS.json",import.meta.url),"utf8"));
test("exact source file SHA-256 receipts, no lost or substituted paths",()=>{
 assert.equal(manifest.schema,"NOX-V16-SOURCE-RECEIPT-V1");
 assert.equal(manifest.runId,"NOX-V16-PACK02-50-20261028");
 assert.equal(manifest.paths.length,11);
 const ids=new Set();
 for(const item of manifest.paths){
  assert.ok(!ids.has(item.path));ids.add(item.path);
  assert.ok(/^(?:proposals\/NOX-PACK02-50\/|\.github\/workflows\/nox-pack02-)/.test(item.path));
  assert.ok(!item.path.includes(".."));
  assert.equal(item.preimage,"ABSENT");
  const p=resolve(repositoryRoot,item.path);
  assert.ok(p.startsWith(repositoryRoot+sep),"path boundary");
  const bytes=readFileSync(p);
  const sha=createHash("sha256").update(bytes).digest("hex");
  assert.equal(sha,item.post_sha256,"SHA-256 mismatch: "+item.path);
  assert.equal(item.bytes_utf8,bytes.length);
 }
 const required=["ops.mjs","catalog.mjs","catalog.json","panel.mjs","panel.css","smoke.test.mjs","golden.test.mjs","receipt.test.mjs","README.md","acceptance-ledger.csv"];
 for(const name of required)assert.ok(ids.has("proposals/NOX-PACK02-50/"+name));
 assert.ok(ids.has(".github/workflows/nox-pack02-fifty-checks.yml"));
});
