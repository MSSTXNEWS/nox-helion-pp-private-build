/* P03 media weights opt-in WebView2 UI, secondary-only. No JS downloads or external requests. */
(function(){'use strict';
const OPTIONS=Object.freeze([{"kind":"3d","id":"hunyuan3d-mini","name":"Hunyuan3D 2 Mini","source":"https://huggingface.co/tencent/Hunyuan3D-2mini"},{"kind":"3d","id":"hunyuan3d-21","name":"Hunyuan3D 2.1","source":"https://huggingface.co/tencent/Hunyuan3D-2.1"},{"kind":"3d","id":"trellis","name":"TRELLIS 3D","source":"https://huggingface.co/microsoft/TRELLIS-image-large"},{"kind":"video","id":"wan21-small","name":"Wan 2.1 T2V 1.3B","source":"https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B"},{"kind":"video","id":"wan22-5b","name":"Wan 2.2 TI2V 5B","source":"https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B"},{"kind":"video","id":"hunyuan15","name":"HunyuanVideo 1.5","source":"https://huggingface.co/tencent/HunyuanVideo-1.5"},{"kind":"photo","id":"flux2-klein","name":"FLUX.2 Klein 4B","source":"https://huggingface.co/black-forest-labs/FLUX.2-klein-4B"},{"kind":"photo","id":"qwen-image-2512","name":"Qwen Image 2512","source":"https://huggingface.co/Qwen/Qwen-Image-2512"}]);
const byId=new Map(OPTIONS.map(x=>[x.id,x])),byName=id=>byId.get(id);
const el=id=>document.getElementById(id);
const H=/^[a-f0-9]{64}$/i,R=/^[a-f0-9]{40}$/i;
const state={kind:"3d",verified:new Map(),jobs:new Map(),pending:new Set(),host:false,capabilities:{}};
const fmt=n=>typeof n==="number"&&Number.isFinite(n)&&n>=0?(n/1073741824).toFixed(2)+" ГБ":"Н/Д";
const safe=(txt,max=130)=>String(txt??"").slice(0,max);
const element=(tag,cls,txt)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(txt!==undefined)e.textContent=txt;return e};
function ready(x){return x&&x.installable===true&&H.test(x.sha256||"")&&R.test(x.immutableRevision||"")&&typeof x.expectedBytes==="number"&&x.expectedBytes>0&&x.licenseVerified===true;}
function modelJob(id){return state.jobs.get(id)||null}
function stateName(id){const j=modelJob(id),meta=state.verified.get(id);if(j){if(j.state==="Downloading")return "Загрузка · "+fmt(j.completedBytes)+" / "+fmt(j.totalBytes);return safe(j.state)}
 return ready(meta)?"ГОТОВО К СКАЧИВАНИЮ":"Нужны SHA/Revision/Host";}
function render(){
 const cards=el("mediaWeightCards");cards.replaceChildren();
 const visible=OPTIONS.filter(m=>m.kind===state.kind);
 for(const entry of visible){
  const item=element("article","p03-media-card");
  const header=element("div","p03-media-card-head");
  header.append(element("strong","",entry.name),element("small","",entry.kind.toUpperCase()));
  const info=element("p","p03-media-state",stateName(entry.id));
  const meta=state.verified.get(entry.id),job=modelJob(entry.id);
  const size=element("small","p03-media-size","Размер комплекта: "+fmt(meta?.expectedBytes));
  const ops=element("div","p03-media-ops");
  const get=element("button","p03-media-get","Скачать веса");
  get.type="button";get.dataset.model=entry.id;
  const can=state.host&&state.capabilities.download===true&&ready(meta)&&
   el("mediaRightsAck").checked&&!state.pending.has(entry.id)&&!["Downloading","Queued"].includes(job?.state);
  get.disabled=!can;
  get.title=can?"Скачать проверенный комплект по разрешению Windows host":"Требуется проверенный комплект, права и подключённый Windows host";
  get.addEventListener("click",()=>dispatch("download",entry.id));
  ops.append(get);
  if(job&&["Downloading","Queued"].includes(job.state)){
   const stop=element("button","p03-media-stop","Отменить");
   stop.type="button";stop.disabled=!(state.host&&state.capabilities.cancel===true&&job.jobId);
   stop.addEventListener("click",()=>dispatch("cancel",entry.id,job.jobId));ops.append(stop);
   if(typeof job.completedBytes==="number"&&typeof job.totalBytes==="number"&&job.totalBytes>0){
     const meter=element("progress","p03-media-progress");meter.max=job.totalBytes;meter.value=Math.min(job.totalBytes,job.completedBytes);ops.append(meter);
   }
  }
  const source=element("a","p03-media-source","Официальный источник");
  source.href=entry.source;source.rel="noopener noreferrer";source.target="_blank";
  item.append(header,info,size,ops,source);cards.append(item);
 }
 el("mediaWeightSummary").textContent=state.host?"Windows host подключён · команды только по подтверждённым весам.":"Каталог доступен. Загрузка требует подтверждённого Windows host и SHA-256 файлов.";
}
function dispatch(action,id,jobId=null){
 const model=byName(id);if(!model||state.pending.has(id)||!state.host)return;
 if(action==="download"&&(!ready(state.verified.get(id))||!state.capabilities.download||!el("mediaRightsAck").checked))return;
 if(action==="cancel"&&(!jobId||!state.capabilities.cancel))return;
 const cid="mw"+Date.now().toString(36)+Math.random().toString(36).slice(2,8);
 state.pending.add(id);render();
 const msg={type:"p03.media.command.v1",commandId:cid,action,modelId:id,licenseAcknowledged:el("mediaRightsAck").checked,jobId};
 try{window.chrome.webview.postMessage(msg);el("mediaWeightSummary").textContent="Команда отправлена, ожидается подтверждение host. Это ещё не скачивание."}
 catch{state.pending.delete(id);render();el("mediaWeightSummary").textContent="Нет связи с Windows host. Файлы не скачаны."}
}
function receive(msg){
 if(!msg||typeof msg!=="object")return;
 if(msg.type==="p03.media.snapshot.v1"){
  if(!Array.isArray(msg.models)||msg.models.length>64)return;
  const mapped=new Map();
  for(const m of msg.models){if(!m||!byId.has(m.id))continue;mapped.set(m.id,m)}
  state.verified=mapped;state.host=true;state.capabilities=(msg.capabilities&&typeof msg.capabilities==="object")?msg.capabilities:{};
  if(Array.isArray(msg.jobs)&&msg.jobs.length<=64)state.jobs=new Map(msg.jobs.filter(x=>x&&byId.has(x.modelId)).map(x=>[x.modelId,x]));
  render();
 }else if(msg.type==="p03.media.progress.v1"&&msg.job&&byId.has(msg.job.modelId)){
  const j=msg.job;state.jobs.set(j.modelId,{...j});render();
 }else if(msg.type==="p03.media.ack.v1"&&byId.has(msg.modelId)){
  state.pending.delete(msg.modelId);render();
  el("mediaWeightSummary").textContent=msg.accepted===true?"Host принял команду. Прогресс поступит в событиях.":"Host отклонил: "+safe(msg.reason||"нет разрешения");
 }
}
for(const b of document.querySelectorAll("[data-media-kind]"))b.addEventListener("click",()=>{
 const kind=b.dataset.mediaKind;if(!["3d","video","photo"].includes(kind))return;
 state.kind=kind;
 for(const x of document.querySelectorAll("[data-media-kind]"))x.setAttribute("aria-pressed",String(x===b));
 render();
});
el("mediaRightsAck").addEventListener("change",render);
if(window.chrome?.webview?.addEventListener)window.chrome.webview.addEventListener("message",e=>receive(e.data));
render();
})();
