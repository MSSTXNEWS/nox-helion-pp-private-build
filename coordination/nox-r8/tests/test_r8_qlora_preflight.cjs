'use strict';
const fs=require('fs'),assert=require('node:assert/strict');
const cs=fs.readFileSync('coordination/nox-r8/overrides/src/MainWindow.xaml.cs','utf8');
const html=fs.readFileSync('coordination/nox-r8/overrides/src/index.html','utf8');
for(const token of ['case "qlora.preflight": _ = SendP04QloraPreflightAsync(); break;',
'private async Task SendP04QloraPreflightAsync()','P04_QLORA_PREFLIGHT_READONLY',
'train_qlora.py','preflight_local_gpu.py','merge_qlora_adapter.py',
'ReadNvidiaAsync("NOX_R8_QLORA_PREFLIGHT_READONLY")',
'ready = false, trainingStarted = false','checkpointVerified = false, modelMergeVerified = false'])
 assert(cs.includes(token),'P04_PREFLIGHT_NATIVE_MISSING: '+token);
for(const token of ['id="qloraPreflight"','id="qloraPreflightState"',
"post('qlora.preflight')","case 'qlora.preflight':",
'обучение НЕ ЗАПУЩЕНО'])
 assert(html.includes(token),'P04_PREFLIGHT_UI_MISSING: '+token);
assert((html.match(/<button class="core /g)||[]).length===8,'NOX_CORE_COUNT_CHANGED');
assert(cs.includes('case "chat": await Generate(Text("text"), Text("requestId")); break;'),'CHAT_CHANGED');
assert(cs.includes('active.Cancel();'),'STOP_CHANGED');
console.log('NOX_R8_QLORA_PREFLIGHT_SOURCE_PASS: READ_ONLY, NO FALSE TRAINING');
