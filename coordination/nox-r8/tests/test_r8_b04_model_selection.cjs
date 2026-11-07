'use strict';
// SOURCE_ONLY regression. Does not claim owner-PC or Ollama/SQLite physical PASS.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.resolve(__dirname,'../overrides/src/MainWindow.xaml.cs'),'utf8');
const start = source.indexOf('    private async Task SelectModel(string model, string requestId)');
const end = source.indexOf('    private async Task PullExistingProviderModel(',start);
assert.ok(start >= 0 && end > start,'original native model picker exists');
const s = source.slice(start,end);
assert.equal((s.match(/if \(active != null\)/g)||[]).length,2,'reject before and after async probe');
assert.match(s,/http\.GetAsync\(Api \+ "\/api\/tags", probe\.Token\)/,'exact local Ollama tag list');
assert.match(s,/TimeSpan\.FromSeconds\(4\)/,'bounded provider health request');
assert.match(s,/if \(!exists\)[\s\S]*NOX_MODEL_TAG_NOT_REGISTERED_HOLD/,'unregistered tag rejected');
assert.match(s,/db\.BeginTransaction\(\)[\s\S]*tx\.Commit\(\)/,'atomic preference write');
assert.match(s,/VALUES\('model',\$m\)/,'only model key mutated');
assert.match(s,/using \(var verifyDb = OpenDatabase\(\)\)[\s\S]*NOX_MODEL_SELECT_SQLITE_READBACK_HOLD/,'independent post-commit readback');
assert.ok(s.indexOf('Send("model.select.receipt"') > s.indexOf('NOX_MODEL_SELECT_SQLITE_READBACK_HOLD'),'never acknowledge before durable readback');
assert.match(source,/case "stop":[\s\S]*active\.Cancel\(\)/,'native STOP preserved');
console.log('B04_MODEL_SELECTION_SOURCE_ONLY_PASS');


// B04 SOURCE_ONLY: verified installed-tag receipt, owner STOP vs provider ERROR.
const pullStart = source.indexOf('    private async Task PullExistingProviderModel(string modelName, string requestId)');
const pullEnd = source.indexOf('    private const string VuneoImportReceipt',pullStart);
assert.ok(pullStart>=0 && pullEnd>pullStart,'original native model pull owner method exists');
const pull = source.slice(pullStart,pullEnd);
assert.ok(pull.indexOf('NOX_MODEL_PULL_TAG_READBACK_HOLD')>pull.indexOf('transferClient.GetAsync(Api + "/api/tags", verify.Token)'),'DONE needs exact provider tag');
assert.ok(pull.indexOf('Send("download", new { requestId, status = "DONE"')>pull.indexOf('NOX_MODEL_PULL_TAG_READBACK_HOLD'),'DONE after provider tag check');
assert.match(pull,/string.Equals\(x.GetProperty\("name"\).GetString\(\), modelName, StringComparison.Ordinal\)/);
assert.match(pull,/ValidWriteRequestId\(requestId\)/,'native validates the pull owner');
assert.match(pull,/MessageBox.Show\(this,/,'native explicit owner confirmation required');
assert.match(pull,/if \(permission != MessageBoxResult.Yes\)/,'refusal is non-destructive');
assert.match(pull,/cts.Token.ThrowIfCancellationRequested\(\);[\s\S]*Send\("download", new \{ requestId, status = "DONE"/);
assert.match(pull,/catch \(OperationCanceledException\) when \(cts.IsCancellationRequested\)/,'only owner STOP reports STOPPED');
assert.match(pull,/catch \(Exception\) \{[\s\S]*status = "ERROR"/,'non-STOP failures report error');
assert.match(pull,/if \(activeModelPull != null\)/,'one model transfer at a time');
assert.match(pull,/finally \{\s*if \(ReferenceEquals\(activeModelPull, cts\)\) \{\s*activeModelPull = null;[\s\S]*activeModelPullName = null;/,'clear only current owner lease');
assert.match(source,/case "model.cancel": \{[\s\S]*activeModelPullRequestId, pullId[\s\S]*activeModelPullName, pullModel[\s\S]*activeModelPull.Cancel\(\);/,'foreign pull STOP cannot cancel current owner');
console.log('B04_MODEL_PULL_VERIFIED_OWNER_RECEIPT_SOURCE_ONLY_PASS');

const html = fs.readFileSync(path.resolve(__dirname,'../overrides/src/index.html'),'utf8');
assert.match(source,/case "model.select": await SelectModel\(Text\("model"\), Text\("requestId"\)\)/);
assert.match(s,/if \(!ValidWriteRequestId\(requestId\)\)/,'reject missing owner request ID');
assert.match(s,/Send\("model.select.denied", new \{ requestId, reason = "NOX_MODEL_REQUEST_ID_HOLD" \}\)/);
assert.match(s,/Send\("model.select.receipt", new \{ requestId, model, saved = true \}\)/);
assert.ok(s.indexOf('NOX_MODEL_SELECT_SQLITE_READBACK_HOLD') < s.indexOf('Send("model.select.receipt"'),'ACK follows independent readback');
assert.match(s,/catch \(Exception ex\)[\s\S]*Send\("model.select.denied", new \{ requestId, reason \}\)/);
assert.match(html, /pendingModel=\{requestId,model,previous:committedModel\}/);
assert.match(html, /post\('model.select',\{model,requestId\}\)===false/);
assert.match(html, /case 'model.select.receipt':if\(pendingModel&&v\?\.requestId===pendingModel.requestId&&v.model===pendingModel.model&&v.saved===true\)/);
assert.match(html, /case 'model.select.denied':if\(pendingModel&&v\?\.requestId===pendingModel.requestId\)/);
assert.match(html, /if\(previous\)\$\('modelPicker'\)\.value=previous/);
console.log('B04_MODEL_OWNER_RECEIPT_SOURCE_ONLY_PASS');
