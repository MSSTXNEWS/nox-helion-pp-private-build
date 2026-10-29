/* NOX R30. Owner-roster based independent QA/source performance comparison.
   Static evidence only; no fabricated QA or product completion. */
(function(w,d){
"use strict";
var D=w.NOX_CONTROL_DATA||{},H=w.NOX_PERFORMANCE_HISTORY||D.performance_history||{schema:"NOX_R30_HISTORY_V1",snapshots:[]};
var esc=x=>String(x==null?"Н/Д":x).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
var sha=s=>typeof s==="string"&&/^[a-f0-9]{40}$/.test(s);
var stamp=s=>{var v=Date.parse(s);return Number.isFinite(v)?v:null};
var whole=x=>Number.isSafeInteger(x)&&x>=0;
function validRecord(x){
 return x&&whole(x.accepted)&&whole(x.integrated)&&sha(x.receipt_blob)&&
 typeof x.evidence_url==="string"&&/^https:\/\/github\.com\//.test(x.evidence_url)&&
 (x.accepted===0||x.qa_reviewer==="manual-2");
}
function series(history,workerId,head){
 if(!history||history.schema!=="NOX_R30_HISTORY_V1"||!Array.isArray(history.snapshots)||!sha(head))return[];
 var points=[];
 history.snapshots.forEach(s=>{
  if(!s||s.head!==head||stamp(s.at)==null||!Array.isArray(s.workers))return;
  var x=s.workers.find(r=>String(r.id)===String(workerId));
  if(validRecord(x))points.push({at:stamp(s.at),a:x.accepted,i:x.integrated,total:whole(x.fixed_total)&&x.fixed_total>0?x.fixed_total:null,url:x.evidence_url});
 });
 points.sort((a,b)=>a.at-b.at);
 return points.filter((x,i)=>i===0||x.at!==points[i-1].at);
}
function metrics(points){
 var b=points.at(-1),a=points.at(-2),c=points.at(-3);
 var result={value:b?b.a:null,integrated:b?b.i:null,delta:null,rate:null,change:null,trend:"НЕТ ИСТОРИИ",percent:null,url:b?b.url:null};
 if(b&&b.total)result.percent=Math.round(100*b.a/b.total);
 if(!a||!b)return result;
 var delta=b.a-a.a;
 if(delta<0){result.trend="ПРОВЕРИТЬ ОТКАТ";return result}
 result.delta=delta;
 var hours=(b.at-a.at)/3600000;
 if(hours>0)result.rate=delta/hours;
 result.trend=delta>0?"ПРОГРЕСС":"БЕЗ НОВОЙ QA";
 if(!c||c.a>a.a||result.rate==null)return result;
 var previousHours=(a.at-c.at)/3600000;
 if(previousHours<=0)return result;
 var previous=(a.a-c.a)/previousHours;
 result.trend=result.rate>previous?"РОСТ СКОРОСТИ":result.rate<previous?"ПАДЕНИЕ СКОРОСТИ":"СКОРОСТЬ БЕЗ ИЗМЕНЕНИЙ";
 if(previous>0)result.change=Math.round(100*(result.rate-previous)/previous);
 return result;
}
w.NOX_R30_ENGINE={series,metrics};
var CSS='.nox-r30{margin:23px 0}.nox-r30-hero{background:linear-gradient(110deg,#302016ed,#0a0d10ed);border:1px solid #c6a16f6b;border-left:3px solid #e4c18e;padding:20px 23px;border-radius:4px;box-shadow:0 20px 44px #0009}.nox-r30-hero h2{font-size:clamp(17px,2.2vw,25px);font-weight:350;letter-spacing:.13em;margin:8px 0;color:#edddcb}.nox-r30-hero p,.nox-r30-notice{font-size:11px;color:#abb4b1;line-height:1.6}.nox-r30-section{color:#e7bd85;letter-spacing:.18em;font-size:11px;margin:22px 0 12px}.nox-r30-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));gap:10px}.nox-r30-card{background:linear-gradient(130deg,#281d16b5,#0b1519ed 60%,#080b0eea);border:1px solid #b598735b;border-top:2px solid #c9a477b0;padding:17px;border-radius:4px;box-shadow:0 14px 40px #0009;transition:border-color .2s,transform .2s}.nox-r30-card:hover{transform:translateY(-2px);border-color:#e9c496}.nox-r30-top{display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:12px;color:#ebd3b1}.nox-r30-top small{font-size:9px;color:#c3ae92;text-align:right}.nox-r30-top small.up{color:#92d5b5}.nox-r30-top small.down{color:#eaa19a}.nox-r30-mid{display:flex;align-items:center;justify-content:space-between;gap:13px;margin:14px 0}.nox-r30-big{font-size:30px;font-weight:340;color:#f0c391}.nox-r30-big span{display:block;font-size:10px;color:#abbbb8;margin-top:4px}.nox-r30-line{width:135px;max-width:46%;height:55px}.nox-r30-empty{color:#8da09d;font-size:10px;width:46%;text-align:right}.nox-r30-row{display:flex;gap:7px;flex-wrap:wrap;font-size:10px;color:#b6bfbb}.nox-r30-row b{color:#e4c7a0}.nox-r30-track{height:6px;background:#070c10;border:1px solid #c8a16b51;margin-top:13px;overflow:hidden;border-radius:5px}.nox-r30-track span{height:100%;display:block;background:linear-gradient(90deg,#845936,#efc58b);box-shadow:0 0 10px #f8cb8c77}.nox-r30-card p{font-size:10px;color:#aeb7b3;line-height:1.6}.nox-r30-card a{color:#dbb889}@media(max-width:570px){.nox-r30-grid{grid-template-columns:1fr}}@media(prefers-reduced-motion:reduce){.nox-r30-card{transition:none}}';
function line(points){
 if(points.length<2)return'<span class="nox-r30-empty">Кривая: Н/Д</span>';
 var lo=Math.min(...points.map(p=>p.a)),hi=Math.max(...points.map(p=>p.a)),span=Math.max(1,hi-lo);
 var coords=points.slice(-8).map((p,i,a)=>({x:8+i*128/Math.max(1,a.length-1),y:48-39*(p.a-lo)/span}));
 return'<svg class="nox-r30-line" viewBox="0 0 145 55" role="img" aria-label="Кривая подтверждённых QA по последовательным отчётам"><polyline fill="none" stroke="#dfb985" stroke-width="2.8" points="'+coords.map(p=>p.x+','+p.y).join(' ')+'"/>'+coords.map(p=>'<circle cx="'+p.x+'" cy="'+p.y+'" r="3" fill="#e4ceaa"/>').join('')+'</svg>';
}
function card(worker,kind){
 var points=series(H,worker.id,D.head),m=metrics(points);
 var status=m.trend,cl=status.startsWith("РОСТ")?"up":status.startsWith("ПАДЕНИЕ")?"down":"";
 var num=m.value==null?"Н/Д":m.value;
 var delta=m.delta==null?"Н/Д":(m.delta>0?"+":"")+m.delta;
 var trend=m.change==null?"Н/Д":(m.change>0?"+":"")+m.change+"%";
 var bar=m.percent==null?0:Math.min(100,Math.max(0,m.percent));
 var proof=m.url?'<a target="_blank" rel="noopener" href="'+esc(m.url)+'">Открыть квитанцию</a>':'Нужны проверенные квитанции';
 return'<article class="nox-r30-card"><div class="nox-r30-top"><b>'+esc(worker.name||worker.title||worker.id)+'</b><small class="'+cl+'">'+esc(status)+'</small></div><div class="nox-r30-mid"><div class="nox-r30-big">'+esc(num)+'<span>QA_ACCEPTED · '+esc(kind)+'</span></div>'+line(points)+'</div><div class="nox-r30-row"><span>Δ принятых: <b>'+esc(delta)+'</b></span><span>TaskID/ч: <b>'+(m.rate==null?'Н/Д':m.rate.toFixed(2))+'</b></span><span>Δ скорости: <b>'+esc(trend)+'</b></span></div><div class="nox-r30-track"><span style="width:'+bar+'%"></span></div><p>Принято по фиксированному знаменателю: '+(m.percent==null?"Н/Д":m.percent+"%")+' · '+proof+'</p></article>';
}
function render(){
 var root=d.getElementById("nox-r30-comparison");if(!root)return;
 var manual=Array.isArray(D.manuals)?D.manuals:[],autos=Array.isArray(D.automations)?D.automations.filter(a=>a.registry_scope==="current"||!a.registry_scope&&a.kind==="source_support"):[];
 var html='<div class="nox-r30-hero"><div class="eyebrow">NOX HELION · EXECUTOR PERFORMANCE / R30</div><h2>СРАВНЕНИЕ · РОСТ И ПАДЕНИЕ</h2><p>Скорость, динамика, принятые TaskID и изменения к прошлым ОТЧ-1. Сравнение только при достаточной проверенной истории на одном HEAD.</p></div>';
 html+='<div class="nox-r30-section">РУЧНЫЕ · ПРИОРИТЕТ</div><div class="nox-r30-grid">'+manual.map(x=>card(x,"РУЧНОЙ")).join("")+'</div>';
 html+='<div class="nox-r30-section">AUTO · ВСПОМОГАТЕЛЬНЫЕ</div><div class="nox-r30-grid">'+autos.map(x=>card(x,"AUTO")).join("")+'</div>';
 html+='<p class="nox-r30-notice">Для изменения прогресса нужны два подтверждённых отчёта. Для роста/падения именно скорости — три с сопоставимым знаменателем. Нет истории = Н/Д, а не нулевая работа. Исторические FAIL и новые HEAD не смешиваются.</p>';
 root.innerHTML=html;
}
function install(){
 var main=d.getElementById("tab-overview"),metrics=d.getElementById("metrics");if(!main||d.getElementById("nox-r30-comparison"))return;
 var style=d.createElement("style");style.textContent=CSS;d.head.append(style);
 var root=d.createElement("section");root.id="nox-r30-comparison";root.className="nox-r30";
 if(metrics&&metrics.parentNode===main)main.insertBefore(root,metrics.nextSibling);else main.append(root);
 render();
}
d.addEventListener("nox:performance-update",evt=>{if(evt.detail&&evt.detail.schema==="NOX_R30_HISTORY_V1"&&Array.isArray(evt.detail.snapshots)){H=evt.detail;render()}});
if(d.readyState==="loading")d.addEventListener("DOMContentLoaded",install,{once:true});else install();
})(window,document);
