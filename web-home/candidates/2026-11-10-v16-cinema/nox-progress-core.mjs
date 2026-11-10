/* NOX evidence-based progress math. Percent means checkpointed student steps, never intelligence absorption. */
const hex64 = v => typeof v === 'string' && /^[a-f0-9]{64}$/i.test(v);
const whole = n => Number.isSafeInteger(n) && n >= 0;
export function assessNoxProgress(evidence) {
 const hold = reason => ({schema:'nox-progress-receipt-v1',status:'HOLD',reason,stepPercent:null,
  complete:false,weightUpdateVerified:false,windowsSyncVerified:false,qualityGainVerified:false});
 if(!evidence || evidence.schema!=='nox-distillation-evidence-v1') return hold('NO_VERIFIED_DISTILLATION_EVIDENCE');
 if(evidence.model!=='NOX' || evidence.operation!=='FULL_WEIGHT_DISTILLATION')return hold('NOT_NOX_FULL_WEIGHT_DISTILLATION');
 if(!whole(evidence.completedSteps) || !whole(evidence.targetSteps) || evidence.targetSteps<=0 || evidence.completedSteps>evidence.targetSteps)
  return hold('INVALID_STEP_COUNTERS');
 const weights=evidence.weights;
 if(!weights || !Array.isArray(weights.files)||!weights.files.length ||
    weights.files.some(f=>!hex64(f.sha256)||!whole(f.bytes)||f.bytes<=0||f.verified!==true) ||
    !hex64(weights.combinedSha256)||!hex64(evidence.baselineCombinedSha256) ||
    weights.combinedSha256===evidence.baselineCombinedSha256 ||
    weights.kind!=='FULL_STUDENT_WEIGHTS')
  return hold('STUDENT_WEIGHT_DELTA_NOT_VERIFIED');
 const quality=evidence.quality||{};
 const qualityGainVerified=quality.verified===true && Number.isFinite(quality.baseline) &&
  Number.isFinite(quality.student) && quality.student>quality.baseline &&
  hex64(quality.evalDatasetSha256);
 const windowsSyncVerified=!!evidence.windowsSync&&evidence.windowsSync.verified===true &&
  evidence.windowsSync.combinedSha256===weights.combinedSha256;
 const teacherCount=Array.isArray(evidence.teachers)?evidence.teachers.filter(t=>t&&
  typeof t.name==='string'&&hex64(t.sourceSha256)&&t.samplesVerified===true).length:0;
 const complete=evidence.completedSteps===evidence.targetSteps && qualityGainVerified &&
  windowsSyncVerified && teacherCount>=3;
 return {schema:'nox-progress-receipt-v1',status:complete?'VERIFIED_COMPLETE':'VERIFIED_CHECKPOINT_STEPS',
  reason:complete?'FINAL_GATES_PASSED':'FURTHER_GATES_REQUIRED',
  observedAt:evidence.observedAt||null,model:'NOX',operation:'FULL_WEIGHT_DISTILLATION',
  podId:evidence.podId||null,completedSteps:evidence.completedSteps,targetSteps:evidence.targetSteps,
  stepPercent:Number((100*evidence.completedSteps/evidence.targetSteps).toFixed(2)),
  studentWeightsSha256:weights.combinedSha256,weightFiles:weights.files.length,
  weightUpdateVerified:true,teacherEvidenceCount:teacherCount,
  qualityGainVerified,windowsSyncVerified,complete};
}
