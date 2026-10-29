"use strict";
(function(){
 const q=id=>document.getElementById(id);
 const CSS=".nox-free-r34{margin:24px 0;padding:20px 23px;background:linear-gradient(125deg,#311f14d9,#090e11f4 52%,#111a1be9);border:1px solid #d4aa7f61;border-left:3px solid #e5c58d;border-radius:4px;color:#e9decf;box-shadow:0 20px 45px #0009}.nox-free-r34 h2{font-weight:400;font-size:clamp(19px,2.1vw,27px);letter-spacing:.12em;margin:9px 0}.nox-free-r34 .free-status{display:inline-flex;align-items:center;gap:8px;font-size:10px;color:#b2d2c2;letter-spacing:.12em}.nox-free-r34 .free-led{width:7px;height:7px;border-radius:50%;background:#8ad7ab;box-shadow:0 0 9px #96e6bc}.nox-free-r34 .free-layout{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:19px;align-items:start}.nox-free-r34 pre{white-space:pre-wrap;word-break:break-word;line-height:1.65;color:#d9d7cb;font:11px/1.65 'Segoe UI',sans-serif;margin:14px 0 0;padding:16px;background:#080d10b9;border:1px solid #c79a6345;min-height:84px;max-height:390px;overflow:auto}.nox-free-r34 button{border:1px solid #e6bf8c;background:#64462cbd;color:#f3dabb;padding:11px 16px;border-radius:3px;cursor:pointer;white-space:nowrap}.nox-free-r34 .free-foot{font-size:10px;color:#b9b5ae;margin-top:13px}.nox-free-r34 .free-foot a{color:#e4bb88}@media(max-width:640px){.nox-free-r34 .free-layout{grid-template-columns:1fr}.nox-free-r34 button{width:max-content}}";
 function mount(){
  const host=q("tab-reports")||q("tab-overview");if(!host||q("nox-free-r34"))return;
  const css=document.createElement("style");css.textContent=CSS;document.head.appendChild(css);
  const section=document.createElement("section");section.id="nox-free-r34";section.className="nox-free-r34";
  section.innerHTML='<div class="eyebrow">NOX HELION · ZERO-COST LOCAL INTELLIGENCE</div><div class="free-layout"><div><h2>БЕСПЛАТНАЯ ДИАГНОСТИКА</h2><span class="free-status"><i class="free-led"></i>ЛОКАЛЬНЫЙ АЛГОРИТМ · 0 € · БЕЗ API</span><p style="font-size:11px;color:#aebbb8;line-height:1.5">Работает офлайн, на загруженных доказательствах. Проверяет блокировки, приёмку и разрывы доставки.</p></div><button id="nox-free-r34-analyze" type="button">◈ Проанализировать</button></div><pre id="nox-free-r34-result" aria-live="polite">Данные готовы к проверке. Не требуется OpenAI API, токен или GPU.</pre><div class="free-foot">Не изменяет PR, общий журнал или STATUS. <a href="https://github.com/MSSTXNEWS/nox-helion-pp-private-build/issues/177" target="_blank" rel="noopener">Сверить квитанции GitHub</a></div>';
  host.insertBefore(section,host.firstChild);
  const button=q("nox-free-r34-analyze");
  button.addEventListener("click",()=>{
    const engine=window.NOX_FREE_DIAGNOSTICS,box=q("nox-free-r34-result");
    if(!engine){box.textContent="Модуль бесплатной диагностики не загружен. Никаких фиктивных результатов.";return}
    try{
      const d=window.NOX_CONTROL_DATA||{},s=window.NOX_SCHEDULE_SNAPSHOT||{};
      const report=engine.analyze(d,{runData:s});
      box.textContent=engine.narrative(report);
    }catch(e){box.textContent="Доказательства недостаточны: "+String(e.message||"ошибка проверки")+". Прогресс и QA не изменены."}
  });
  button.click();
 }
 if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",mount,{once:true});else mount();
})();