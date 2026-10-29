/* NOX R29. Real run timestamps only. Product progress/ETA is evidence-gated. */
(function(){
"use strict";
const D=window.NOX_CONTROL_DATA||{},S=window.NOX_SCHEDULE_SNAPSHOT||{};
const q=id=>document.getElementById(id);
const esc=x=>String(x==null?"Н/Д":x).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const parse=s=>{const d=typeof s==="string"?new Date(s):null;return d&&Number.isFinite(d.getTime())?d:null};
const fmt=new Intl.DateTimeFormat("ru-RU",{timeZone:"Europe/Moscow",day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false});
const clock=t=>parse(t)?fmt.format(parse(t))+" МСК":"Н/Д";
const validSHA=s=>typeof s==="string"&&/^[0-9a-f]{40}$/.test(s);
const ids=new Set((Array.isArray(D.automations)?D.automations:[]).filter(a=>a.kind==="source_support").map(a=>a.id));
let currentFilter="current",liveEvents=[],latestApi=null;
function tasks(){const src=Array.isArray(S.tasks)?S.tasks:[];return src.filter(x=>x&&typeof x==="object").map(x=>({id:x.id,title:x.title,enabled:x.enabled===true,current:x.scope==="current"||x.scope==null&&ids.has(x.id),run:x.last_run||null,schedule:x.schedule||""})).sort((a,b)=>(parse(b.run?.started_at)?.getTime()||0)-(parse(a.run?.started_at)?.getTime()||0))}
function schedule(s){const m=String(s).match(/BYMINUTE=(\d{1,2})/);return m&&+m[1]<60?"ежечасно :"+String(+m[1]).padStart(2,"0")+" МСК":"Н/Д"}
function duration(r){const a=parse(r?.started_at),b=parse(r?.completed_at);if(!a||!b||b<a)return"Н/Д";const m=Math.round((b-a)/60000);return m<60?m+" мин":Math.floor(m/60)+" ч "+m%60+" мин"}
function qa(){const z=Array.isArray(D.acceptance_events_verified)?D.acceptance_events_verified:[],found=new Set();return z.filter(x=>{if(!x||x.qa_accepted!==true||x.reviewer!=="manual-2"||x.head!==D.head||!validSHA(x.receipt_blob)||!x.task_id||!parse(x.completed_at)||found.has(x.task_id))return false;found.add(x.task_id);return true})}
function status(s){return s==="completed"?"ЗАВЕРШЕНО":s==="in_progress"?"ВЫПОЛНЯЕТСЯ":s==="failed"?"ОШИБКА":s==="no_update"?"БЕЗ РЕЗУЛЬТАТА":"Н/Д"}
function renderRuns(){const out=q("ops-runs");if(!out)return;const selected=tasks().filter(x=>currentFilter==="all"||currentFilter==="current"&&x.current||currentFilter==="archive"&&!x.current||currentFilter==="failed"&&x.run?.status==="failed"||currentFilter==="running"&&x.run?.status==="in_progress");
out.innerHTML=selected.map(x=>'<article class="ops-job"><div><b>'+esc(x.title)+'</b><small>'+esc(status(x.run?.status))+'</small></div><time>'+esc(clock(x.run?.completed_at||x.run?.started_at))+'</time><p>'+esc(x.run?.completed_at?"Последнее фактическое завершение":"Последний фактический старт")+' · '+esc(duration(x.run))+'</p><p>НАЧАЛО: '+esc(clock(x.run?.started_at))+'</p><p>ПЛАН: '+esc(schedule(x.schedule))+'</p><p class="ops-id">RunID: '+esc(x.run?.run_id||"Н/Д")+' · '+(x.enabled?"ENABLED":"DISABLED")+'</p></article>').join("")||'<div class="ops-empty">Нет записей для этого фильтра.</div>';
q("ops-total").textContent=selected.length+" исполнителей";
}
function drawChart(){
const svg=q("ops-chart");if(!svg)return;const runs=new Map();
tasks().forEach(x=>{if(parse(x.run?.started_at))runs.set(x.run?.run_id||x.id,x.run.started_at)});
liveEvents.forEach(x=>{const k=x.run_id||x.runId||x.id,t=x.timestamp||x.started_at||x.completed_at;if(k&&parse(t))runs.set(k,t)});
const accepted=qa();const stamps=[...runs.values()].map(x=>parse(x).getTime()).concat(accepted.map(x=>parse(x.completed_at).getTime()));
const end=stamps.length?Math.floor(Math.max(...stamps)/3600000)*3600000:Math.floor(Date.now()/3600000)*3600000,start=end-7*3600000;
const values=Array.from({length:8},(_,i)=>({t:start+i*3600000,r:0,a:0}));
runs.forEach(t=>{const i=Math.floor((parse(t).getTime()-start)/3600000);if(i>=0&&i<8)values[i].r++});
accepted.forEach(x=>{const i=Math.floor((parse(x.completed_at).getTime()-start)/3600000);if(i>=0&&i<8)values[i].a++});
const max=Math.max(2,...values.map(x=>Math.max(x.r,x.a))),X=i=>55+98*i,Y=v=>215-165*v/max;
const line=k=>values.map((v,i)=>(i?"L":"M")+X(i)+" "+Y(v[k])).join(" ");
let text="";for(let i=0;i<=4;i++){const v=max*i/4,y=Y(v);text+='<line class="gridline" x1="55" y1="'+y+'" x2="743" y2="'+y+'"/><text x="5" y="'+(y+5)+'">'+(Math.round(v*10)/10)+'</text>'}
text+='<path class="curve-run" d="'+line("r")+'"/><path class="curve-qa" d="'+line("a")+'"/>';
values.forEach((v,i)=>{text+='<circle cx="'+X(i)+'" cy="'+Y(v.r)+'" r="3" fill="#b6e1df"><title>'+v.r+' наблюдаемых запусков</title></circle><circle cx="'+X(i)+'" cy="'+Y(v.a)+'" r="3" fill="#e2b77f"><title>'+v.a+' QA_ACCEPTED</title></circle><text x="'+(X(i)-21)+'" y="248">'+esc(new Intl.DateTimeFormat("ru-RU",{timeZone:"Europe/Moscow",hour:"2-digit",minute:"2-digit"}).format(new Date(v.t)))+'</text>'});
svg.innerHTML=text;forecast(accepted);
}
function forecast(accepted){
const out=q("ops-eta"),note=q("ops-eta-note"),verified=D.prebuild_verified;
if(!out||!note)return;
if(!verified||verified.head!==D.head||!Number.isInteger(verified.remaining)||verified.remaining<0){out.textContent="Н/Д";note.textContent="Нет подтверждённого остатка предсборочных критериев на текущем HEAD. Исторический 6/29 не является основанием прогноза.";return}
if(verified.remaining===0){out.textContent="T10 CHECK";note.textContent="Нулевой остаток не доказывает готовность Windows EXE или E07.";return}
if(accepted.length<2){out.textContent="Н/Д";note.textContent="Недостаточно независимых QA_ACCEPTED для скорости. Нужны два результата с временем и тем же HEAD.";return}
const times=accepted.map(x=>parse(x.completed_at).getTime()).sort((a,b)=>a-b),hours=(times.at(-1)-times[0])/3600000;
if(hours<=0){out.textContent="Н/Д";note.textContent="Не установлена временная скорость приёмки.";return}
const remaining=verified.remaining/((accepted.length-1)/hours);
out.textContent=remaining<1?Math.round(remaining*60)+" мин":remaining.toFixed(1).replace(".",",")+" ч";
note.textContent="Условная оценка до SOURCE_READY. Сборка, E07, новые ошибки и внешние задержки не включены.";
}
function render(){
const items=tasks(),primary=items.filter(x=>x.current),most=items.find(x=>x.run?.started_at);
const arr=[["РУЧНЫЕ · ГЛАВНЫЕ",(D.manuals||[]).length,"Из ролевого реестра"],["AUTO · АКТУАЛЬНЫЕ",primary.length,primary.filter(x=>x.enabled).length+" включены"],["АРХИВ / ОТЛОЖЕННЫЕ",items.length-primary.length,"История сохранена"],["ПОСЛЕДНИЙ ФАКТ. ЗАПУСК",most?clock(most.run.started_at):"Н/Д","Не расписание"]];
q("ops-stats").innerHTML=arr.map(x=>'<article class="ops-stat"><span>'+esc(x[0])+'</span><b>'+esc(x[1])+'</b><small>'+esc(x[2])+'</small></article>').join("");
q("ops-evidence").textContent="Срез последних фактических запусков: "+(S.last_run_observed_at?clock(S.last_run_observed_at):"Н/Д")+". Исторический снимок, не live.";
renderRuns();drawChart();
}
function install(){
if(q("nox-operational-r29"))return;
const css=document.createElement("style");css.textContent='.nox-ops{margin:22px 0;color:#e5d4b9}.ops-banner{display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;padding:19px;border:1px solid #c6a17388;border-left:3px solid #e4b984;background:linear-gradient(110deg,#2e2117cf,#070c11f5);border-radius:4px}.ops-banner h2{font-size:23px;font-weight:400;letter-spacing:.14em;margin:7px 0}.ops-banner p,.ops-evidence,.ops-job p{color:#a7b2b1;font-size:11px}.ops-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin:11px 0}.ops-stat,.ops-panel,.ops-job{border:1px solid #b39a7959;background:linear-gradient(150deg,#172023e9,#06090df4);border-radius:4px;padding:15px}.ops-stat span{font-size:9px;color:#afa7a1;letter-spacing:.1em}.ops-stat b{display:block;font-size:25px;font-weight:380;color:#e9c28e;margin:7px 0}.ops-stat small{color:#adb6b4;font-size:10px}.ops-columns{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(240px,.85fr);gap:11px}.ops-panel h3{font-size:14px;letter-spacing:.14em;font-weight:450;margin:0 0 15px}.ops-panel p{font-size:11px;color:#a7b0b0;line-height:1.7}.ops-chart{width:100%;height:auto;min-height:195px}.ops-chart text{fill:#adb6b5;font:11px Consolas,monospace}.ops-chart .gridline{stroke:#aeada235;stroke-dasharray:3 7}.ops-chart .curve-run{fill:none;stroke:#b8e4e3;stroke-width:3}.ops-chart .curve-qa{fill:none;stroke:#e4b47c;stroke-width:3}.ops-eta{font-size:35px;font-weight:330;color:#e4c291;margin:19px 0}.ops-filter{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}.ops-filter button{cursor:pointer;background:#142025;color:#e1d6c8;border:1px solid #b7a07862;border-radius:3px;padding:9px 12px}.ops-filter button.active{background:#73532f88;border-color:#e0b681}.ops-runs{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:9px}.ops-job>div:first-child{display:flex;justify-content:space-between;gap:8px}.ops-job b{font-size:11px}.ops-job small{font-size:9px;color:#cbb39b}.ops-job time{display:block;margin:12px 0 5px;font:16px Consolas,monospace;color:#e7bc8a}.ops-job p{margin:6px 0}.ops-id{font-family:Consolas,monospace;overflow-wrap:anywhere}@media(max-width:1100px){.ops-columns{grid-template-columns:1fr}.ops-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){.ops-runs{grid-template-columns:1fr}.ops-stat b{font-size:20px}}';
document.head.append(css);
const pane=document.createElement("section");pane.id="nox-operational-r29";pane.className="nox-ops";
pane.innerHTML='<div class="ops-banner"><div><span class="eyebrow">NOX HELION · R29 / ACTUAL EVIDENCE</span><h2>ПУЛЬС ИСПОЛНЕНИЯ</h2><p>Только фактические запуски, независимая QA и реальные результаты</p></div><span class="ops-evidence" id="ops-evidence"></span></div><div class="ops-stats" id="ops-stats"></div><div class="ops-columns"><article class="ops-panel"><h3>КРИВЫЕ ПРОИЗВОДИТЕЛЬНОСТИ</h3><p>Голубая — фактические старты, янтарная — принятые QA TaskID</p><svg class="ops-chart" id="ops-chart" viewBox="0 0 800 265" role="img" aria-label="Фактические запуски и QA_ACCEPTED по часовым интервалам"></svg><p>Виден только последний запуск каждой роли; пробелы не означают нулевую производительность.</p></article><article class="ops-panel"><h3>ПРОГНОЗ ДО SOURCE_READY</h3><div class="ops-eta" id="ops-eta">Н/Д</div><p id="ops-eta-note"></p></article></div>';
const overview=q("tab-overview"),before=q("metrics");if(overview){if(before&&before.parentNode===overview)overview.insertBefore(pane,before);else overview.append(pane)}
const section=document.createElement("section");section.id="nox-runs-r29";section.className="nox-ops";
section.innerHTML='<div class="ops-banner"><div><h2>ПОСЛЕДНИЕ ФАКТИЧЕСКИЕ ЗАПУСКИ</h2><p>Начало / завершение / длительность, расписание отдельно</p></div><span class="ops-evidence" id="ops-total"></span></div><div class="ops-filter"><button data-op="current" class="active">Актуальные</button><button data-op="all">Все</button><button data-op="archive">Архив</button><button data-op="running">Выполняются</button><button data-op="failed">Ошибка</button></div><div class="ops-runs" id="ops-runs"></div>';
if(q("tab-executors"))q("tab-executors").append(section);
section.querySelectorAll("[data-op]").forEach(b=>b.addEventListener("click",()=>{currentFilter=b.dataset.op;section.querySelectorAll("[data-op]").forEach(x=>x.classList.toggle("active",x===b));renderRuns()}));
render();
}
document.addEventListener("nox:ops-events",ev=>{const arr=Array.isArray(ev.detail)?ev.detail:ev.detail?.events;if(Array.isArray(arr)){liveEvents=arr;render()}});
document.addEventListener("nox:schedule-update",ev=>{if(Array.isArray(ev.detail?.tasks)){S.tasks=ev.detail.tasks;if(Array.isArray(ev.detail.current_auto_ids)){ids.clear();ev.detail.current_auto_ids.forEach(id=>ids.add(id))}render()}});
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",install,{once:true});else install();
})();