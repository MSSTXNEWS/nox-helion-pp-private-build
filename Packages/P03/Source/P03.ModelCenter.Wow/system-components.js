/* NOX V16 SYSTEM CENTER: drivers, runtimes, patches; only original host can install.
 * Web/mobile browser shows official source + read-only check; never installs directly. */
(function(global){'use strict';
const ITEMS=Object.freeze([{"category":"gpu","id":"nvidia-driver","title":"NVIDIA GPU Driver","url":"https://www.nvidia.com/Download/index.aspx","compatibility":"GPU_VENDOR_MATCH","critical":true},{"category":"gpu","id":"amd-driver","title":"AMD Software GPU Driver","url":"https://www.amd.com/en/support/download/drivers.html","compatibility":"GPU_VENDOR_MATCH","critical":true},{"category":"gpu","id":"intel-driver","title":"Intel Graphics Driver","url":"https://www.intel.com/content/www/us/en/download-center/home.html","compatibility":"GPU_VENDOR_MATCH","critical":true},{"category":"gpu","id":"cuda","title":"CUDA Toolkit","url":"https://developer.nvidia.com/cuda-downloads","compatibility":"NVIDIA_MATRIX","critical":false},{"category":"gpu","id":"rocm","title":"AMD ROCm HIP SDK","url":"https://rocm.docs.amd.com/projects/install-on-windows/en/latest/","compatibility":"AMD_SUPPORT_MATRIX","critical":false},{"category":"gpu","id":"oneapi","title":"Intel oneAPI toolkit","url":"https://www.intel.com/content/www/us/en/developer/tools/oneapi/toolkits.html","compatibility":"INTEL_SUPPORT_MATRIX","critical":false},{"category":"gpu","id":"vulkan","title":"LunarG Vulkan SDK","url":"https://vulkan.lunarg.com/sdk/home","compatibility":"OPTIONAL_3D","critical":false},{"category":"runtime","id":"webview2","title":"WebView2 Runtime","url":"https://developer.microsoft.com/en-us/microsoft-edge/webview2/","compatibility":"NOX_SHELL","critical":false},{"category":"runtime","id":"dotnet8","title":".NET 8 Desktop Runtime","url":"https://dotnet.microsoft.com/en-us/download/dotnet/8.0","compatibility":"NOX_SHELL","critical":false},{"category":"runtime","id":"vcredist","title":"Visual C++ Redistributable x64","url":"https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist","compatibility":"NATIVE_RUNTIME","critical":false},{"category":"runtime","id":"directx","title":"DirectX End User Runtime","url":"https://www.microsoft.com/en-us/download/details.aspx?id=35","compatibility":"OPTIONAL_LEGACY","critical":false},{"category":"runtime","id":"windows-sdk","title":"Windows SDK","url":"https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/","compatibility":"DEVELOPMENT_ONLY","critical":false},{"category":"runtime","id":"wdk","title":"Windows Driver Kit","url":"https://learn.microsoft.com/en-us/windows-hardware/drivers/download-the-wdk","compatibility":"DEVELOPMENT_ONLY","critical":false},{"category":"ai","id":"python","title":"Python Windows","url":"https://www.python.org/downloads/windows/","compatibility":"PYTHON_COMPAT","critical":false},{"category":"ai","id":"pytorch","title":"PyTorch / CUDA wheels","url":"https://pytorch.org/get-started/locally/","compatibility":"CUDA_MATRIX","critical":false},{"category":"ai","id":"ollama","title":"Ollama Windows","url":"https://ollama.com/download/windows","compatibility":"LOCAL_MODEL_HOST","critical":false},{"category":"ai","id":"comfyui","title":"ComfyUI Desktop","url":"https://docs.comfy.org/installation/desktop/windows","compatibility":"SINGLE_GENERATION_HOST","critical":false},{"category":"ai","id":"ffmpeg","title":"FFmpeg","url":"https://ffmpeg.org/download.html","compatibility":"MEDIA_TOOLS","critical":false},{"category":"ai","id":"nodejs","title":"Node.js LTS","url":"https://nodejs.org/en/download","compatibility":"BUILD_TOOLS","critical":false},{"category":"ai","id":"git","title":"Git for Windows","url":"https://git-scm.com/downloads/win","compatibility":"DEV_TOOLS","critical":false},{"category":"ai","id":"git-lfs","title":"Git LFS","url":"https://git-lfs.com/","compatibility":"WEIGHT_DATA","critical":false},{"category":"patch","id":"windows-update","title":"Windows Security & Updates","url":"https://support.microsoft.com/en-us/windows","compatibility":"OS_SECURITY","critical":true},{"category":"patch","id":"powershell","title":"PowerShell 7","url":"https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell-on-windows","compatibility":"SHELL_TOOLS","critical":false},{"category":"patch","id":"windows-terminal","title":"Windows Terminal","url":"https://learn.microsoft.com/en-us/windows/terminal/install","compatibility":"OPTIONAL_TOOLS","critical":false},{"category":"patch","id":"vs-buildtools","title":"Visual Studio Build Tools","url":"https://visualstudio.microsoft.com/downloads/","compatibility":"NATIVE_BUILDS","critical":false},{"category":"patch","id":"nsis","title":"NSIS installer tools","url":"https://nsis.sourceforge.io/Download","compatibility":"INSTALLER_BUILD","critical":false},{"category":"patch","id":"winget","title":"WinGet Package Manager","url":"https://learn.microsoft.com/en-us/windows/package-manager/winget/","compatibility":"SYSTEM_PACKAGES","critical":false}].map(x=>Object.freeze(x)));
const CATEGORIES=Object.freeze([{"id":"gpu","title":"Драйверы / GPU"},{"id":"runtime","title":"Windows Runtime"},{"id":"ai","title":"ИИ / Генерация"},{"id":"patch","title":"Патчи / Разработка"}].map(x=>Object.freeze(x)));
const BY_ID=new Map(ITEMS.map(x=>[x.id,x]));
const SHA=/^[a-f0-9]{64}$/i;
const state={category:"gpu",installed:new Map(),hostReady:false,caps:{},pending:new Map()};
const $=id=>document.getElementById(id);
const node=(tag,cls,s)=>{const x=document.createElement(tag);if(cls)x.className=cls;if(s!==undefined)x.textContent=s;return x};
const STATUS=()=>$("systemComponentStatus");
function attested(d){return d?.readyForInstall===true&&SHA.test(d.artifactSha256||"")&&
 d.publisherSignatureVerified===true&&d.compatibilityVerified===true&&
 typeof d.version==="string"&&d.version.length<100&&d.sourceVerified===true;}
function action(type,item){
 if(!state.hostReady||state.pending.has(item.id))return false;
 if(type==="check"&&state.caps.check!==true)return false;
 if(type==="install"&&(!state.caps.install||!attested(state.installed.get(item.id))||
   !$("systemInstallConsent").checked))return false;
 const command={type:"p03.system.command.v1",commandId:"sc"+Date.now().toString(36)+
 Math.random().toString(36).slice(2,7),action:type,componentId:item.id,
 userApproved:type==="install"&&$("systemInstallConsent").checked};
 state.pending.set(item.id,type);render();
 try{global.chrome.webview.postMessage(command);STATUS().textContent=
  type==="check"?"Запрос проверки отправлен Windows host.":"Запрос установки отправлен host; требуется подтверждение."}
 catch{state.pending.delete(item.id);render();STATUS().textContent="Отсутствует Windows host: установка недоступна";}
 return true;
}
function render(){
 const tabRoot=$("systemComponentTabs");if(!tabRoot)return;
 tabRoot.replaceChildren();
 for(const c of CATEGORIES){
  const button=node("button","system-component-tab",c.title+" · "+ITEMS.filter(i=>i.category===c.id).length);
  button.type="button";button.dataset.systemTab=c.id;button.setAttribute("aria-pressed",String(state.category===c.id));
  button.addEventListener("click",()=>{state.category=c.id;render()});tabRoot.append(button);
 }
 const root=$("systemComponentCards");root.replaceChildren();
 for(const c of ITEMS.filter(i=>i.category===state.category)){
  const live=state.installed.get(c.id),card=node("article","system-component-card");card.dataset.componentId=c.id;
  card.append(node("strong","",c.title),node("small","system-component-meta",c.compatibility));
  card.append(node("p","system-component-state",live?.state||"Не проверено · источник доступен"));
  if(live?.installedVersion)card.append(node("small","","Установлено: "+String(live.installedVersion).slice(0,65)));
  const buttons=node("div","system-component-actions");
  const check=node("button","","Проверить");check.type="button";check.dataset.check=c.id;
  check.disabled=!state.hostReady||state.caps.check!==true||state.pending.has(c.id);
  check.addEventListener("click",()=>action("check",c));
  const install=node("button","","Установить");install.type="button";install.dataset.install=c.id;
  install.disabled=!state.hostReady||state.caps.install!==true||!attested(live)||
   !$("systemInstallConsent").checked||state.pending.has(c.id);
  install.title="Требуется подтверждённая версия, SHA, издатель, совместимость и согласие пользователя";
  install.addEventListener("click",()=>action("install",c));
  const source=node("a","","Официальный источник");source.href=c.url;source.rel="noopener noreferrer";
  source.target="_blank";buttons.append(check,install,source);card.append(buttons);
  root.append(card);
 }
 STATUS().textContent=state.hostReady?
  "Host подключён: проверка версий доступна, установка только с подтверждением.":
  "Веб-версия: ссылки доступны; проверка драйверов и установка требуют Windows host.";
}
if(global.chrome?.webview?.addEventListener)global.chrome.webview.addEventListener("message",event=>{
 const msg=event.data;if(!msg||typeof msg!=="object")return;
 if(msg.type==="p03.system.snapshot.v1"){
  if(!Array.isArray(msg.components)||msg.components.length>100)return;
  state.installed=new Map(msg.components.filter(x=>x&&BY_ID.has(x.id)).map(x=>[x.id,x]));
  state.hostReady=true;state.caps=msg.capabilities||{};render();
 }else if(msg.type==="p03.system.ack.v1"&&BY_ID.has(msg.componentId)){
  state.pending.delete(msg.componentId);render();
  STATUS().textContent=msg.accepted===true?"Host принял команду; результат в событиях.":
   "Host отклонил операцию: "+String(msg.reason||"неизвестно").slice(0,90);
 }
});
document.addEventListener("DOMContentLoaded",()=>{
 $("systemInstallConsent").addEventListener("change",render);
 render();
});
global.NoxSystemComponents=Object.freeze({components:ITEMS,categories:CATEGORIES});
})(window);
