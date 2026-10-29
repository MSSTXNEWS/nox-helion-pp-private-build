"use strict";
const assert = require("node:assert/strict");
// Exact reviewedTag from owner candidate Git blob f261956746e2d2f6b0c91246a9284b0d1dbb8fe6.
const reviewedTagOriginal = (s,id) => typeof s==='string' && s.length<=160 &&
  /^[a-z0-9][a-z0-9._-]*:[a-z0-9][a-z0-9._-]*$/i.test(s) &&
  s.toLowerCase().startsWith(id.toLowerCase()+':') &&
  !s.includes('..') && !s.toLowerCase().endsWith(':latest');
// Targeted candidate guard; no new dependencies or host methods.
const reviewedTagPatched = (s,id) => typeof id==='string' && typeof s==='string' && s.length<=160 &&
  /^[a-z0-9][a-z0-9._-]*:[a-z0-9][a-z0-9._-]*$/i.test(s) &&
  s.toLowerCase().startsWith(id.toLowerCase()+':') &&
  !s.includes('..') && !s.toLowerCase().endsWith(':latest');
for (const [tag,id] of [['qwen3:8b','qwen3'],['QWEN3:8B','qwen3'],['llama3.2:1b','llama3.2']])
  assert.equal(reviewedTagPatched(tag,id),true);
for (const [tag,id] of [['qwen3:8b','other'],['qwen3:latest','qwen3'],['qwen3:..','qwen3'],['other:tag','qwen3'],['../bad','qwen3']])
  assert.equal(reviewedTagPatched(tag,id),false);
for (const id of [null,undefined,42,{},[],true]) {
  assert.throws(()=>reviewedTagOriginal('qwen3:8b',id),TypeError);
  assert.equal(reviewedTagPatched('qwen3:8b',id),false);
}
console.log('PRE RED 6/6 TypeError; POST GREEN 14/14 focused assertions');
