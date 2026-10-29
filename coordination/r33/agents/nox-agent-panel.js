/* NOX R33 · D02 OpenAI Agents SDK insights; user-initiated, never auto-paid. */
(function(){
"use strict";
const D=window.NOX_CONTROL_DATA||{},q=id=>document.getElementById(id);
const css=".nox-agent-r33{margin:26px 0;background:linear-gradient(125deg,#322117eb,#081013f5);border:1px solid #d0ae7854;border-left:3px solid #e5bd83;border-radius:5px;padding:19px 22px;box-shadow:0 20px 55px #0009;color:#ebd7ba}.nox-agent-r33 h2{letter-spacing:.13em;font-size:19px;font-weight:400;margin:10px 0}.nox-agent-r33 p{font-size:11px;color:#a5b7b3;line-height:1.6}.nox-agent-r33 .status{color:#e6bb7c;font-size:10px;letter-spacing:.12em}.nox-agent-layout{display:grid;grid-template-columns:110px minmax(0,1fr);gap:21px;align-items:center}.nox-agent-sun{width:100px;height:100px;border-radius:50%;background:radial-gradient(circle at 41% 35%,#111a19,#000 67%);box-shadow:0 0 6px 5px #e0aa705c,0 0 34px #e9b97942;animation:nox-observer-pulse 9s ease-in-out infinite}.nox-agent-output{background:#080d11c9;border:1px solid #b59b734b;padding:13px;font-size:11px;line-height:1.65;white-space:pre-wrap;min-height:62px;max-height:230px;overflow:auto}.nox-agent-btn{cursor:pointer;padding:11px 15px;border:1px solid #e0b57c;background:#59402fba;color:#f4ddbd;font-size:11px}.nox-agent-btn:disabled{opacity:.42;cursor:not-allowed}@keyframes nox-observer-pulse{50%{box-shadow:0 0 8px 7px #e6c09d83,0 0 51px #d6a86b64}}@media(max-width:500px){.nox-agent-layout{grid-template-columns:1fr}.nox-agent-sun{margin:auto}}@media(prefers-reduced-motion:reduce){.nox-agent-sun{animation:none!important}}";
function mounted(){
 const pane=q("tab-reports")||q("tab-overview");if(!pane||q("nox-agent-r33"))return;
 const style=document.createElement("style");style.textContent=css;document.head.append(style);
 const section=document.createElement("section");section.id="nox-agent-r33";section.className="nox-agent-r33";
 section.innerHTML='<div class="eyebrow">NOX HELION / OPENAI AGENTS SDK · R33</div><h2>ИНТЕЛЛЕКТУАЛЬНЫЙ КОНТРОЛЬ</h2><p>Дополнительная аналитика по фактическим ОТЧ-1 и реестру. Без прав на Git, QA, сборку или удаление данных.</p><div class="nox-agent-layout"><div class="nox-agent-sun" aria-hidden="true"></div><div><div class="status" id="nox-agent-status">ПРОВЕРКА ЗАЩИЩЁННОГО API</div><div class="nox-agent-output" id="nox-agent-output" aria-live="polite">Контроль работает локально. OpenAI-модель доступна только после настройки серверного ключа и лимитов расходов.</div><button type="button" class="nox-agent-btn" disabled id="nox-agent-button">◈ Запросить AI-анализ</button></div></div><p>Платные вызовы не выполняются автоматически при открытии сайта. Передаются лишь агрегированные числа; оригинальные паспорта, код и токены не отправляются.</p>';
 pane.append(section);q("nox-agent-button").addEventListener("click",run);check();
}
function evidence(){
 const cur=(D.automations||[]).filter(x=>x.kind==="source_support"&&x.enabled===true);
 const err=D.errors||{};
 return {head:D.head,manuals:(D.manuals||[]).length,automations:cur.length,errors:Number.isInteger(err.OPEN)?err.OPEN:0,accepted:0,source_ready:false,journal_sync:"UNVERIFIED",last_run_at:D.observed_at||null,task_ids:(D.tasks||[]).slice(0,24).map(x=>x.id).filter(Boolean)};
}
async function check(){
 const status=q("nox-agent-status"),out=q("nox-agent-output");
 if(location.protocol==="file:"){status.textContent="ЛОКАЛЬНЫЙ ПРОСМОТР · БЕЗ SDK";return}
 try{
  const r=await fetch("/api/agent-insights",{method:"GET",credentials:"same-origin",cache:"no-store"});
  if(!r.ok)throw Error("HTTP "+r.status);
  const z=await r.json();if(z.configured!==true){status.textContent="SDK · ТРЕБУЕТ НАСТРОЙКИ";out.textContent="Не настроен серверный OpenAI API-ключ, модель или проверенный бюджет. Исторический ОТЧ-1 продолжает работать без ИИ.";return}
  status.textContent="SDK READY · READ ONLY";out.textContent="Подключение подтверждено. Запросите один контролируемый AI-анализ.";q("nox-agent-button").disabled=false;
 }catch{status.textContent="ОФЛАЙН · API НЕ ПОДТВЕРЖДЁН";out.textContent="Надёжный локальный режим активен. Состояние модели не влияет на исходники, QA или метрики."; }
}
async function run(){
 const button=q("nox-agent-button"),out=q("nox-agent-output"),status=q("nox-agent-status");
 if(!/^[0-9a-f]{40}$/.test(String(D.head)))return;
 button.disabled=true;out.textContent="Выполняю read-only анализ…";
 const c=new AbortController(),timer=setTimeout(()=>c.abort(),18000);
 try{
  const r=await fetch("/api/agent-insights",{method:"POST",credentials:"same-origin",cache:"no-store",headers:{"Content-Type":"application/json"},body:JSON.stringify(evidence()),signal:c.signal});
  const z=await r.json();
  if(!r.ok||!z.ok){out.textContent="Нет вызова модели: "+String(z.reason||z.error||"не настроено")+". Контроль продолжает работу.";status.textContent="SDK BLOCKED";return}
  out.textContent=String(z.analysis||"Нет подтверждённых выводов").slice(0,3500);status.textContent="SDK · АНАЛИЗ ГОТОВ";
 }catch(err){out.textContent="Защищённый агент недоступен: "+String(err.message||"ошибка связи");status.textContent="NO MODEL RESULT";}
 finally{clearTimeout(timer);button.disabled=false;}
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",mounted,{once:true});else mounted();
})();