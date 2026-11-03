import {DIRECTIONS,WORLDS,CORE_IDS,PERSONAS,PRIMARY,ROUTE_COUNT,getWorld,getRoute} from './express-layout.mjs';
import {createNativeMenuClient} from '../onehost-menu-bindings.mjs';
const doc=document,$=id=>doc.getElementById(id);
const el=(tag,cls,label)=>{const x=doc.createElement(tag);if(cls)x.className=cls;if(label!==undefined)x.textContent=label;return x;};
const button=(label,cls,click)=>{const b=el('button',cls,label);b.type='button';b.addEventListener('click',click);return b;};
const P={directions:$('directions'),planets:$('planets'),details:$('details'),status:$('status'),actions:$('actions'),title:$('title'),subtitle:$('subtitle'),search:$('search'),cores:$('cores'),fx:$('fx'),host:$('host')};
let client=null,active=null,requesting=false;
if(window.location.origin==='https://nox.local'&&window.location.pathname==='/'&&window.chrome?.webview){
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
function setDetails(...children){P.details.hidden=false;P.details.replaceChildren(...children);}
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
 top.append(button('← НАЗАД','back',()=>world(getRoute(id)?.world.id||active)),el('span','eyebrow',id));
 const p=el('p','body-copy','Этот модуль уже имеет своё место во вселенной NOX. Его рабочий обработчик, права доступа и результаты пока не подтверждены. Можно поставить разработку в приоритет.');
 const steps=el('div','steps');
 ['АНАЛИЗ','РАЗРАБОТКА','ПРОВЕРКА','АКТИВАЦИЯ'].forEach((s,i)=>steps.append(el('span','step',String(i+1).padStart(2,'0')+' · '+s)));
 const priority=button('✦ УСКОРИТЬ NOX','boost',async()=>{
  if(requesting)return;requesting=true;priority.disabled=true;
  const task=draft(id,label);
  // The user must activate a separate native owner-approved action; no silent queue.
  if(client){
   say('Проверяется возможность поставить функцию в приоритет...');
   try{
    const result=await client.request('chat.commands',{action:'selfbuilder.propose',task});
    say(result?.state==='COMPLETED'
     ?'OneHost принял запрос. Проверьте RunID и приоритет в журнале; обучение не запускалось.'
     :'OneHost не подтвердил постановку задачи. Задание можно сохранить вручную.');
   }catch{say('Локальный OneHost пока не принял заявку на развитие.');}
  }else{
   const field=el('textarea','task-copy');field.readOnly=true;field.value=task;field.setAttribute('aria-label','Приоритетное задание для NOX');
   const copy=button('КОПИРОВАТЬ ЗАДАНИЕ','back',async()=>{
    try{await navigator.clipboard.writeText(task);say('Техническое задание скопировано для отправки в NOX.');}
    catch{field.select();say('Выделите и скопируйте задание вручную.');}
   });
   P.details.append(field,copy);say('Приоритетное задание подготовлено. Подключите OneHost либо скопируйте его.');
  }
  requesting=false;priority.disabled=false;
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
function openRoute(id){
 const item=getRoute(id);if(!item)return;
 const label={id,name:item.label,world:item.world.id};
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
CORE_IDS.forEach(id=>{P.cores.append(button(id,'core',()=>say(id+' · показания появятся после native events.v3')));});
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
