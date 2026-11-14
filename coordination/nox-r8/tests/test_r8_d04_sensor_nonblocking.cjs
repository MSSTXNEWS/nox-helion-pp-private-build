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
check(source.includes('gpu = gpuSnapshot,')&&source.includes('private object GetGpuStatus()'),'real GPU sensor retained without synchronous fallback');
check(source.includes('case "stop":')&&source.includes('case "chat":'),'original STOP/chat routes preserved');
check(source.includes('private object GetSystemState(object gpuSnapshot)'),'sensor status requires precollected off-UI GPU snapshot');
check(!source.includes('gpu = gpuSnapshot ?? GetGpuStatus(),'),'sensor status cannot fall through to synchronous nvidia-smi');
check((source.match(/\bGetGpuStatus\b/g)||[]).length===2,'only background call and GPU sensor method remain');
// Read the actual C# owner method: every GPU must influence the thermal HOLD.
// This is a SOURCE_ONLY contract, not a simulated NVIDIA device or Windows test.
const gpuMethod=source.match(/private object GetGpuStatus\(\)[\s\S]*?\n    private string BuildLocalContext\(/);
check(!!gpuMethod,'existing native GPU probe');
const gpuSrc=gpuMethod[0];
check(gpuSrc.includes('StandardOutput.ReadToEndAsync()'),'drain entire CSV before waiting for process');
check(gpuSrc.includes('outputTask.GetAwaiter().GetResult()'),'consume complete real nvidia-smi output');
check(gpuSrc.includes('if (!outputTask.Wait(400))')&&gpuSrc.includes('reason = "stdout_timeout"'),'post-exit stdout pipe cannot hang telemetry worker indefinitely');
check(gpuSrc.indexOf('outputTask.Wait(400)')<gpuSrc.indexOf('outputTask.GetAwaiter().GetResult()'),'bounded pipe wait is enforced before blocking readback');
check(!gpuSrc.includes('StandardOutput.ReadLine()'),'first-GPU-only status cannot hide hot adapters');
check(gpuSrc.includes("csv.Split(new[] { '\\r', '\\n' }"),'parse each reported adapter row');
check(gpuSrc.includes('foreach (var row in rows)')&&gpuSrc.includes('names.Add(name)'),'inspect all real NVIDIA adapters');
check(gpuSrc.includes('hottest = Math.Max(hottest, temp)'),'hottest measured adapter wins');
check(gpuSrc.includes('thermalHold = hottest >= 65')&&gpuSrc.includes('coolingPauseSeconds = hottest >= 65 ? 180 : 0'),'do not show false thermal clearance');
check(gpuSrc.includes('return new { available = false, reason = "unexpected_format" }'),'unknown or malformed sensor data must not claim safe');
check(gpuSrc.includes('gpuCount = names.Count'),'explicit physical NVIDIA adapter count');
console.log('D04 sensor nonblocking / multi-GPU SOURCE_ONLY contract PASS; .NET/Windows/owner-GPU NOT_TESTED');