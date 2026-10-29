import test from "node:test";import assert from "node:assert/strict";import {readFileSync} from "node:fs";import {createHash} from "node:crypto";import {resolve,sep} from "node:path";import {fileURLToPath} from "node:url";
const root=resolve(fileURLToPath(new URL("../../",import.meta.url)));
const receipt=JSON.parse(readFileSync(new URL("./FILE_SHA256_RECEIPTS.json",import.meta.url),"utf8"));
test("original asset tree untouched; exact SHA-256 for every new production asset",()=>{
 assert.equal(receipt.schema,"NOX-WOW51-100-EXACT-SOURCE-RECEIPTS");
 assert.equal(receipt.basePr,30);
 assert.equal(receipt.paths.length,10);
 const seen=new Set();
 for(const x of receipt.paths){
   assert.ok(!seen.has(x.path));seen.add(x.path);
   assert.equal(x.preimage,"ABSENT");
   assert.ok(x.path.startsWith("proposals/NOX-WOW51-100/")||x.path===".github/workflows/nox-wow51-100.yml");
   const target=resolve(root,x.path);
   assert.ok(target.startsWith(root+sep));
   const raw=readFileSync(target,"utf8");
   // GitHub stores the canonical UTF-8 blob; Windows checkout may materialize CRLF. Compare the canonical LF content.
   const canonical=Buffer.from(raw.replace(/\r\n/g,"\n"),"utf8");
   assert.equal(createHash("sha256").update(canonical).digest("hex"),x.post_sha256,x.path);
   assert.equal(canonical.length,x.bytes_utf8,x.path);
 }
});
