// G3-B R23 P03 SOURCE-ONLY reviewed-artifact and durable STOP guard.
// Run in the G3-B donor checkout: node coordination/automation/r30/G3-B/tests/G3B-20261029T232527MSK-R23-REVIEW-STOP-PR162-GATE.test.mjs
// Static contract assertions, NOT native C# or independent T08 QA.
import {readFileSync} from 'node:fs';
import {strict as assert} from 'node:assert';
const src = readFileSync(new URL('../../../../../Packages/P03/Source/P03.ModelCenter/ModelDownloadQueueWorker.cs', import.meta.url), 'utf8');
const begin = src.indexOf('var imported = await ollama.ImportGgufAsync');
const end = src.indexOf('// Ollama may finish while a native STOP', begin);
assert.ok(begin > 0 && end > begin, 'GGUF import code exists');
const gguf = src.slice(begin, end);
const checks = {
  license_https_review: /var reviewedLicense = job\.LicenseAcknowledged/.test(src) && /licenseEvidence\.Scheme == Uri\.UriSchemeHttps/.test(src),
  revision_sha_pin: /var pinnedRevision/.test(src) && /revision\.All\(Uri\.IsHexDigit\)/.test(src),
  gguf_size_hash_pin: /job\.ExpectedLocalBytes is > 4/.test(src) && /job\.ExpectedLocalSha256\.All\(Uri\.IsHexDigit\)/.test(src),
  gguf_rights_receipt: /string\.IsNullOrWhiteSpace\(job\.RightsReceiptId\)/.test(src),
  fail_closed_before_lease: src.indexOf('if (!hasReviewedEvidence)') > 0 && src.indexOf('if (!hasReviewedEvidence)') < src.indexOf('store.TryAcquireExecutionLease'),
  stop_after_import: /linked\.Token\.ThrowIfCancellationRequested\(\)/.test(gguf),
  state_bounded_hash_write: /j\.State == ModelJobState\.Running/.test(gguf) && /ComputedSha256 = imported\.Sha256/.test(gguf),
  refuse_hash_after_terminal: /recorded\?\.State != ModelJobState\.Running/.test(gguf),
  durable_stop_wins: /j\.State == ModelJobState\.Cancelling/.test(src) && /stoppedBeforeFailure/.test(src),
  privacy_safe_errors: /const string publicError = "P03_TRANSFER_FAILED"/.test(src) && /PublicProgressDigest/.test(src)
};
for (const [name, ok] of Object.entries(checks)) assert.ok(ok, 'P03 gate missing: ' + name);
console.log('G3-B R23 P03 reviewed+STOP+privacy SOURCE STATIC: 10/10 PASS; native .NET/Windows NOT_RUN');
