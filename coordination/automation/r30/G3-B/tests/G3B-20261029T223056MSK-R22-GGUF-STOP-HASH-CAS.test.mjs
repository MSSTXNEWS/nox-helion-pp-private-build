// G3-B source-only STOP/hash receipt race guard. Run: node coordination/automation/r30/G3-B/tests/G3B-20261029T223056MSK-R22-GGUF-STOP-HASH-CAS.test.mjs
// Static C# contract test; does NOT substitute for .NET/Windows same-SHA QA.
import {readFileSync} from 'node:fs';
import {strict as assert} from 'node:assert';
const src=readFileSync(new URL('../../../../../Packages/P03/Source/P03.ModelCenter/ModelDownloadQueueWorker.cs', import.meta.url), 'utf8');
const scoped=src.slice(src.indexOf('var imported = await ollama.ImportGgufAsync'), src.indexOf('// Ollama may finish while a native STOP'));
assert.match(scoped, /linked\.Token\.ThrowIfCancellationRequested\(\)/);
assert.match(scoped, /j\.State == ModelJobState\.Running/);
assert.match(scoped, /j with \{ ComputedSha256 = imported\.Sha256 \}/);
assert.match(scoped, /: j, CancellationToken\.None/);
assert.match(scoped, /recorded\?\.State != ModelJobState\.Running/);
assert.doesNotMatch(scoped, /j => j with \{ ComputedSha256/);
assert.match(src, /public async Task<bool> CancelAsync/);
assert.match(src, /const string publicError = "P03_TRANSFER_FAILED"/);
assert.match(src, /var hasReviewedEvidence = reviewedLicense/);
console.log('G3-B STOP/hash source-contract static checks: 9/9 PASS; .NET native NOT_RUN');
