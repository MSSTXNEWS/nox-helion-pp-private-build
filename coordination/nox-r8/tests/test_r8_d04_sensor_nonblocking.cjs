'use strict';
/* D04: genuine native GPU sensor polling must not block WebView2 chat/STOP.
 * SOURCE CONTRACT ONLY. Windows/UIA/owner-GPU execution remains required. */
const fs=require('node:fs'),path=require('node:path');
const candidates=[path.resolve(__dirname,'src','MainWindow.xaml.cs'),
  path.resolve(__dirname,'..','overrides','src','MainWindow.xaml.cs')];
const available=candidates.filter(p=>fs.existsSync(p));
function check(v,name){if(!v)throw Error('D04_SENSOR_STATUS_HOLD '+name);}
check(available.length>0,'native source exists');
const source=fs.readFileSync(available[0],'utf8');
check((source.match(/_ = SendSystemStateAsync\(\);/g)||[]).length===2,'startup and dashboard dispatch asynchronously');
check(!source.includes('Send("system", GetSystemState());'),'no synchronous GPU probe on WebView2 dispatcher');
check(source.includes('private readonly SemaphoreSlim sensorReadLock = new(1, 1);'),'single-flight polling lock');
const method=source.match(/private async Task SendSystemStateAsync\(\)[\s\S]*?\n    private object GetSystemState\(/);
check(!!method,'async native polling method');
check(method[0].includes('sensorReadLock.WaitAsync(0)'),'duplicate polls fail fast');
check(method[0].includes('Task.Run(GetGpuStatus)'),'nvidia-smi runs off UI dispatcher');
check(method[0].includes('Send("system", GetSystemState(gpu))'),'real sensor snapshot published through native IPC');
check(method[0].includes('sensorReadLock.Release()'),'polling lock released on all paths');
check(method[0].includes('Dispatcher.HasShutdownStarted'),'closing WebView2 never receives queued telemetry');
check(source.includes('gpu = gpuSnapshot ?? GetGpuStatus(),'),'real GPU sensor retained without synthetic telemetry');
check(source.includes('case "stop":')&&source.includes('case "chat":'),'original STOP/chat routes preserved');
console.log('D04 sensor nonblocking SOURCE_ONLY contract PASS; .NET/Windows/owner-GPU NOT_TESTED');