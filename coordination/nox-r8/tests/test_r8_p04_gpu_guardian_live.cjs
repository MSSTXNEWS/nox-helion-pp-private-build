"use strict";
/* P04: real original nvidia-smi vendor reader compiled into R8, fail-closed UI IPC.
 * SOURCE_ONLY; Windows smoke checks actual owner WebView2 roundtrip separately.
 */
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const root=path.resolve(__dirname,"..");
const html=fs.readFileSync(path.join(root,"overrides","src","index.html"),"utf8");
const native=fs.readFileSync(path.join(root,"overrides","src","MainWindow.xaml.cs"),"utf8");
const guardian=fs.readFileSync(path.join(root,"integrations","v16","P04","GpuGuardian","GpuGuardian.cs"),"utf8");
assert.match(guardian,/public async Task<IReadOnlyList<GpuTelemetrySample>> ReadNvidiaAsync/);
assert.match(guardian,/TimeSpan.FromSeconds\(5\)/);
assert.match(native,/new NoxP04\.GpuGuardian\.GpuGuardian\(\)/);
assert.match(native,/case "gpu\.guardian": _ = SendP04GpuGuardianAsync\(\);/);
assert.match(native,/sensorReadLock\.WaitAsync\(0\)/);
assert.match(html,/id="gpuGuardianRefresh"/);
assert.match(html,/id="gpuGuardianState"/);
const start=html.indexOf("case 'gpu.guardian':{"),end=html.indexOf("\ncase 'system':",start);
assert.ok(start>=0&&end>start,"P04_ACTUAL_WEBVIEW_REPLY_HANDLER_HOLD");
const fixture=html.slice(start,end);
assert.ok(!fixture.includes("innerHTML")&&!fixture.includes("learn.request")&&!fixture.includes("model.pull"),
  "P04_READONLY_NOT_ALLOWED_TO_INJECT_HTML_OR_START_TRAINING");
for(const sample of [
  {source:"P04_GPU_GUARDIAN",available:false,thermalHold:true,reason:"NVIDIA_TELEMETRY_UNAVAILABLE",samples:[]},
  {source:"P04_GPU_GUARDIAN",available:true,thermalHold:false,samples:[{
    state:"READY",name:"GPU0",temperatureC:42,memoryUsedMiB:100,memoryTotalMiB:1024
  }]}
]){
  const box={textContent:"",dataset:{}},states=[];
  vm.runInNewContext("switch('gpu.guardian'){"+fixture+"}",{
    v:sample,$:id=>{assert.equal(id,"gpuGuardianState");return box;},
    window:{noxVisual:{setThermalHold(value){states.push(value);}}}
  },{timeout:1500});
  assert.equal(box.dataset.source,"P04_GPU_GUARDIAN");
  assert.equal(box.dataset.readback,"DONE");
  assert.ok(box.textContent.includes(sample.available?"GPU Guardian":"Датчики NVIDIA"));
  if(!sample.available)assert.deepEqual(states,[true]);
}
console.log("P04_VENDOR_GPU_GUARDIAN_NATIVE_SOURCE_ONLY_PASS");
