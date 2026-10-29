/* PACK02 opt-in view; requires an approved secondary mount; no scripts on HOME. */
import {execute} from "./ops.mjs";
import {catalog} from "./catalog.mjs";
const node=(tag,klass,label)=>{const n=document.createElement(tag);if(klass)n.className=klass;if(label!==undefined)n.textContent=label;return n};
export function mountPack02(root,{allowHome=false}={}){
 if(!root||root.nodeType!==1)throw Error("APPROVED_SECONDARY_MOUNT_REQUIRED");
 if(root.closest('[data-nox-page="home"]')&&!allowHome)throw Error("D02_HOME_LOCK");
 const frame=node("section","nox-p2");
 frame.setAttribute("aria-label","NOX TOOLKIT · 50 локальных операций");
 const header=node("header","nox-p2-header");
 header.append(node("strong","","NOX HELION · TOOLKIT 02"),node("small","","50 готовых локальных операций · без сети и установки"));
 const search=node("input","nox-p2-search");search.type="search";search.placeholder="Поиск по 50 инструментам";search.setAttribute("aria-label","Поиск");
 const grid=node("div","nox-p2-grid");
 const workspace=node("section","nox-p2-workspace");
 const heading=node("h3","","Выберите инструмент");
 const input=node("textarea","nox-p2-editor");input.placeholder="Входной текст, SRT, CSV, JSON или задачи";input.rows=7;input.maxLength=100000;
 const opts=node("textarea","nox-p2-options");opts.placeholder='Параметры JSON: {"seconds":1}';opts.value="{}";opts.rows=2;opts.maxLength=4000;
 const run=node("button","nox-p2-run","Выполнить локально");run.type="button";run.disabled=true;
 const status=node("output","nox-p2-status","Режим: локально · данные не отправляются");
 const output=node("pre","nox-p2-result");output.textContent="";
 let active=null;
 const cards=new Map();
 for(const item of catalog.actions){
   const btn=node("button","nox-p2-tool",item.title);
   btn.type="button";btn.dataset.tool=item.routeId;
   btn.setAttribute("aria-label",item.routeId+" · "+item.title);
   btn.addEventListener("click",()=>{active=item;heading.textContent=item.title+" · "+item.taskId;run.disabled=false;
     for(const b of cards.values())b.setAttribute("aria-pressed",String(b===btn));
     status.textContent="Готово к выполнению без сервера: "+item.routeId;output.textContent="";
   });btn.setAttribute("aria-pressed","false");cards.set(item.routeId,btn);grid.append(btn);
 }
 const filter=()=>{const q=search.value.trim().toLocaleLowerCase();for(const item of catalog.actions)cards.get(item.routeId).hidden=!!q&&!(item.title+" "+item.routeId).toLocaleLowerCase().includes(q)};
 search.addEventListener("input",filter);
 run.addEventListener("click",()=>{if(!active)return;try{const o=JSON.parse(opts.value||"{}");
   const result=execute(active.routeId,input.value,o);
   output.textContent=typeof result.result==="string"?result.result:JSON.stringify(result.result,null,2);
   status.textContent="OK · вычислено локально · "+active.taskId;
 }catch(e){status.textContent="HOLD / ошибка ввода: "+String(e?.message||"UNKNOWN").slice(0,90);output.textContent="";}});
 workspace.append(heading,input,opts,run,status,output);
 frame.append(header,search,grid,workspace);root.append(frame);
 return Object.freeze({dispose(){frame.remove()},getSelected(){return active?.routeId??null},getCount(){return catalog.actions.length}});
}
