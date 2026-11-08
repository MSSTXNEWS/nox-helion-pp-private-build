'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict');
const cs=fs.readFileSync('coordination/nox-r8/overrides/src/MainWindow.xaml.cs','utf8');
const html=fs.readFileSync('coordination/nox-r8/overrides/src/index.html','utf8');
for (const word of [
  'case "qlora.snapshot-probe": _ = RunLocalP04ModelSnapshotProbeAsync(Text("revision"), Text("requestId")); break;',
  'private async Task RunLocalP04ModelSnapshotProbeAsync(string revision, string requestId)',
  'new Microsoft.Win32.OpenFolderDialog',
  'MessageBoxButton.YesNo',
  '"NOX.HELION.P04.model_snapshot_probe.py"',
  'P04_SNAPSHOT_SCRIPT_CHANGED_HOLD',
  'SHA256.HashData(File.ReadAllBytes(script))',
  'P04WorkerRoot()',
  '"--expected-revision", revision.ToLowerInvariant()',
  'psi.ArgumentList.Add(argument)',
  'process.WaitForExitAsync(budget.Token)',
  'process.Kill(entireProcessTree: true)',
  'NOX-P04-MODEL-SNAPSHOT-PROBE-v1',
  'LOCAL_FILES_PRESENT_ONLY',
  'trainingStarted = false',
  'licenseVerified = false',
  'modelMergeVerified = false'
])assert(cs.includes(word),'P04_MODEL_PROBE_SOURCE_MISSING '+word);
for (const word of [
  'id="qloraModelRevision"','id="qloraSnapshotProbe"','id="qloraSnapshotState"',
  "post('qlora.snapshot-probe',{revision,requestId})",
  "case 'qlora.snapshot-probe':",
  'лицензия/обучение/merge НЕ подтверждены'
])assert(html.includes(word),'P04_MODEL_PROBE_UI_MISSING '+word);
assert((html.match(/<button class="core /g)||[]).length===8,'ORIGINAL_CORE_COUNT_CHANGED');
assert(cs.includes('case "chat": await Generate(Text("text"), Text("requestId")); break;'),'CHAT_CHANGED');
assert(cs.includes('active.Cancel();'),'STOP_CHANGED');
console.log('NOX_R8_REAL_HF_MODEL_SNAPSHOT_READONLY_SOURCE_PASS');
