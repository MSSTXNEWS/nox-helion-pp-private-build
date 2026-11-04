import {DIRECTIONS,WORLDS,CORE_IDS,PERSONAS,PRIMARY,ROUTE_COUNT,getWorld,getRoute} from './express-layout.mjs';
import {createNativeMenuClient,isNativeChatTerminal,canonicalChatContext} from '../onehost-menu-bindings.mjs';
const doc=document,$=id=>doc.getElementById(id);
const el=(tag,cls,label)=>{const x=doc.createElement(tag);if(cls)x.className=cls;if(label!==undefined)x.textContent=label;return x;};
const button=(label,cls,click)=>{const b=el('button',cls,label);b.type='button';b.addEventListener('click',click);return b;};
const P={directions:$('directions'),planets:$('planets'),details:$('details'),status:$('status'),actions:$('actions'),title:$('title'),subtitle:$('subtitle'),search:$('search'),cores:$('cores'),fx:$('fx'),host:$('host')};
let client=null,active=null,requesting=false,chatInFlight=false,chatStopPending=false;
let selectedCore=null,selectedPersona=null;
const PERSONA_TO_OWNER=Object.freeze({KV:'kairen',AM:'adrian',LA:'leon',EV:'elina',KW:'cassien'});
function ownerScope(){
 if(!selectedCore||!selectedPersona)return null;
 const scope=canonicalChatContext(selectedCore,PERSONA_TO_OWNER[selectedPersona]);
 return scope.core_id&&scope.persona_id?scope:null;
}
if(window.location.origin==='https://nox.local'&&window.location.pathname==='/'&&window.location.search===''&&window.location.hash===''&&window.chrome?.webview){
 try{client=createNativeMenuClient({webview:window.chrome.webview});P.host.textContent='ТРАНСПОРТ НАЙДЕН';}
 catch{client=null;}
}
const say=message=>{P.status.textContent=message;};
function draft(id,name){return [
 'NOX HELION EXPRESS / P0 / FEATURE '+id,
 'В приоритет на развитие: '+name+'. ТЗ: EXPRESS V11 / FIN V16.',
 'Использовать существующие WPF/WebView2 + Python OneHost, 8 CoreID и S03.',
 'Изучить журнал ошибок и исходники, найти готовый донор, дописать и связать native обработчик, UI и ACL.',
 'Реальный прогресс: источник → код → тест → интеграция → Windows запуск → независимая E07.',
 'Самостоятельный рост ИИ: проверенный RAG, оценка качества, разрешённое обучение LoRA/QLoRA с GPU preflight.',
 'Не запускать обучение, установку, управление ПК или патчи без разрешения; STOP и rollback обязательны.',
 'Передать владельцу RunID, SHA, результат и ошибки. Никакого вымышленного PASS.'
 ].join('\n');}
function setDetails(...children){
 P.details.hidden=false;P.details.replaceChildren(...children);
 // Navigation panels live beneath the universe: actually bring the opened function into view.
 window.requestAnimationFrame?.(()=>{if(!P.details.hidden)P.details.scrollIntoView?.({block:'start',behavior:'auto'});});
}
function overview(){
 active=null;P.details.hidden=true;P.details.replaceChildren();
 P.title.textContent='10 МИРОВ HELION';
 P.subtitle.textContent='8 направлений · 10 графических миров · '+ROUTE_COUNT+' маршрута';
 [...P.planets.querySelectorAll('button'),...P.directions.querySelectorAll('button')].forEach(b=>b.setAttribute('aria-pressed','false'));
 say('NOX EXPRESS · функциям требуется подтверждение от локального ядра');
}
function world(id){
 const w=getWorld(id);if(!w)return;
 active=id;P.title.textContent=w.title;P.subtitle.textContent=w.description;
 const top=el('div','detail-top');
 top.append(button('← ВСЕ МИРЫ','back',overview),el('span','eyebrow',w.routes.length+' ФУНКЦИЙ'));
 const grid=el('div','route-grid');
 w.routes.forEach(r=>{
  const b=button(r.label,'route',()=>openRoute(r.id));b.dataset.route=r.id;
  b.append(el('small','',r.id));grid.append(b);
 });
 setDetails(top,grid);
 P.planets.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.world===id)));
 P.directions.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.section===w.section)));
 say(w.title+' · выберите нужную функцию');
}
function pending(id,label){
 const h=el('h2','',''+label),top=el('div','detail-top');
 top.append(button('← НАЗАД','back',()=>{const parent=getRoute(id)?.world.id||active;if(parent)world(parent);else overview();}),el('span','eyebrow',id));
 const p=el('p','body-copy','Этот модуль уже имеет своё место во вселенной NOX. Его рабочий обработчик, права доступа и результаты пока не подтверждены. Можно поставить разработку в приоритет.');
 const steps=el('div','steps');
 ['АНАЛИЗ','РАЗРАБОТКА','ПРОВЕРКА','АКТИВАЦИЯ'].forEach((s,i)=>steps.append(el('span','step',String(i+1).padStart(2,'0')+' · '+s)));
 const priority=button('✦ УСКОРИТЬ NOX','boost',async()=>{
  if(requesting)return;requesting=true;priority.disabled=true;
  const task=draft(id,label);
  const offerCopy=()=>{
   if(P.details.querySelector('.task-copy'))return;
   const field=el('textarea','task-copy');field.readOnly=true;field.value=task;field.setAttribute('aria-label','Приоритетное задание для NOX');
   const copy=button('КОПИРОВАТЬ ЗАДАНИЕ','back',async()=>{
    try{await navigator.clipboard.writeText(task);say('Задание скопировано. Для постановки в очередь нужно подтверждение NOX.');}
    catch{field.select();say('Выделите задание и скопируйте вручную.');}
   });
   P.details.append(field,copy);
  };
  // Existing native ACL/consent remains the only route. Never claim autonomous work on click.
  try{
   const scope=ownerScope();
   if(!client){offerCopy();say('План ускорения подготовлен. Подключите локальный OneHost или скопируйте его.');}
   else if(!scope){offerCopy();say('Выберите CoreID и Persona для памяти S03; пока задание только для копирования.');}
   else{
    say('Запрашиваю подтверждение владельца для очереди S03...');
    const result=await client.request('chat.commands',{action:'selfbuilder.propose',task,...scope});
    const receipt=result?.result;
    const runId=receipt?.run_id;
    if(result?.state==='COMPLETED'&&receipt?.ack===true&&
       typeof runId==='string'&&/^S03-[A-Za-z0-9._:-]{1,128}$/.test(runId)&&
       typeof receipt.source_head==='string'&&/^[0-9a-f]{40}(?:[0-9a-f]{24})?$/.test(receipt.source_head)){
     say('Задание принято в S03: RunID '+runId+'. Это не сборка патча и не автоматическое обучение.');
    }else{offerCopy();say('ACK/RunID не подтверждён OneHost. Задание доступно для копирования.');}
   }
  }catch{offerCopy();say('Нет подтверждённого ответа OneHost. Приоритетное задание доступно для копирования.');}
  finally{requesting=false;priority.disabled=false;}
 });
 setDetails(top,el('div','notready','В РАЗРАБОТКЕ'),h,p,steps,priority);
 say(label+' · в плане развития HELION');
}
async function nativeRequest(route,payload,label){
 if(!client){pending(label.id,label.name);return;}
 const top=el('div','detail-top');
 top.append(button('← К РАЗДЕЛУ','back',()=>world(label.world)),el('span','eyebrow','ONEHOST · '+route));
 const output=el('pre','output','Ожидание данных от локального ядра');
 setDetails(top,el('h2','',label.name),output);
 try{
  const reply=await client.request(route,payload);
  const valid=reply?.state==='COMPLETED';
  if(valid){
   output.textContent=JSON.stringify(reply.result??reply.data??{state:reply.state},null,2).slice(0,9000);
   say('Получен ответ от OneHost. Выполнение всей функции отдельно не подтверждено.');
  }else{pending(label.id,label.name);say('Native обработчик пока не подтвердил действие.');}
 }catch{pending(label.id,label.name);say('Локальный OneHost недоступен или действие отклонено.');}
}

/* LIVE native CHAT for EXPRESS. One existing WebView2 owner, bounded rendering and native STOP.
   Never show success or release an in-flight request without a native terminal receipt. */
function liveChat(label){
 const top=el('div','detail-top');
 top.append(button('← К МИРУ','back',()=>world(label.world)),el('span','eyebrow','P02 · LOCAL ONEHOST'));
 const surface=el('div','nox-chat'),heading=el('div','nox-chat-heading');
 heading.append(el('h2','','HELION · LIVE CHAT'),el('span','nox-chat-trust',client?'NATIVE ТРАНСПОРТ ОБНАРУЖЕН':'OFFLINE · ONEHOST НЕТ'));
 const coreRow=el('div','nox-chat-chips'),personaRow=el('div','nox-chat-chips'),modelsRow=el('div','nox-chat-chips');
 coreRow.setAttribute('aria-label','Выбор ядра');personaRow.setAttribute('aria-label','Выбор персоны');
 modelsRow.setAttribute('aria-label','Локальная модель');
 const log=el('div','nox-chat-log');log.setAttribute('role','log');log.setAttribute('aria-label','Локальный диалог HELION');
 const form=el('form','nox-chat-compose'),input=el('textarea','nox-chat-input');
 input.rows=3;input.maxLength=4000;input.placeholder='Сообщение локальному ядру (Enter — отправить, Shift+Enter — перенос)';
 input.setAttribute('aria-label','Текст сообщения');
 const send=button('ОТПРАВИТЬ','nox-chat-send',()=>{}),stop=button('■ STOP','nox-chat-stop',()=>{});
 const info=el('p','nox-chat-info',client?'Выберите установленную модель. Ответы подтверждает OneHost.':'Для ответов необходим установленный OneHost.');
 info.setAttribute('role','status');info.setAttribute('aria-live','polite');
 const controls=el('div','nox-chat-controls');controls.append(send,stop);
 form.append(input,controls);
 surface.append(heading,el('p','nox-chat-label','ЯДРО'),coreRow,el('p','nox-chat-label','ПЕРСОНА'),personaRow,
  el('p','nox-chat-label','УСТАНОВЛЕННЫЕ МОДЕЛИ'),modelsRow,log,form,info);
 setDetails(top,surface);
 let core='core.core',persona='persona.kairen_voss',model='',chatEpoch=0,modelSelectionPending=false;
 // A selected model belongs to its native-confirmed UI scope, never to a different CoreID/Persona.
 let scopeEpoch=0,renderModels=()=>{};
 const enabled=()=>!!client&&!!model&&!chatInFlight&&!modelSelectionPending;
 const redraw=()=>{send.disabled=!enabled();stop.disabled=!client||!chatInFlight||chatStopPending;};
 function chips(parent,items,current,onSelect){
  parent.replaceChildren();
  for(const [value,label] of items){
   const b=button(label,'nox-chat-chip',()=>{if(chatInFlight)return;onSelect(value);chips(parent,items,value,onSelect);});
   b.setAttribute('aria-pressed',String(current===value));b.disabled=chatInFlight;parent.append(b);
  }
 }
 const cores=CORE_IDS.map(id=>['core.'+id.toLowerCase(),id]);
 const personas=PERSONAS.map((id,i)=>[['persona.kairen_voss','persona.adrian_marrow','persona.leon_ardis','persona.elina_veil','persona.kassien_veir'][i],id]);
 const invalidateModelScope=()=>{
  ++scopeEpoch;model='';renderModels();redraw();
  if(info.isConnected)info.textContent='HOLD · контекст изменился; подтвердите модель через OneHost';
 };
 const chooseCore=v=>{
  const changed=core!==v;core=v;selectedCore=CORE_IDS.find(id=>'core.'+id.toLowerCase()===v)||null;
  if(changed)invalidateModelScope();
 };
 const choosePersona=v=>{
  const changed=persona!==v;persona=v;
  selectedPersona=PERSONAS[['persona.kairen_voss','persona.adrian_marrow','persona.leon_ardis','persona.elina_veil','persona.kassien_veir'].indexOf(v)]||null;
  if(changed)invalidateModelScope();
 };
 chips(coreRow,cores,core,chooseCore);chips(personaRow,personas,persona,choosePersona);
 const row=(who,content)=>{const item=el('p','nox-chat-bubble nox-chat-'+who,content);log.append(item);log.scrollTop=log.scrollHeight;return item;};
 async function loadModels(){
  const inventoryEpoch=scopeEpoch;
  if(!client){modelsRow.append(el('span','nox-chat-empty','Локальное ядро не подключено'));redraw();return;}
  try{
   const reply=await client.request('chat.model',{});
   if(!modelsRow.isConnected)return;
   if(reply?.state!=='COMPLETED'||!Array.isArray(reply.result?.models)){throw Error('NO_MODELS');}
   const names=[...new Set(reply.result.models.filter(v=>typeof v==='string'&&v.length&&v.length<=160))].slice(0,32);
   // An inventory reply which began in a previous scope cannot authorize SEND.
   model=inventoryEpoch===scopeEpoch&&names.includes(reply.result.selectedModel)?reply.result.selectedModel:'';
   const render=()=>{
    modelsRow.replaceChildren();
    if(!names.length)modelsRow.append(el('span','nox-chat-empty','Модели не установлены · откройте MODELS'));
    for(const name of names){
     const b=button(name,'nox-chat-chip',async()=>{
      // Serialize native selections: competing ACKs must not select a stale model.
      if(chatInFlight||modelSelectionPending)return;
      modelSelectionPending=true;
      model=''; // Unknown until the native owner confirms this exact selection.
      render();redraw();
      info.textContent='Выбор модели проверяется ядром...';
      const requestedScopeEpoch=scopeEpoch;
      try{
       const a=await client.request('chat.model',{model:name});
       if(requestedScopeEpoch===scopeEpoch&&modelsRow.isConnected&&
          a?.state==='COMPLETED'&&a.result?.selectedModel===name){
        model=name;info.textContent='Модель подтверждена: '+name;
       }else info.textContent='HOLD · нет актуального native ACK выбранной модели и контекста';
      }catch{info.textContent='HOLD · нет подтверждения выбора модели';}
      finally{modelSelectionPending=false;render();redraw();}
     });
     b.setAttribute('aria-pressed',String(name===model));b.disabled=chatInFlight||modelSelectionPending;modelsRow.append(b);
    }
   };
   renderModels=render;render();redraw();
   info.textContent=model?'Выбрана локальная модель: '+model:'Выберите модель из списка, подтверждённого OneHost';
  }catch{modelsRow.replaceChildren(el('span','nox-chat-empty','Не удалось получить локальные модели'));info.textContent='HOLD · каталог моделей недоступен';redraw();}
 }
 async function submit(ev){
  ev?.preventDefault?.();
  const text=input.value.trim();if(!enabled()||!text)return;
  chatInFlight=true;chatStopPending=false;const epoch=++chatEpoch;redraw();
  chips(coreRow,cores,core,chooseCore);chips(personaRow,personas,persona,choosePersona);
  input.value='';row('user',text);
  const replyRow=row('assistant','');info.textContent='REQUESTED · запрос в OneHost';
  function terminal(reply){
   if(!isNativeChatTerminal(reply))return;
   chatInFlight=false;chatStopPending=false;
   if(!info.isConnected)return;
   if(reply.state==='COMPLETED'&&typeof reply.result?.answer==='string')replyRow.textContent=reply.result.answer.slice(0,100000);
   info.textContent=reply.state==='COMPLETED'?'COMPLETED · ответ локальной модели':'HOLD · '+(reply.errorCode||'операция отклонена');
   redraw();chips(coreRow,cores,core,chooseCore);chips(personaRow,personas,persona,choosePersona);
  }
  try{
   const result=await client.request('helion.chat',{text,model,core_id:core,persona_id:persona},ev=>{
    if(epoch!==chatEpoch||!replyRow.isConnected||typeof ev.delta!=='string')return;
    if(replyRow.textContent.length<100000)replyRow.textContent=(replyRow.textContent+ev.delta).slice(0,100000);
    info.textContent='STREAMING · локальный OneHost';log.scrollTop=log.scrollHeight;
   },terminal);
   terminal(result);
   if(!isNativeChatTerminal(result)&&info.isConnected)info.textContent='HOLD · нет терминального подтверждения; STOP доступен';
  }catch(err){
   if(err.message!=='TIMEOUT'){chatInFlight=false;chatStopPending=false;redraw();}
   if(info.isConnected)info.textContent=err.message==='TIMEOUT'?'HOLD · истекло ожидание, STOP доступен':'HOLD · native ответ не получен';
  }
 }
 form.addEventListener('submit',submit);
 send.addEventListener('click',submit);
 input.addEventListener('keydown',ev=>{if(ev.key==='Enter'&&!ev.shiftKey&&!ev.isComposing){ev.preventDefault();void submit(ev);}});
 stop.addEventListener('click',async()=>{
  if(!client||!chatInFlight||chatStopPending)return;
  chatStopPending=true;redraw();info.textContent='STOP REQUESTED · ожидаем native подтверждение';
  try{
   const r=await client.request('chat.stop',{});
   if(info.isConnected)info.textContent=r?.state==='HOLD'?'HOLD · STOP отклонён':
    'STOP запрошен; ждём терминальный результат исходного запроса';
  }catch{if(info.isConnected)info.textContent='HOLD · STOP не подтверждён';}
  finally{chatStopPending=false;redraw();}
 });
 redraw();void loadModels();
}

function openRoute(id){
 const item=getRoute(id);if(!item)return;
 const label={id,name:item.label,world:item.world.id};
 if(id==='chat'){liveChat(label);return;}
 // Only read-only native routes with an existing client contract; no fake success.
 const reads={
 'model-library':['models.catalog',{}],'model-load':['models.catalog',{}],
 'chat-history':['chat.history',{}],
 'progress':['chat.commands',{action:'selfbuilder.worker.status'}],
 'core-status':['chat.commands',{action:'selfbuilder.capabilities'}],
 'learning-proofs':['chat.commands',{action:'selfbuilder.learning.proofs'}]
 };
 if(client&&reads[id]){const [route,payload]=reads[id];void nativeRequest(route,payload,label);}
 else pending(id,item.label);
}
function direction(id){
 const worlds=WORLDS.filter(w=>w.section===id);
 if(worlds.length===1){world(worlds[0].id);return;}
 const grid=el('div','route-grid');
 worlds.forEach(w=>grid.append(button(w.title,'route',()=>world(w.id))));
 P.title.textContent=DIRECTIONS.find(x=>x[0]===id)?.[1]||id;P.subtitle.textContent='Выберите графический мир';
 setDetails(button('← ВСЕ МИРЫ','back',overview),grid);
 P.directions.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.section===id)));
}
function mainAction(name){
 const routes={CHAT:'chat',INSTALL:'system',MODELS:'model-library',LEARN:'evolution',REPORTS:'progress'};
 const id=routes[name];if(id)openRoute(id);
}
DIRECTIONS.forEach(([id,name])=>{
 const b=button(name,'direction',()=>direction(id));b.dataset.section=id;b.setAttribute('aria-pressed','false');P.directions.append(b);
});
WORLDS.forEach(w=>{
 const b=button('', 'planet planet-'+w.id,()=>world(w.id));b.dataset.world=w.id;
 b.style.setProperty('--i',String(w.index));b.setAttribute('aria-label',w.title+' · '+w.routes.length+' функций');
 b.setAttribute('aria-pressed','false');b.append(el('span','planet-label',w.title),el('small','',w.routes.length+' ФУНКЦИЙ'));P.planets.append(b);
});
PRIMARY.forEach(name=>{const b=button(name,'main-action',()=>mainAction(name));b.dataset.action=name;P.actions.append(b);});
CORE_IDS.forEach(id=>{
 const b=button(id,'core',()=>{
  selectedCore=id;
  P.cores.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.core===id)));
  say('Выбрано ядро '+id+'. Для заявки на ускорение также выберите Persona.');
 });
 b.dataset.core=id;b.setAttribute('aria-pressed','false');P.cores.append(b);
});
doc.querySelectorAll('.persona span').forEach(chip=>{
 const id=chip.textContent?.trim();
 if(!PERSONAS.includes(id))return;
 chip.setAttribute('role','button');chip.setAttribute('tabindex','0');
 chip.setAttribute('aria-label','Выбрать Persona '+id);
 chip.setAttribute('aria-pressed','false');
 const choose=()=>{
  selectedPersona=id;
  doc.querySelectorAll('.persona span').forEach(x=>x.setAttribute('aria-pressed',String(x===chip)));
  say('Выбрана Persona '+id+'. Предложение только через согласие OneHost.');
 };
 chip.addEventListener('click',choose);
 chip.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose();}});
});
P.search.addEventListener('input',()=>{
 const q=P.search.value.trim().toLocaleLowerCase('ru');if(!q){overview();return;}
 const results=WORLDS.flatMap(w=>w.routes.map(r=>({...r,world:w}))).filter(x=>
 x.label.toLocaleLowerCase('ru').includes(q)||x.id.includes(q)||x.world.title.toLocaleLowerCase('ru').includes(q));
 P.title.textContent='ПОИСК';P.subtitle.textContent='Найдено '+results.length+' функций';
 const grid=el('div','route-grid');results.forEach(r=>grid.append(button(r.world.title+' / '+r.label,'route',()=>openRoute(r.id))));
 setDetails(grid);
});
const modes=['BALANCED','MAX','ECO'];let idx=0;
P.fx.addEventListener('click',()=>{idx=(idx+1)%modes.length;doc.body.dataset.fx=modes[idx];P.fx.textContent='FX '+modes[idx];});
doc.addEventListener('keydown',e=>{if(e.isComposing||e.defaultPrevented||e.repeat)return;
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();P.search.focus();P.search.select();}
 if(e.key==='Escape'&&!P.details.hidden)overview();
});
window.addEventListener('pagehide',()=>client?.destroy?.(),{once:true});
overview();
