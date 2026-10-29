/* NOX V16 · MANUAL #2 · R33 finite evidence gate.
   Source-only coordination logic. Does not sign T08/T10 or authorize GitLab. */
const SHA = /^[0-9a-f]{40}$/;
const CRITERIA = Object.freeze(["base","P01","P02","P03","P04","P05","common_integration","accepted_head_manifest"]);
const isSha = v => typeof v === "string" && SHA.test(v);
const unique = a => new Set(a).size === a.length;
function sourceDigest(rows) {
  if (!Array.isArray(rows) || rows.some(x => !x || typeof x.path !== "string" || !x.path || !isSha(x.blob)) ||
      !unique(rows.map(x => x.path))) return null;
  return rows.map(x => x.path + ":" + x.blob).sort().join("|");
}
export function evaluateFiniteSource(snapshot, previous = null) {
  const errors = [];
  if (!snapshot || !isSha(snapshot.head) || !isSha(snapshot.tree)) {
    return Object.freeze({phase:"HOLD_INVALID_HEAD",ready:false,completed:0,total:8,productPercent:null,errors:["EXACT_HEAD_TREE_MISSING"]});
  }
  const digest = sourceDigest(snapshot.sources);
  if (digest === null) errors.push("SOURCE_BLOB_LIST_MISSING_OR_INVALID");
  const upstream = Array.isArray(snapshot.criteria) ? snapshot.criteria : [];
  const complete = CRITERIA.filter(id => upstream.some(v => v?.id === id &&
    v.head === snapshot.head && isSha(v.sourceBlob) && isSha(v.receiptBlob) &&
    isSha(v.testReceiptBlob) && v.readback === true && v.status === "SOURCE_VERIFIED"));
  if (upstream.length !== 8 || !unique(upstream.map(x=>x?.id)) ||
      upstream.some(x=>!CRITERIA.includes(x?.id))) errors.push("T06_CRITERIA_INCOMPLETE_OR_DUPLICATED");
  if (complete.length !== 8) errors.push("T06_8_OF_8_NOT_PROVED");
  const source = snapshot.host50 || {};
  if (source.total !== 50 || !Number.isInteger(source.bound) || source.bound < 0 ||
      source.bound > 50 || !Number.isInteger(source.nativePending) ||
      source.nativePending < 0 || source.nativePending > 50) {
    errors.push("HOST50_COUNTERS_UNVERIFIED");
  } else {
    if (source.bound !== 50) errors.push("HOST50_SOURCE_UNBOUND_" + (50-source.bound));
    if (source.nativePending !== 0) errors.push("HOST50_NATIVE_PENDING_" + source.nativePending);
  }
  const archive = snapshot.archive || {};
  if (archive.parts !== 3 || archive.files !== 729 || archive.verified !== true ||
      !/^[a-f0-9]{64}$/.test(archive.sha256 || "")) errors.push("SOURCELOCK_729_UNVERIFIED");
  const reviewer = snapshot.t08 || {};
  if (reviewer.head !== snapshot.head || !isSha(reviewer.receiptBlob) ||
      reviewer.independent !== true || reviewer.accepted !== true || reviewer.readback !== true)
    errors.push("INDEPENDENT_T08_SAME_HEAD_NOT_ACCEPTED");
  const pin = snapshot.t09 || {};
  if (pin.head !== snapshot.head || pin.tree !== snapshot.tree || pin.frozen !== true ||
      !isSha(pin.receiptBlob)) errors.push("T09_FROZEN_SHA_NOT_PROVED");
  const t10 = snapshot.t10 || {};
  if (t10.head !== snapshot.head || t10.accepted !== true || !isSha(t10.receiptBlob) ||
      t10.readback !== true) errors.push("T10_SOURCE_READY_NOT_PROVED");
  if (snapshot.gitlabBuild === true && errors.length)
    errors.push("PREMATURE_GITLAB_BUILD_ATTEMPT");
  const previousDigest = previous && isSha(previous.head) ? sourceDigest(previous.sources) : null;
  const unchanged = previousDigest !== null && digest !== null && digest === previousDigest &&
    (previous.ownerEvidenceBlob || null) === (snapshot.ownerEvidenceBlob || null);
  if (unchanged && errors.length) return Object.freeze({
    phase:"WAITING_OWNER_SOURCE_CHANGE",ready:false,completed:complete.length,total:8,
    productPercent:null,sourceCoverage:source.total===50?source.bound/50:null,
    errors:[...new Set(errors)],meaningfulChange:false,runAnotherQaCycle:false
  });
  return Object.freeze({
    phase:errors.length?"SOURCE_GATES_INCOMPLETE":"READY_FOR_EXTERNAL_SIGNED_ACCEPTANCE",
    ready:false, /* Never sign SOURCE_READY in a local JS evaluator. */
    completed:complete.length,total:8,productPercent:null,
    sourceCoverage:source.total===50?source.bound/50:null,
    errors:[...new Set(errors)],meaningfulChange:!unchanged,runAnotherQaCycle:!unchanged
  });
}
