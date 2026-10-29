'use strict';
// G3-B R30: source-only static boundary and deterministic transition-model regression.
// Run with: node tests/P03/g3b_r30_queue_cancel_source_contract_20261029.cjs
// This does NOT run native C#/.NET, Ollama HTTP downloads, or a Windows build.
const fs=require('node:fs'), path=require('node:path');
function verifyQueueCancelSourceContract(s) {
  const checks=[
    ["queued_unpinned_race_guard",s.includes('j => j.State == ModelJobState.Queued\n                    ? j with { State = ModelJobState.Failed')],
    ["unpinned_cancelled_is_noop",s.includes('Error = "UNPINNED_ARTIFACT" }\n                    : j, ct);')],
    ["generic_error_rechecks_durable_stop",s.includes('if (j.State == ModelJobState.Cancelling)\n                    {\n                        stoppedBeforeFailure = true;')],
    ["generic_error_transitions_cancelled",s.includes('return j with { State = ModelJobState.Cancelled,\n                            Status = "Cancelled; Ollama may resume this pull later" };')],
    ["ordinary_failure_only_running",s.includes('return j.State == ModelJobState.Running\n                        ? j with { State = ModelJobState.Failed')],
    ["cancelled_event_only_durable_stop",s.includes('if (stoppedBeforeFailure && outcome?.State == ModelJobState.Cancelled)')],
    ["failed_event_only_failed",s.includes('else if (outcome?.State == ModelJobState.Failed)')],
    ["preserve_stop_progress_donor",s.includes('persisted?.State != ModelJobState.Running || linked.IsCancellationRequested')],
    ["preserve_http_cancel_donor",s.includes('catch (Exception ex) when (linked.IsCancellationRequested)')],
    ["preserve_cts_retirement",s.includes('catch (ObjectDisposedException) { }')&&s.includes('catch (AggregateException ex)')],
    ["preserve_queue_retry",s.includes('RetryAsync(Guid id, CancellationToken ct = default) => store.RetryAsync(id, ct)')],
    ["preserve_lease",s.includes('store.TryAcquireExecutionLease(job.Id)')],
    ["preserve_local_pull",s.includes('await ollama.PullAsync(current, OnProgress, linked.Token)')],
    ["preserve_import",s.includes('await ollama.ImportGgufAsync(current, OnProgress, linked.Token)')],
    ["preserve_terminal_receipt",s.includes('ReceiptPath = ollama.ReceiptPathFor(j.Id)')]
  ];
  for(const [name,passed] of checks) if(!passed) throw new Error("SOURCE_CONTRACT_RED "+name);
  // Deterministic transition-model regressions, NOT a native C# execution.
  const errorState = state => state==="Cancelling"?"Cancelled":state==="Running"?"Failed":state;
  const unpinnedState = state => state==="Queued"?"Failed":state;
  const examples=[["Cancelling","Cancelled"],["Running","Failed"],["Completed","Completed"],["Cancelled","Cancelled"],["Queued","Queued"]];
  for(const [initial,expected] of examples)
    if(errorState(initial)!==expected) throw new Error("TRANSITION_MODEL_RED "+initial);
  if(unpinnedState("Cancelled")!=="Cancelled" || unpinnedState("Queued")!=="Failed")
    throw new Error("UNPINNED_TRANSITION_MODEL_RED");
  return {sourceChecks:checks.length,modelCases:examples.length+2};
}
const worker=fs.readFileSync(path.join(__dirname,'../../Packages/P03/Source/P03.ModelCenter/ModelDownloadQueueWorker.cs'),'utf8');
const result=verifyQueueCancelSourceContract(worker);
console.log('G3B_R30_QUEUE_CANCEL_SOURCE_CONTRACT_PASS',JSON.stringify(result));
