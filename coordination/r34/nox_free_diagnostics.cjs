"use strict";
/* NOX R34 - deterministic ZERO-COST diagnostics.
   No model, no network, no user telemetry and no write capabilities.
   All outputs are evidence-conditioned and reference existing task owners.
*/
(function(root,factory){const api=factory();if(typeof module!=="undefined"&&module.exports)module.exports=api;if(root)root.NOX_FREE_DIAGNOSTICS=api;})(typeof window!=="undefined"?window:null,function(){
"use strict";
const SHA=/^[0-9a-f]{40}$/;
function iso(s){return typeof s==="string"&&Number.isFinite(Date.parse(s))}
function input(raw){
 if(!raw||typeof raw!=="object"||!Array.isArray(raw.manuals)||!Array.isArray(raw.automations))throw Error("DATA_UNAVAILABLE");
 return raw;
}
function analyze(raw,{liveHead=null,runData=null}={}){
 const d=input(raw);const warnings=[],actions=[],evidence=[];
 const hd=SHA.test(d.head||"")?d.head:null;
 const drift=liveHead&&SHA.test(liveHead)&&hd&&liveHead!==hd;
 const primary=d.manuals.length,current=d.automations.filter(x=>x.kind==="source_support");
 const active=current.filter(x=>x.enabled===true).length;
 const tasks=Array.isArray(d.tasks)?d.tasks:[];
 const integrated=tasks.filter(x=>/^INTEGRATED/.test(String(x.stage||"")));
 const prepared=tasks.filter(x=>String(x.stage||"").includes("PREPARED"));
 const accepted=tasks.filter(x=>x.qa_accepted===true&&x.qa_head===hd&&x.qa_reviewer==="manual-2"&&SHA.test(x.qa_blob||""));
 const stats=d.errors||{};
 if(drift){warnings.push("ДАННЫЕ УСТАРЕЛИ: HEAD на источнике изменился.");actions.push({owner:"T02",task:"Обновить источник данных и сохранить фактический SHA; не переносить предыдущие QA_PASS.",priority:0});}
 if(d.source_ready!==true){warnings.push("SOURCE_READY пока не подтверждён.");}
 if(stats.history_complete!==true){warnings.push("Общий реестр ошибок неполон; нельзя объявить окончательный процент.");}
 if(stats.OPEN>0){actions.push({owner:"Ручной №1",task:"Закрыть P0 исходные блокировки с точным PRE/POST и защитными тестами.",priority:1});}
 if(integrated.length>accepted.length){actions.push({owner:"Ручной №2",task:"Проверить интегрированные исходники на одном frozen HEAD и выдать независимые QA-квитанции.",priority:0});}
 if(prepared.length){actions.push({owner:"Ручной №3 → №1",task:"Передать готовые P04/P05 owner-патчи для единой интеграции по CAS/readback.",priority:2});}
 const last=d.last_t02_journal||{};
 if(String(last.e06||"").includes("FAILED_PRECONDITION")||String(last.e06||"").includes("BLOCKED")){
  warnings.push("E06 остаётся заблокированным; синхронизация журнала неполная.");
  actions.push({owner:"T02",task:"Сверить актуальную ревизию E06, сохранить CAS/readback либо выдать точную блокировку.",priority:1});
 }
 if(runData&&Array.isArray(runData.tasks)){
  const failed=runData.tasks.filter(x=>x.last_run?.status==="failed"&&x.enabled);
  if(failed.length){
   warnings.push("Наблюдается "+failed.length+" неуспешных последних запусков среди включённых AUTO.");
   actions.push({owner:"T02",task:"Сверить failed-run с сохранённым Git SHA; не переисполнять уже применённые патчи.",priority:1});
  }
 }
 actions.sort((a,b)=>a.priority-b.priority);
 if(hd)evidence.push({name:"Git HEAD в текущем снимке",value:hd});
 evidence.push({name:"Основные ручные",value:primary},{name:"Актуальные AUTO",value:current.length},{name:"Включены AUTO",value:active});
 return{schema:"NOX_R34_FREE_DIAGNOSTIC_V1",mode:"FREE_LOCAL_READ_ONLY",source_head:hd,source_stale:!!drift,
  product_percent:null,qa_accepted_proven:accepted.length,integrated_candidates:integrated.length,
  warnings,actions:actions.slice(0,6),evidence,eta:"Н/Д",
  disclaimer:"Алгоритмическая диагностика, не вывод OpenAI-модели. Принятые TaskID требуют независимой QA. Никаких изменений кода или разрешений."};
}
function narrative(report){
 const a=report.actions.map((x,i)=>(i+1)+". "+x.owner+": "+x.task).join("\n");
 return"NOX HELION · БЕСПЛАТНЫЙ АНАЛИЗ\n\n"+(report.warnings.length?report.warnings.join("\n"):"Критических предупреждений по предоставленному срезу нет.")+
 "\n\nПРИОРИТЕТНЫЕ ДЕЙСТВИЯ:\n"+(a||"Нет новых обоснованных действий.")+
 "\n\nФАКТЫ: "+report.evidence.map(x=>x.name+" — "+x.value).join("; ")+
 "\nQA_ACCEPTED доказано: "+report.qa_accepted_proven+"; интегрированных кандидатов: "+report.integrated_candidates+
 "\nГотовность продукта/ETA: Н/Д. Данные могут устареть при смене SHA.";
}
return{analyze,narrative};
});