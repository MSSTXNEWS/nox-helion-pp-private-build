import {CATEGORIES,verifyCatalog,normalizeCapabilities,filteredActions,optionsForField,makeRequest} from "./registry.mjs";
import {mountCinematic} from "./cinema50.mjs";
/* NOX 50-route secondary-screen card interface.
 * No direct Ollama/SIP/PC/network access. All operations require native-host attestation.
 */
const stateLabels=Object.freeze({HOLD:"Не подключено",AVAILABLE:"Обнаружено",CONNECTED:"Подключено",VERIFIED:"Проверено"});
function el(tag,klass,text){
  const node=document.createElement(tag);
  if(klass)node.className=klass;
  if(text!==undefined)node.textContent=String(text);
  return node;
}
export function mountPack(target,{catalog,bridge}={}){
  if(typeof document==="undefined"||!target||target.nodeType!==1)throw Error("NOX_PACK_DOM_REQUIRED");
  if(target.closest('[data-nox-page="home"]')||target.dataset.noxPage==="home")throw Error("NO_PACK_ON_D02_HOME");
  if(!bridge||typeof bridge.dispatch!=="function")throw Error("TRUSTED_NOX_HOST_REQUIRED");
  verifyCatalog(catalog);
  let destroyed=false,category="all",query="",selected=null,capabilities=normalizeCapabilities(catalog,{}),choices={},inFlight=false;
  const root=el("section","nox-pack01");root.setAttribute("aria-label","NOX · Каталог функций");
  const header=el("header","nox-pack01__head");
  const title=el("strong","","NOX · ФУНКЦИИ 01/50");
  const search=el("input","nox-pack01__search");
  search.type="search";search.setAttribute("aria-label","Поиск функций");search.placeholder="Поиск функции · Ctrl+K";
  const count=el("output","nox-pack01__count","50 функций");
  header.append(title,search,count);
  const tabs=el("nav","nox-pack01__tabs");tabs.setAttribute("aria-label","Группы функций");
  const grid=el("div","nox-pack01__grid");
  const settings=el("section","nox-pack01__detail");settings.setAttribute("aria-label","Параметры функции");settings.hidden=true;
  const feedback=el("output","nox-pack01__feedback","Реальные функции активируются только после подключения к NOX");
  feedback.setAttribute("aria-live","polite");
  root.append(header,tabs,grid,settings,feedback);target.append(root);
  const cinematic=mountCinematic(root,catalog);
  function setFeedback(text){feedback.textContent=String(text).slice(0,240);}
  function drawTabs(){
    tabs.replaceChildren();
    for(const c of ["all",...CATEGORIES]){
      const b=el("button","nox-pack01__tab",c==="all"?"Все":c);
      b.type="button";b.setAttribute("aria-pressed",String(category===c));
      b.onclick=()=>{category=c;selected=null;draw();};tabs.append(b);
    }
  }
  function drawDetail(){
    settings.replaceChildren();
    if(!selected){settings.hidden=true;return;}
    settings.hidden=false;
    const x=selected,cap=capabilities[x.routeId];
    const name=el("h3","",x.title);
    const about=el("p","","Блок №"+x.owner+" · "+x.routeId+" · "+stateLabels[cap.state]);
    const form=el("form","nox-pack01__form");
    const inputs={};
    for(const field of x.settings){
      const label=el("label","nox-pack01__field");
      label.append(el("span","",field.label));
      const select=el("select");select.name=field.key;
      const opts=optionsForField(field,choices);
      if(!opts.length){
        const option=el("option","","Не установлено / нет данных");
        option.value="";select.append(option);select.disabled=true;
      }else{
        for(const [v,txt] of opts){const option=el("option","",txt);option.value=v;select.append(option);}
      }
      inputs[field.key]=select;label.append(select);form.append(label);
    }
    const run=el("button","nox-pack01__run",cap.enabled?"Выполнить в NOX":"Ожидает подключения");
    run.type="submit";run.disabled=!cap.enabled||x.settings.some(f=>inputs[f.key].disabled);
    const close=el("button","nox-pack01__close","Закрыть");
    close.type="button";close.onclick=()=>{selected=null;drawDetail();};
    form.append(run,close);
    form.onsubmit=async(event)=>{
      event.preventDefault();
      if(inFlight||destroyed||!capabilities[x.routeId].enabled)return;
      let request;
      try{
        request=makeRequest(x,Object.fromEntries(Object.entries(inputs).map(([k,n])=>[k,n.value])),choices);
      }catch(e){setFeedback("Параметры не готовы: "+e.message);return;}
      inFlight=true;run.disabled=true;setFeedback("Команда передана защищённому локальному NOX");
      try{
        // The native host MUST independently validate route, current user permissions,
        // per-action consent and real backend availability. UI approval is not authorization.
        const response=await bridge.dispatch("nox.feature.request",request);
        if(!destroyed){
          if(response?.accepted===true&&typeof response?.receiptId==="string")
            setFeedback("NOX подтвердил приём · "+response.receiptId.slice(0,96));
          else setFeedback("NOX не подтвердил выполнение · HOLD");
        }
      }catch{
        if(!destroyed)setFeedback("Ошибка или запрет локального NOX · HOLD");
      }finally{inFlight=false;if(!destroyed)drawDetail();}
    };
    settings.append(name,about,form);
  }
  function draw(){
    drawTabs();grid.replaceChildren();
    const actions=filteredActions(catalog,query,category);
    count.textContent=actions.length+" из 50";
    for(const x of actions){
      const cap=capabilities[x.routeId];
      const button=el("button","nox-pack01__tile");
      button.type="button";button.dataset.state=cap.state;button.dataset.risk=x.risk;button.dataset.routeId=x.routeId;
      button.setAttribute("aria-label",x.title+" · "+stateLabels[cap.state]);
      const name=el("span","nox-pack01__title",x.title);
      const status=el("span","nox-pack01__status",stateLabels[cap.state]);
      const id=el("small","",x.taskId);
      button.append(name,status,id);
      // Unavailable cards only display real requirements; execution remains disabled.
      button.onclick=()=>{selected=x;drawDetail();};
      grid.append(button);
    }
    drawDetail();
    cinematic.decorate();
  }
  search.oninput=()=>{query=search.value.slice(0,96);selected=null;draw();};
  const onKey=(e)=>{
    if(destroyed||e.key?.toLowerCase()!=="k"||!e.ctrlKey||e.altKey||e.metaKey)return;
    // Do not steal Ctrl+K from HOME, another route, or a hidden secondary page.
    if(!root.isConnected || !root.getClientRects().length ||
       document.querySelector('[data-nox-page="home"]')?.contains(root))return;
    e.preventDefault();search.focus();search.select();
  };
  document.addEventListener("keydown",onKey);
  draw();
  return Object.freeze({
    setCapabilities(raw){if(destroyed)return;capabilities=normalizeCapabilities(catalog,raw);draw();},
    setHostChoices(raw){if(destroyed)return;choices=raw&&typeof raw==="object"?raw:{};drawDetail();},
    search(text){if(destroyed)return;query=String(text||"").slice(0,96);search.value=query;draw();},
    setCinemaMode(mode){if(destroyed)return false;return cinematic.setMode(mode);},
    applyNativeVisualEvent(event){if(destroyed)return false;return cinematic.applyNativeEvent(event);},
    getStats(){return {total:50,advertised:Object.values(capabilities).filter(x=>x.enabled).length,
      notConnected:Object.values(capabilities).filter(x=>!x.enabled).length};},
    destroy(){if(destroyed)return;destroyed=true;document.removeEventListener("keydown",onKey);cinematic.destroy();root.remove();}
  });
}
