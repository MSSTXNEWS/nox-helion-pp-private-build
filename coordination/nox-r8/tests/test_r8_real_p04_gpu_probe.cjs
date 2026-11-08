'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict');
const cs=fs.readFileSync('coordination/nox-r8/overrides/src/MainWindow.xaml.cs','utf8');
const html=fs.readFileSync('coordination/nox-r8/overrides/src/index.html','utf8');
for(const token of ['case "qlora.gpu-probe": _ = RunLocalP04GpuProbeAsync(Text("requestId")); break;',
'private async Task RunLocalP04GpuProbeAsync(string requestId)',
'P04WorkerRoot()','EmbeddedP04WorkerAvailable()',
'P04_WORKER_CONTENT_DRIFT_HOLD','MessageBoxButton.YesNo',
'process.WaitForExitAsync(timeout.Token)','TimeSpan.FromSeconds(45)',
'process.Kill(entireProcessTree: true)','RedirectStandardOutput = true',
'UseShellExecute = false','Process.Start(psi)','preflight_local_gpu.py',
'NOX-P04-LOCAL-GPU-PREFLIGHT-v1','HARDWARE_READY_ONLY',
'modelMergeVerified = false','trainingStarted = false'])
assert(cs.includes(token),'NATIVE_PROBE_GUARD_MISSING '+token);
for(const token of ['id="qloraGpuProbe"','id="qloraGpuProbeState"',
"post('qlora.gpu-probe',{requestId})","case 'qlora.gpu-probe':"])
assert(html.includes(token),'UI_PROBE_GUARD_MISSING '+token);
assert((html.match(/<button class="core /g)||[]).length===8,'EIGHT_CORE_ID_CHANGED');
assert(cs.includes('case "chat": await Generate(Text("text"), Text("requestId")); break;'),'QWEN_CHAT_CHANGED');
assert(cs.includes('active.Cancel();'),'CHAT_STOP_CHANGED');
console.log('R8_NATIVE_QLORA_GPU_READONLY_PYTHON_PREFLIGHT_SOURCE_PASS');
