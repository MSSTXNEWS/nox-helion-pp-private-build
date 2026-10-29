'use strict';
// Independent manual #2 source-level security regression for the EXACT P03 UI.
// Do not merge without T06 owner admission. No product code is modified.
// node --test coordination/qa/manual2/test_p03_metadata_gate_r26.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const file = path.resolve(__dirname, '../../../Packages/P03/Source/P03.ModelCenter.Wow/ui.js');
const source = fs.readFileSync(file, 'utf8');
const preStart = source.indexOf('const numeric =');
const preEnd = source.indexOf('function el(');
const start = source.indexOf('const reviewedDigest =');
const end = source.indexOf('const currentJob =');
assert.ok(preStart >= 0 && preEnd > preStart && start > preEnd && end > start, 'P03 gate extraction must be reviewed after source refactor');
const gate = vm.runInNewContext(
  source.slice(preStart, preEnd) + '\n' + source.slice(start, end) +
  '\n({hasEvidence,reviewedTag,reviewedRevision,reviewedDigest,reviewedEvidenceUrl,officialFamilyUrl})',
  { URL }
);
const valid = Object.freeze({
  id: 'qwen3', officialUrl: 'https://ollama.com/library/qwen3',
  artifactVerified: true, exactTag: 'qwen3:0.6b',
  immutableRevision: 'a'.repeat(64), license: 'reviewed-license',
  licenseEvidenceUrl: 'https://example.org/review/license',
  artifactBytes: 1024, sha256: 'b'.repeat(64),
  manifestSha256: 'c'.repeat(64), requiredVramGiB: 4,
  compatibilityReviewed: true
});
const expectHold = (label, patch) => test(label, () =>
  assert.equal(gate.hasEvidence(Object.assign({}, valid, patch)), false));
test('positive 64-hex synthetic metadata shape (not real license attestation)', () =>
  assert.equal(gate.hasEvidence(valid), true));
expectHold('do not crash on non-string model id', { id: 42 });
expectHold('reject prototype/array model id', { id: ['qwen3'] });
expectHold('reject model family outside exact owner tag', { exactTag: 'llama3:8b' });
expectHold('reject mutable latest tag', { exactTag: 'qwen3:latest' });
expectHold('reject tag traversal', { exactTag: 'qwen3:../latest' });
expectHold('reject missing exact owner tag', { exactTag: null });
expectHold('reject legacy 40-hex commit as immutable model digest', { immutableRevision: 'a'.repeat(40) });
expectHold('reject zero model revision', { immutableRevision: '0'.repeat(64) });
expectHold('reject missing immutable revision', { immutableRevision: null });
expectHold('reject missing artifact SHA-256', { sha256: null });
expectHold('reject all-zero artifact SHA-256', { sha256: '0'.repeat(64) });
expectHold('reject all-zero manifest SHA-256', { manifestSha256: '0'.repeat(64) });
expectHold('reject insecure license evidence URL', { licenseEvidenceUrl: 'http://example.org/notice' });
expectHold('reject local license evidence URL', { licenseEvidenceUrl: 'https://localhost/secret' });
expectHold('reject credential-bearing license URL', { licenseEvidenceUrl: 'https://user:pass@example.org' });
expectHold('reject unofficial family URL', { officialUrl: 'https://malicious.example/library/qwen3' });
expectHold('reject wrong official family', { officialUrl: 'https://ollama.com/library/llama3' });
expectHold('reject non-default official port', { officialUrl: 'https://ollama.com:444/library/qwen3' });
expectHold('reject unverified artifact', { artifactVerified: false });
expectHold('reject empty license', { license: '   ' });
expectHold('reject missing compatibility review', { compatibilityReviewed: false });
expectHold('reject absent memory requirement', { requiredVramGiB: 0, recommendedRamGiB: 0 });
expectHold('reject zero artifact bytes', { artifactBytes: 0 });
test('new SHA gate intentionally rejects old positive fixture revision', () => {
  assert.equal(gate.reviewedRevision('a'.repeat(40)), false);
  assert.equal(gate.reviewedRevision('a'.repeat(64)), true);
});
