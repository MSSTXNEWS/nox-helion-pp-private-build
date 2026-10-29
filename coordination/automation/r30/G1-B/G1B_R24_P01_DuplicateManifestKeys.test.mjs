// NOX V16 G1-B / ERR-SRC-004: SOURCE-ONLY diagnostic, NOT native PowerShell QA.
// Run: node G1B_R24_P01_DuplicateManifestKeys.test.mjs Verify-Payload.ps1 Remove-InstalledPayload.ps1
// Intentionally reports RED while raw manifest duplicate members are not rejected BEFORE ConvertFrom-Json.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const files = process.argv.slice(2);
assert.equal(files.length, 2, 'Provide the two exact P01 PowerShell files');
const cases = [
  '{"schema":"UNTRUSTED","schema":"NOX_P01_PAYLOAD_SHA256_V1"}',
  '{"files":[],"files":[{"path":"NOX.P01.Shell.exe"}]}'
];
assert.equal(JSON.parse(cases[0]).schema, 'NOX_P01_PAYLOAD_SHA256_V1');
assert.equal(JSON.parse(cases[1]).files.length, 1);
for (const file of files) {
  const source=readFileSync(file,'utf8');
  assert.match(source, /\\bConvertFrom-Json\\b/, file+' must be manifest JSON parser');
  // Conservative source-triage heuristic, NOT a substitute for the native negative fixture.
  const guard=/\\b(?:Assert|Reject|Validate|Ensure|Test)[\\w-]{0,70}(?:Duplicate|Unique)(?:Json|Key|Member)[\\w-]*\\b/i.test(source);
  assert.ok(guard, 'P01_DUPLICATE_MANIFEST_MEMBER_REJECTION_MISSING: '+file);
}
console.log('P01_DUPLICATE_JSON_GUARD_SOURCE_STATIC_PASS; native Windows PowerShell 5.1 fixture still REQUIRED');
