/* NOX GENESIS evidence panel. Uses only an EXISTING authenticated same-origin OneHost route.
 * Host sets <meta name="nox-genesis-evidence-endpoint" content="/the-real-route">.
 * No route is invented. No fake metrics; HOLD if missing. */
const VERSION="nox-genesis-live-evidence-v1";
const PAGES=new Set(["training.html","memory.html","resonance.html","chat.html"]);
const page=location.pathname.split("/").pop().toLowerCase();
const ACTIVE=PAGES.has(page);
const css=[
"#nox-genesis-trace{position:fixed;z-index:2147483000;right:14px;top:70px;width:min(300px,calc(100vw - 28px));background:rgba(8,7,6,.94);border:1px solid #806044;border-radius:11px;box-shadow:0 8px 40px #000a;color:#e6cfac;font:12px/1.5 system-ui,sans-serif;padding:12px}",
"#nox-genesis-trace header{display:flex;align-items:center;gap:8px;justify-content:space-between}",
"#nox-genesis-trace button{background:#21190f;border:1px solid #826342;border-radius:7px;color:#f5d59b;padding:6px 9px;cursor:pointer}",
"#nox-genesis-trace button:focus-visible{outline:2px solid #f2c068}",
"#nox-genesis-trace .noxg-body{white-space:pre-wrap;overflow-wrap:anywhere;margin-top:8px}",
"@media(max-width:680px){#nox-genesis-trace{top:auto;bottom:72px;right:8px;width:min(270px,calc(100vw - 18px))}}"
].join("\n");
function make(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
function trustedEndpoint(){
  const v=document.querySelector('meta[name="nox-genesis-evidence-endpoint"]')?.getAttribute("content");
  if(!v||!v.startsWith("/")||v.startsWith("//"))return null;
  try{const u=new URL(v,location.origin);return u.origin===location.origin?u.href:null;}catch{return null;}
}
function presentation(x){
  if(!x||x.schema!==VERSION)return "HOLD · неверная схема ответа";
  if(x.state==="HOLD")return "HOLD · "+String(x.reason||"нет данных").slice(0,140);
  if(x.state!=="RECEIPT_FORMAT_VALIDATED_NOT_GPU_REPLAYED")return "HOLD · неподтверждённый статус";
  if(!/^[a-f0-9]{64}$/.test(x.training?.model_sha256||""))return "HOLD · отсутствует SHA";
  const t=x.training;
  const output=["OneHost: квитанция прочитана; GPU-приёмка не проведена",
    "NOX SHA: "+t.model_sha256.slice(0,12)+"…",
    "Optimizer steps (по квитанции): "+(Number.isInteger(t.optimizer_steps_claimed)?t.optimizer_steps_claimed:"HOLD"),
    "Checkpoint: "+(t.checkpoint_sha256?t.checkpoint_sha256.slice(0,12)+"…":"HOLD"),
    "S03: "+(x.memory?.state==="CONNECTED_BY_TRUSTED_HOST"?"readback по квитанции":"HOLD")];
  if(x.quality?.state==="RECEIPT_EVALUATION_NOT_INDEPENDENTLY_REPLAYED")
    output.push(x.quality.benchmark+": "+x.quality.correct+"/"+x.quality.total+" (не повторено независимо)");
  else output.push("Бенчмарк: HOLD");
  return output.join("\n");
}
async function load(){
  const url=trustedEndpoint();
  if(!url)return {schema:VERSION,state:"HOLD",reason:"OneHost не указал действующий endpoint"};
  const c=new AbortController(),timer=setTimeout(()=>c.abort(),5000);
  try{
    const r=await fetch(url,{credentials:"same-origin",cache:"no-store",redirect:"error",signal:c.signal,
      headers:{Accept:"application/json"}});
    if(!r.ok)return {schema:VERSION,state:"HOLD",reason:"OneHost HTTP "+r.status};
    if(Number(r.headers.get("content-length")||0)>250000)throw Error("size");
    const s=await r.text();if(s.length>250000)throw Error("size");return JSON.parse(s);
  }catch{return {schema:VERSION,state:"HOLD",reason:"OneHost недоступен или данные некорректны"};}
  finally{clearTimeout(timer);}
}
export function mountGenesisEvidence(){
  if(!ACTIVE||document.getElementById("nox-genesis-trace"))return;
  const style=make("style");style.textContent=css;document.head.appendChild(style);
  const box=make("section");box.id="nox-genesis-trace";box.setAttribute("aria-label","NOX GENESIS: доказательства обучения");
  const header=make("header");const title=make("strong","GENESIS · ПРОГРЕСС");
  const check=make("button","Проверить");check.type="button";
  const close=make("button","×");close.type="button";close.setAttribute("aria-label","Закрыть");
  const body=make("div","HOLD · ожидаются данные OneHost");body.className="noxg-body";
  body.setAttribute("aria-live","polite");header.append(title,check,close);
  box.append(header,body);document.body.appendChild(box);
  const refresh=async()=>{check.disabled=true;try{body.textContent=presentation(await load());}finally{check.disabled=false;}};
  check.addEventListener("click",refresh);close.addEventListener("click",()=>box.remove());void refresh();
}
if(ACTIVE){
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",mountGenesisEvidence,{once:true});
  else mountGenesisEvidence();
}
