/* Optional NOX WOW5 view. No network, SDK, host privileges or background work. */
(function (scope, factory) {
  const make = factory(scope.NoxWow5Core || (typeof module === "object" ? require("./wow-core.js") : null));
  if (typeof module === "object" && module.exports) module.exports = make;
  else scope.createNoxWow5 = make;
})(typeof globalThis !== "undefined" ? globalThis : this, function (Core) {
  "use strict";
  if (!Core) throw Error("WOW5_CORE_REQUIRED");
  function make(tag, klass, label) {
    const node = document.createElement(tag);
    if (klass) node.className = klass;
    if (label !== undefined) node.textContent = label;
    return node;
  }
  function mount(options) {
    const parent = options && options.root;
    if (!parent || parent.nodeType !== 1) throw Error("WOW5_MOUNT_ROOT_REQUIRED");
    const ids = Core.allowedIds(options.coreIds);
    const store = options.storage || {getItem(){return null;},setItem(){}};
    const session = Core.restoreView(store, ids, Date.now());
    let focus = session.focus, panel = session.panel, lastRun = null, lastSeq = -1;
    const view = make("aside", "nox-w5" + (focus ? " nox-w5-focus" : ""));
    view.setAttribute("aria-label", "NOX: источники, события и диагностика");
    const head = make("header", "nox-w5-head");
    const title = make("strong", "", "NOX · LENS");
    const signal = make("small", "nox-w5-muted", "Run: Н/Д");
    head.append(title, signal);
    const evidence = make("details", "nox-w5-card");
    const evidenceTitle = make("summary", "", "EVIDENCE STACK · 0");
    const citationList = make("ul", "nox-w5-list");
    evidence.append(evidenceTitle, citationList);
    const timeline = make("section", "nox-w5-card");
    const timelineTitle = make("h3", "", "MISSION TRAIL");
    const history = make("ol", "nox-w5-list");
    history.append(make("li", "nox-w5-muted", "Подтверждённых новых событий нет"));
    timeline.append(timelineTitle, history);
    const tools = make("section", "nox-w5-card nox-w5-tools");
    const focusButton = make("button", "nox-w5-button", focus ? "Вернуть обычный вид" : "Cinema Focus");
    focusButton.type = "button";
    focusButton.setAttribute("aria-pressed", String(focus));
    const panelSelect = make("select", "nox-w5-select");
    panelSelect.setAttribute("aria-label", "Восстановить безопасный выбор панели");
    const startOption = make("option", "", "Панель не выбрана");
    startOption.value = "";
    panelSelect.append(startOption);
    for (const id of ids) {const option = make("option", "", id);option.value=id;panelSelect.append(option);}
    panelSelect.value = panel || "";
    const sessionInfo = make("small","nox-w5-muted","Запоминаются только выбранная панель и режим отображения");
    tools.append(focusButton, panelSelect, sessionInfo);
    const error = make("section", "nox-w5-card");
    error.hidden = true;
    const errorTitle = make("h3", "", "ERROR DECODER");
    const errorReason = make("p", "");
    const errorCode = make("code","nox-w5-muted");
    const copyButton = make("button", "nox-w5-button","Копировать код и RunID");
    copyButton.type="button";
    copyButton.disabled = typeof options.copyText !== "function";
    error.append(errorTitle,errorCode,errorReason,copyButton);
    view.append(head,evidence,timeline,tools,error);
    parent.append(view);
    const persist = () => Core.storeView(store,ids,panel,focus,Date.now());
    focusButton.addEventListener("click", () => {
      focus=!focus;view.classList.toggle("nox-w5-focus",focus);
      focusButton.textContent=focus?"Вернуть обычный вид":"Cinema Focus";
      focusButton.setAttribute("aria-pressed",String(focus));
      persist();
      if (typeof options.onFocusChange==="function") options.onFocusChange(focus);
    });
    panelSelect.addEventListener("change",()=>{
      const next=panelSelect.value;
      panel=ids.includes(next)?next:null;
      persist();
      if (panel && typeof options.onPanelSelected==="function") options.onPanelSelected(panel);
    });
    let currentDiagnostic=null;
    copyButton.addEventListener("click",()=>{
      if (currentDiagnostic && typeof options.copyText==="function")
        options.copyText(currentDiagnostic.code+" | "+currentDiagnostic.runId);
    });
    const actionTitles=Object.freeze({
      "task.started":"Запуск операции", "task.progress":"Изменение состояния",
      "task.completed":"Операция завершена", "task.failed":"Сообщение об ошибке",
      "training.step":"Шаг обучения", "checkpoint.saved":"Сохранение checkpoint",
      "gpu.sample":"Снимок GPU", "rag.indexed":"Индексация RAG",
      "rag.search":"Поиск RAG"
    });
    return Object.freeze({
      setCitations(data) {
        const entries=Core.normalizedCitations(data);
        citationList.replaceChildren();
        for(const item of entries) {
          const li=make("li","nox-w5-source");
          const name=make("span","",item.title);
          const sha=make("code","nox-w5-muted",item.sha.slice(0,12));
          li.append(name,sha);
          if(typeof options.copyText==="function") {
            const button=make("button","nox-w5-mini","Копировать ID");
            button.type="button";
            button.addEventListener("click",()=>options.copyText(item.id+"#"+item.sha));
            li.append(button);
          }
          citationList.append(li);
        }
        if(!entries.length)citationList.append(make("li","nox-w5-muted","Нет подтверждённых источников для отображения"));
        evidenceTitle.textContent="EVIDENCE STACK · "+entries.length;
      },
      acceptEvent(payload) {
        const event=Core.normalizeEvent(payload,Date.now());
        if(!event)return false;
        if(event.runId!==lastRun){lastRun=event.runId;lastSeq=-1;history.replaceChildren();}
        if(event.seq<=lastSeq)return false;
        lastSeq=event.seq;
        signal.textContent="Run: "+event.runId.slice(0,24);
        const li=make("li","",""+(actionTitles[event.type]||"Событие системы")+" · "+event.state);
        const time=make("small","nox-w5-muted",event.at);
        li.append(time);
        history.prepend(li);
        while(history.children.length>6)history.lastElementChild.remove();
        return true;
      },
      setError(code, runId) {
        const item=Core.diagnostic(code,runId);
        currentDiagnostic=item;
        error.hidden=!item;
        errorCode.textContent=item?item.code+" · "+item.runId:"";
        errorReason.textContent=item?item.hint:"";
        return Boolean(item);
      },
      clearError(){currentDiagnostic=null;error.hidden=true;errorCode.textContent="";errorReason.textContent="";},
      destroy(){view.remove();},
      getState(){return {focus,panel};}
    });
  }
  return mount;
});
