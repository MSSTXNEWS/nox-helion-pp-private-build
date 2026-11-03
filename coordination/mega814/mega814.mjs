/* NOX MEGA 08–14 · owner overlay on original #menu/#control only.
 * Original 8 MENU controls, HOME, portraits, source archive untouched.
 * Real native capabilities MUST be supplied by E06 trusted host. Otherwise HOLD.
 */
import {createP01RouteDispatcher} from "./owner-dispatch.mjs";
import {validateMenuV2,appendMenuV2} from "./menu-v2-adapter.mjs";
import {projectSpaceView} from "./owner-e05.mjs";
import {createNativeReadOnlyPort} from "./native-readonly.mjs";
import {createNativeMenuClient} from "../../ui/onehost-menu-bindings.mjs";
const validId=x=>typeof x==="string"&&/^[a-zA-Z0-9._:-]{1,128}$/.test(x);
const unique=x=>new Set(x).size===x.length;
const hex=x=>typeof x==="string"&&/^[0-9a-f]{64}$/.test(x);
const node=(tag,label,cls)=>{const n=document.createElement(tag);if(label!==undefined)n.textContent=label;if(cls)n.className=cls;return n};
export function validateMega(s){
 const routes=Object.values(s?.legacyRouteGroups||{}).flat();
 if(s?.schema!=="NOX-MEGA814-V16-OWNER-SOURCE-v1"||
    routes.length!==54||!unique(routes)||!routes.every(validId)||
    s.worlds?.length!==10||s.workViews?.length!==8||s.coreIds?.length!==8||
    s.personas?.length!==5||!unique(s.coreIds)||!unique(s.worlds.map(x=>x.id))||
    !unique(s.personas.map(x=>x.id))||!hex(s.asset.menu10SHA256)||!hex(s.asset.menuReferenceSHA256)||s.asset.menu10SHA256===s.asset.menuReferenceSHA256||
    s.personas.find(x=>x.id==="EV")?.status!=="IDENTITY_CONFLICT_HOLD"||
    Object.values(s.criteria||{}).reduce((a,b)=>a+b.length,0)!==30||
    s.worlds.some(w=>w.legacyIndex<0||w.legacyIndex>7||w.routes.some(r=>!routes.includes(r))))
   throw Error("NOX_MEGA814_OWNER_TOPOLOGY_HOLD");
 return Object.freeze({worlds:10,work:8,personas:5,legacyRoutes:54,criteria:30});
}
async function hashBuffer(bytes) {
 const result=await crypto.subtle.digest("SHA-256",bytes);
 return Array.from(new Uint8Array(result)).map(x=>x.toString(16).padStart(2,"0")).join("");
}
async function approvedImage(img,path,sha,mark){
 try{
  const r=await fetch(path,{cache:"no-store",credentials:"same-origin"});
  if(!r.ok||r.type==="opaque")return false;
  const data=await r.arrayBuffer();
  if(data.byteLength<100||data.byteLength>12000000||await hashBuffer(data)!==sha)return false;
  const url=URL.createObjectURL(new Blob([data],{type:"image/png"}));
  img.onload=()=>URL.revokeObjectURL(url);img.onerror=()=>URL.revokeObjectURL(url);
  img.src=url;img.hidden=false;
  mark.textContent="SOURCE IMAGE SHA VERIFIED · видео/визуальная E07 HOLD";
  return true;
 }catch{return false}
}
function note(root,message){const el=node("p",message,"mega814-note");el.setAttribute("role","status");root.append(el);return el}
function legacy(index){
 const target=document.querySelector('#tiles [data-menu-index="'+index+'"]');
 if(target&&!target.disabled){target.click();return true}return false;
}
function openExistingScreen(route) {
 const screen=({chat:"chat","core-status":"core",spaces:"space"})[route];
 if(!screen)return false;
 const target=document.querySelector('.nav [data-screen="'+screen+'"]');
 if(!target||!document.getElementById(screen)?.classList.contains("screen"))return false;
 target.click();
 return document.getElementById(screen).classList.contains("active");
}
function safeRoute(route,probe,label=route,aiClient=null,payload={},parentIndex=null){
 const line=node("div",undefined,"mega814-action");
 const button=node("button",label,"mega814-button");
 const status=node("small","HOLD · не подтверждён native handler");
 button.type="button";button.disabled=true;
 const viewAvailable=["chat","core-status","spaces"].includes(route);
 if(viewAvailable){
   button.disabled=false;
   status.textContent="Доступный исходный экран; функция backend отдельно";
   button.addEventListener("click",()=>{
     status.textContent=openExistingScreen(route)?
       "Открыт существующий экран · backend требует отдельной QA":
       "HOLD · исходный экран недоступен";
   });
 }
 if(route==="nox.parent-navigation"){
  button.disabled=!Number.isInteger(parentIndex)||parentIndex<0||parentIndex>7;
  status.textContent=button.disabled?"HOLD · исходный раздел недоступен":
    "Переход в исходный родительский раздел; отдельное действие проверяется отдельно";
  button.addEventListener("click",()=>{
   if(button.disabled)return;
   const opened=legacy(parentIndex);
   status.textContent=opened?
    "Открыт исходный раздел · конкретная функция не подтверждена E07":
    "HOLD · исходный раздел не открылся";
  });
 }
 if(route==="helion.chat"&&aiClient){
  button.disabled=false;button.textContent=label||"СПРОСИТЬ NOX";
  status.textContent="Готово к отправке в существующий AI / OneHost канал";
  const answer=node("pre",undefined,"mega814-ai-answer");answer.hidden=true;
  button.addEventListener("click",async()=>{
   if(button.dataset.pending==="true")return;
   button.dataset.pending="true";button.disabled=true;
   status.textContent="NOX AI · запрос отправлен · ожидание native-ответа";
   answer.hidden=true;answer.textContent="";
   try{
    const reply=await aiClient.request("helion.chat",payload);
    if(reply?.routeId==="helion.chat"&&reply.state==="COMPLETED"){
     const value=reply.result;
     const rendered=typeof value?.answer==="string"?value.answer:
      typeof value?.text==="string"?value.text:JSON.stringify(value,null,2);
     answer.textContent=String(rendered||"AI ответил без текстового содержимого").slice(0,12000);
     answer.hidden=false;
     status.textContent="AI-ответ получен · выполнение запрошенной операции отдельно не подтверждено";
    }else status.textContent="HOLD · "+String(reply?.errorCode||"NOX_AI_NATIVE_HOLD");
   }catch(error){
    status.textContent="HOLD · "+(error&&/^[A-Z0-9_]{1,80}$/.test(error.message)?error.message:"NOX_AI_REQUEST_FAILED");
   }finally{delete button.dataset.pending;button.disabled=false}
  });
  line.append(answer);
 }
 if(route==="model-library"&&probe?.available===true){
   button.disabled=false;
   button.textContent="ПРОВЕРИТЬ ЛОКАЛЬНЫЕ МОДЕЛИ";
   status.textContent="Native P02 · chat.model · ещё не проверено";
   button.addEventListener("click",async()=>{
     button.disabled=true;status.textContent="Запрос через E06 NativeIngress";
     try{
       const answer=await probe.request("chat.model",{});
       status.textContent=answer.ok===true&&Array.isArray(answer.value?.models)?
          "Native P02 · моделей: "+answer.value.models.length+" · E07 HOLD":
          "HOLD · "+answer.reason;
     }finally{button.disabled=false}
   });
 }
 line.append(button,status);return line;
}
/* OWNER MENU V2: the TEN original pictured asteroid objects ARE buttons.
   Never draw a second navigation bar or replace approved PNG pixels. */
function menuWorlds(menu,s,probe,menuV2,aiClient){
 const panel=node("section",undefined,"mega814-menu-scene");
 panel.id="nox-mega814-menu";
 const scene=node("div",undefined,"mega814-spatial");scene.hidden=true;
 const art=document.createElement("img");art.hidden=true;
 art.alt="Утверждённое MENU10 NOX HELION с десятью отдельными кнопками-мирaми";
 art.draggable=false;scene.append(art);
 const legacyPanel=menu.querySelector("#tiles")?.closest(".panel");
 const fallback=node("div",undefined,"mega814-mobile-worlds");
 fallback.setAttribute("aria-label","Кнопки десяти миров");
 const detail=node("section",undefined,"mega814-world-detail");detail.hidden=true;
 detail.setAttribute("aria-live","polite");
 const heading=node("h2",undefined,"mega814-world-name");
 const controls=node("div",undefined,"mega814-options");
 detail.append(heading,controls);
 const positions=Object.freeze({
  work:[47.3,12.5],intelligence:[29.1,20.1],knowledge:[19.1,37.2],
  learning:[20.1,56.5],entertainment:[33.7,76.6],
  people:[56.3,81.9],creative:[73.1,74.5],business:[82.1,55.2],
  world:[79.7,33.4],pc:[66.7,16]
 });
 const controlsFor=new Map();
 function activate(w){
  detail.hidden=false;heading.textContent=w.label;controls.replaceChildren();
  // First show the canonical world's 193-tree subsections immediately:
  // a second click on a collapsed section is NOT part of the approved MENU.
  appendMenuV2(controls,w,menuV2,(route,label,payload,worldContext)=>safeRoute(
    route,probe,label,aiClient,payload,worldContext?.legacyIndex));
  const originalRoutes=node("section",undefined,"mega814-v2-legacy");
  originalRoutes.append(node("h3","ИСХОДНЫЕ МАРШРУТЫ · "+w.routes.length,"mega814-v2-legacy-title"));
  const open=node("button","ОТКРЫТЬ РОДИТЕЛЬСКИЙ РАЗДЕЛ","mega814-button");
  open.type="button";
  open.addEventListener("click",()=>{if(!legacy(w.legacyIndex))note(controls,"HOLD · исходный раздел не готов")});
  originalRoutes.append(open);
  const routeGrid=node("div",undefined,"mega814-v2-subitems");
  routeGrid.setAttribute("role","group");
  routeGrid.setAttribute("aria-label","Исходные маршруты "+w.label);
  for(const route of w.routes)routeGrid.append(safeRoute(route,probe,route,aiClient,{},w.legacyIndex));
  originalRoutes.append(routeGrid);
  controls.append(originalRoutes);
  for(const [id,buttons] of controlsFor){
   for(const button of buttons)button.setAttribute("aria-pressed",String(id===w.id));
  }
 }
 for(const w of s.worlds){
  const xy=positions[w.id];
  if(!xy)throw Error("MEGA814_ASTEROID_POSITION_MISSING:"+w.id);
  const hit=node("button",undefined,"mega814-asteroid-button");
  hit.type="button";hit.dataset.world=w.id;
  hit.setAttribute("aria-label","Открыть мир "+w.label);
  hit.setAttribute("aria-pressed","false");
  hit.title=w.label;hit.style.left=xy[0]+"%";hit.style.top=xy[1]+"%";
  hit.addEventListener("click",()=>activate(w));scene.append(hit);
  const mobile=node("button",w.label,"mega814-mobile-button");
  mobile.type="button";mobile.setAttribute("aria-pressed","false");
  mobile.addEventListener("click",()=>activate(w));fallback.append(mobile);
  controlsFor.set(w.id,[hit,mobile]);
 }
 const home=node("button",undefined,"mega814-asteroid-button mega814-center-home");
 home.type="button";home.setAttribute("aria-label","Вернуться на HOME к восьми ядрам");
 home.title="HOME";home.style.left="50%";home.style.top="47.2%";
 home.addEventListener("click",()=>{
  const target=document.querySelector('.nav [data-screen="home"]');
  if(target && !target.disabled){detail.hidden=true;target.click();}
  else{detail.hidden=false;heading.textContent="HOME";controls.replaceChildren();
   note(controls,"HOLD · исходный переход HOME недоступен");}
 });
 scene.append(home);
 const msg=note(panel,"MENU10 · проверка утверждённого оригинала");
 art.addEventListener("load",()=>{
  if(art.hidden)return;scene.hidden=false;msg.hidden=true;
  legacyPanel?.classList.add("mega814-legacy-hidden");
 });
 art.addEventListener("error",()=>{
  panel.classList.add("mega814-image-hold");
  msg.textContent="HOLD · MENU10 media недоступно; исходные 10 кнопок доступны без подмены изображения";
 });
 void approvedImage(art,"mega814/menu10.png",s.asset.menu10SHA256,msg).then(ok=>{
  if(!ok){
   panel.classList.add("mega814-image-hold");
   msg.textContent="HOLD · MENU10 SHA/media не подтверждены; доступны кнопки миров";
  }
 });
 panel.append(scene,fallback,detail);
 if(legacyPanel)legacyPanel.after(panel);else menu.append(panel);
 return {destroy(){legacyPanel?.classList.remove("mega814-legacy-hidden");panel.remove()}};
}
function workViews(control,s,store,probe){
 const panel=node("section",undefined,"mega814-panel mega814-work");
 panel.id="nox-mega814-work";
 panel.append(node("h2","РАБОТА · ВОСЕМЬ ПРЕДСТАВЛЕНИЙ"));
 const tabs=node("nav",undefined,"mega814-tabs");
 tabs.setAttribute("aria-label","Вкладки WORK");
 const body=node("div",undefined,"mega814-workbody");
 const states=new Map();
 let selected=s.workViews[0],closed=false;
 function render(){
  if(closed)return;
  body.replaceChildren(node("h3",selected.label));
  const snapshot=store.snapshot;
  const telemetry=store.telemetry;
  const hostStatus=store.hostStatus;
  const observed=node("div",undefined,"mega814-observed");
  if(snapshot){
   const meta=node("small","E05 OWNER-REPORTED · RunID: "+String(snapshot.runId).slice(0,80));
   observed.append(meta);
   if(selected.id==="W01"){
    const state=snapshot.readiness?.reason||"HOLD · частичная готовность";
    observed.append(node("p","Подтверждение задач: "+state));
    observed.append(node("p","Hardware: "+(snapshot.hardware?.state||"Н/Д")));
   }else if(selected.id==="W03"){
    const events=snapshot.events;
    observed.append(node("p","События последней сессии: "+String(events?.state||"Н/Д")));
   }else if(selected.id==="W05"){
    observed.append(node("p","Состав исполнителей: Н/Д (native roster не передан)"));
   }else if(selected.id==="W08"){
    observed.append(node("p","Готовность: "+String(snapshot.readiness?.reason||"N/D")));
    const bars=snapshot.readiness?.bars;
    if(Array.isArray(bars)){
     const grid=node("div",undefined,"mega814-bars");
     for(const item of bars){
      const label=node("div",undefined,"mega814-bar");
      label.append(node("strong","№"+item.executor));
      label.append(node("span",typeof item.percent==="number"?
          String(item.percent)+"% · "+item.stage:"Н/Д · "+item.stage));
      grid.append(label);
     }
     observed.append(grid);
    }
   }else observed.append(node("p","Источник E05 не передал проверенные данные этого представления · HOLD"));
  }else observed.append(node("p","Н/Д · E06 host ledger отсутствует. Никаких выдуманных TaskID/RunID или процентов."));
  body.append(observed);
  if(selected.id==="W01"||selected.id==="W08"||selected.id==="W07"){
    const header=node("div",undefined,"mega814-telemetry");
    header.append(node("h3","ИСХОДНЫЙ WPF · ЖИВАЯ ТЕЛЕМЕТРИЯ"));
    if(telemetry){
      const o=telemetry.ollama;
      const gpu=telemetry.gpu;
      if(o)header.append(node("p","Ollama: "+
          (typeof o.state==="string"?o.state:"Н/Д")+
          (Number.isSafeInteger(o.modelCount)&&o.modelCount>=0?
            " · локальных моделей: "+o.modelCount:"")));
      if(gpu){
        header.append(node("p","GPU: "+String(gpu.name||"Н/Д")));
        if(typeof gpu.utilization==="number"&&Number.isFinite(gpu.utilization)&&
           gpu.utilization>=0&&gpu.utilization<=100)
          header.append(node("p","Загрузка GPU: "+gpu.utilization.toFixed(1)+"%"));
        if(typeof gpu.temperature==="number"&&Number.isFinite(gpu.temperature)&&
           gpu.temperature>=-40&&gpu.temperature<=130)
          header.append(node("p","Температура GPU: "+gpu.temperature.toFixed(1)+" °C"));
        if(typeof gpu.memory==="string"&&gpu.memory.length<90)
          header.append(node("p","VRAM: "+gpu.memory));
      }
      header.append(node("small","Исходный WPF · отметка опроса: "+
          String(telemetry.utc||"Н/Д")+" · не E07"));
    }else header.append(node("p","Н/Д · опрос native-хоста ещё не выполнен"));
    if(hostStatus)header.append(node("p","WebView2: "+
        String(hostStatus.webview2||"Н/Д")+
        " · релиз: "+String(hostStatus.productGate||"HOLD")));
    body.append(header);
    const refresh=node("button","ОБНОВИТЬ РЕАЛЬНЫЕ ДАТЧИКИ","mega814-button");
    refresh.type="button";refresh.disabled=!store.hostReady;
    refresh.addEventListener("click",()=>{store.refresh();});
    body.append(refresh);
  }
  if(selected.legacyIndex!==null){
   const b=node("button","ОТКРЫТЬ ИСХОДНЫЙ РАЗДЕЛ","mega814-button");
   b.type="button";
   b.addEventListener("click",()=>{if(!legacy(selected.legacyIndex))note(body,"HOLD · исходный раздел недоступен")});
   body.append(b);
  }
  if(selected.id==="W07"||selected.id==="W08"){
   const test=node("button","ПРОВЕРИТЬ МОДЕЛИ ЧЕРЕЗ E06","mega814-button");
   test.type="button";test.disabled=!probe.available;
   const state=note(body,probe.available?"Только read-only chat.model · E07 HOLD":"HOLD · NativeIngress не подключён");
   test.addEventListener("click",async()=>{
      test.disabled=true;state.textContent="Native запрос отправлен";
      try{
       const reply=await probe.request("chat.model",{});
       state.textContent=reply.ok===true&&Array.isArray(reply.value?.models)?
        "E06 модельный каталог · "+reply.value.models.length+" моделей · E07 HOLD":
        "HOLD · "+reply.reason;
      }finally{test.disabled=false}
   });
   body.append(test);
   // Reuse the already approved native STOP route; never simulate cancellation.
   const stop=node("button","ЗАПРОСИТЬ STOP ЧЕРЕЗ E06","mega814-button");
   stop.type="button";stop.disabled=!probe.available;
   stop.addEventListener("click",async()=>{
     stop.disabled=true;state.textContent="Native STOP: запрос отправлен";
     try{
       const reply=await probe.request("chat.stop",{});
       state.textContent=reply.ok===true&&reply.stopRequested===true?
         "Native STOP_REQUESTED · окончательная остановка не подтверждена · E07 HOLD":
         "HOLD · "+String(reply.reason||"NATIVE_STOP_UNVERIFIED");
     }finally{stop.disabled=false}
   });
   body.append(stop);
  }
  if(selected.id==="W08"&&!snapshot)note(body,"events.v3: ожидаем E06 owner readback");
 }
 s.workViews.forEach((view,i)=>{
  const tab=node("button",view.label,"mega814-tab");
  tab.type="button";tab.id="mega814-tab-"+view.id;
  tab.setAttribute("role","tab");tab.setAttribute("aria-selected",String(i===0));
  tab.addEventListener("click",()=>{
   selected=view;
   for(const e of tabs.children)e.setAttribute("aria-selected",String(e===tab));
   render();
  });
  tabs.append(tab);
 });
 tabs.setAttribute("role","tablist");
 panel.append(tabs,body);
 control.append(panel);
 const unsubscribe=store.subscribe(render);
 render();
 return {element:panel,destroy(){closed=true;unsubscribe();panel.remove()}};
}
function cast(control,s){
 const zone=node("section",undefined,"mega814-panel mega814-persona");
 zone.append(node("h2","ПЯТЬ ПЕРСОН · ПАСПОРТА / SHA"));
 const grid=node("div",undefined,"mega814-cast");
 for(const p of s.personas){
  const card=node("article",undefined,"mega814-card");
  card.append(node("h3",p.name));
  const state=note(card,p.status==="IDENTITY_CONFLICT_HOLD"?"IDENTITY_CONFLICT_HOLD · лицо запрещено заменять":"SOURCE_NOT_STAGED · VIDEO_HOLD");
  const image=document.createElement("img");image.hidden=true;image.alt=p.name+" · оригинальный паспорт";card.append(image);
  if(p.status!=="IDENTITY_CONFLICT_HOLD")
   void approvedImage(image,"mega814/persona-"+p.id+".png",p.sha256,state);
  grid.append(card);
 }
 zone.append(grid);control.append(zone);return zone;
}
function space(control,store){
 const panel=node("section",undefined,"mega814-panel");
 panel.append(node("h2","NOX SPACE · ИСТОЧНИКИ"));
 const status=note(panel,"Н/Д · погода, новости, MARKET, медиа только из E05/E06");
 function render(){
  const p=store.snapshot;
  if(!p){status.textContent="Н/Д · E05 owner snapshot отсутствует";return}
  const feedNames=Array.isArray(p.feeds)?p.feeds.map(x=>String(x?.sourceId||x?.id||"source").slice(0,40)):[];
  status.textContent="E05 OWNER-REPORTED · "+p.runId+
    " · источников "+feedNames.length+
    " · Hardware "+String(p.hardware?.state||"Н/Д")+" · E07 HOLD";
 }
 control.append(panel);
 const off=store.subscribe(render);render();
 return {element:panel,destroy(){off();panel.remove()}};
}
function createE05ReadOnlyStore(host){
 let closed=false,snapshot=null,telemetry=null,hostStatus=null;
 const listeners=new Set();
 const publish=()=>{for(const notify of listeners){try{notify()}catch{}}};
 const onMessage=event=>{
  if(closed)return;
  const data=event?.data;
  if(data?.kind==="e05OwnerSnapshot"&&data.dto){
   try{
     const projected=projectSpaceView(data.dto,Date.now());
     if(!projected||projected.schema!=="NOX-E05-SPACE-READONLY-v1")return;
     snapshot=projected;publish();
   }catch{/* Never accept malformed ledger or imply E07. */}
  }else if(data?.kind==="telemetry"&&data.result&&typeof data.result==="object"){
   const t=data.result;
   if(typeof t.utc!=="string"||t.utc.length>20)return;
   // Original trusted WPF HandleMessage emits telemetry; no page-side writer.
   telemetry=Object.freeze({
     utc:t.utc,
     ollama:typeof t.ollama==="object"&&t.ollama!==null?
        {state:t.ollama.state,modelCount:t.ollama.modelCount}:null,
     gpu:typeof t.gpu==="object"&&t.gpu!==null?
        {name:t.gpu.name,utilization:t.gpu.utilization,
         temperature:t.gpu.temperature,memory:t.gpu.memory}:null
   });
   publish();
  }else if(data?.kind==="hostStatus"&&typeof data.webview2==="string"){
   hostStatus=Object.freeze({
     webview2:data.webview2,productGate:data.productGate,
     reportGate:data.reportGate
   });publish();
  }
 };
 host?.addEventListener?.("message",onMessage);
 function refresh(){
  if(closed||typeof host?.postMessage!=="function")return false;
  try{
   host.postMessage({action:"refreshTelemetry"});
   host.postMessage({action:"status"});
   host.postMessage({action:"readMainSnapshot"});
   return true;
  }catch{return false}
 }
 return Object.freeze({
   get snapshot(){return snapshot},
   get telemetry(){return telemetry},
   get hostStatus(){return hostStatus},
   get hostReady(){return !closed&&typeof host?.postMessage==="function"},
   refresh,subscribe(fn){if(closed||typeof fn!=="function")return ()=>{};
     listeners.add(fn);return ()=>listeners.delete(fn)},
   close(){closed=true;host?.removeEventListener?.("message",onMessage);
     snapshot=null;telemetry=null;hostStatus=null;listeners.clear()}
 });
}
export function bootstrapMega814(s,menuV2){
 const summary=validateMega(s);
 menuV2=validateMenuV2(menuV2,s.worlds);
 const menu=document.getElementById("menu"),control=document.getElementById("control");
 if(!menu||!control||document.getElementById("nox-mega814-menu"))throw Error("MEGA814_OWNER_PAGE_MISSING");
 // Host-origin messages are only model state, NEVER a page-granted ACL.
 const host=window.chrome?.webview;
 const probe=createNativeReadOnlyPort(host);
 const store=createE05ReadOnlyStore(host);
 const world=menuWorlds(menu,s,probe,menuV2);
 const work=workViews(control,s,store,probe);
 const castPanel=cast(control,s);
 const spacePanel=space(control,store);
 // Read-only status request is an existing original WPF action.
 if(store.hostReady)store.refresh();
 const motionPref=window.matchMedia?.("(prefers-reduced-motion: reduce)");
 const lowPref=window.matchMedia?.("(max-width: 390px), (max-height: 480px)");
 const syncMotion=()=>{
  const klass=document.body.classList;
  const reduce=motionPref?.matches===true||klass.contains("mode-reduce")||
   klass.contains("nox-wow-reduced");
  const eco=lowPref?.matches===true||klass.contains("mode-eco")||klass.contains("nox-wow-eco");
  const max=klass.contains("mode-max")||klass.contains("nox-wow-max");
  document.documentElement.dataset.mega814Motion=reduce?"REDUCED":eco?"ECO":max?"MAX":"BALANCED";
 };
 const motionObserver=typeof MutationObserver==="function"?new MutationObserver(syncMotion):null;
 motionObserver?.observe(document.body,{attributes:true,attributeFilter:["class"]});
 motionPref?.addEventListener?.("change",syncMotion);
 lowPref?.addEventListener?.("change",syncMotion);
 syncMotion();
 let closed=false;
 const destroy=()=>{if(closed)return;closed=true;
    motionObserver?.disconnect();motionPref?.removeEventListener?.("change",syncMotion);
    lowPref?.removeEventListener?.("change",syncMotion);
    probe.close();aiClient?.destroy();store.close();world.destroy();work.destroy();castPanel.remove();spacePanel.destroy();};
 window.addEventListener("pagehide",destroy,{once:true});
 return {summary,nativeReady:probe.available,e07:"HOLD",destroy};
}
Promise.all(["mega814/manifest.json","mega814/menu-v2-193.json"].map(async path=>{
 const r=await fetch(path,{cache:"no-store",credentials:"same-origin"});
 if(!r.ok||r.type==="opaque")throw Error("OWNER_MENU_V2_SOURCE_MISSING");
 return r.json();
})).then(([manifest,menuV2])=>bootstrapMega814(manifest,menuV2))
 .catch(()=>{/* original owner app stays functional; no fictitious route readiness */});
