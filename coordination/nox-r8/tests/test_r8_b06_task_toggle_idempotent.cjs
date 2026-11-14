// B06 owner target-state toggle dynamic source adapter (SOURCE_ONLY; not .NET Windows).
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const cs=fs.readFileSync(path.join(__dirname,'..','overrides','src','MainWindow.xaml.cs'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'..','overrides','src','index.html'),'utf8');
const native=cs.slice(cs.indexOf('private void HandleTaskToggle('),cs.indexOf('private void RefreshTasksBestEffort('));
assert.ok(native.includes('bool? desiredComplete')&&native.includes('UPDATE tasks SET complete=$complete'));
assert.ok(native.indexOf('commitAttempted = true;')<native.indexOf('tx.Commit();'));
assert.ok(native.includes('NOX_TASK_TOGGLE_COMMIT_UNKNOWN_HOLD'));
assert.ok(native.includes('NOX_TASK_TOGGLE_READBACK_UNKNOWN_HOLD'));
const dispatch=cs.slice(cs.indexOf('case "tasks.toggle":'),cs.indexOf('case "settings.get":'));
assert.ok(dispatch.includes('JsonValueKind.True')&&dispatch.includes('JsonValueKind.False'));
const render=html.slice(html.indexOf("case 'tasks':"),html.indexOf("case 'tasks.toggle.receipt':"));
assert.ok(render.includes('target:cb.checked')&&render.includes('complete:cb.checked'));
const receipt=html.slice(html.indexOf("case 'tasks.toggle.receipt':"),html.indexOf("case 'tasks.toggle.denied':"));
assert.ok(receipt.includes('v?.complete===pendingTaskToggle.target'));
assert.ok(html.includes("case 'tasks.toggle.uncertain':"));
console.log('B06 SOURCE_ONLY: ATLAS idempotent desired task state + unknown COMMIT receipt contract');
