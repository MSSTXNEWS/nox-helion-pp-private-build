/* NOX V40 three evidence-bound cognition axes for EXISTING V29.3 TRAINING.
 * Works with the same-origin native source/static receipt; no new backend.
 * Unknown evidence -> HOLD (never infer percent from GPU utilization or queue done).
 */
(()=>{'use strict';
 if(!/(?:^|\/)(?:training)\.html$/i.test(location.pathname)) return;
 const SCHEMA='nox-learning-3axes-dashboard-v1';
 const config=[['knowledge','ЗНАНИЯ','S03 · проверенное воспроизведение'],
               ['skills','НАВЫКИ','Практические экзамены и сохранение качества'],
               ['weights','НЕЙРОННЫЕ ВЕСА','Проверенные optimizer steps и checkpoints'],
               ['overall','ОБЩИЙ ПРОГРЕСС','Приёмка ограниченного релиза NOX']];
 const make=(tag,cls,text)=>{const n=document.createElement(tag); if(cls)n.className=cls; if(text)n.textContent=text;return n};
 function circle(id,label){
   const wrap=make('div','nox40-ring');
   const ns='http://www.w3.org/2000/svg';
   const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 140 140');svg.setAttribute('aria-hidden','true');
   const bg=document.createElementNS(ns,'circle');bg.setAttribute('class','nox40-track');bg.setAttribute('cx','70');bg.setAttribute('cy','70');bg.setAttribute('r','54');
   const fg=document.createElementNS(ns,'circle');fg.setAttribute('class','nox40-arc');fg.setAttribute('cx','70');fg.setAttribute('cy','70');fg.setAttribute('r','54');fg.setAttribute('stroke-dasharray','0 339.292');
   svg.append(bg,fg);const val=make('strong','nox40-value','—');val.setAttribute('aria-label',label+': нет подтверждённого результата');
   wrap.append(svg,val);wrap._arc=fg;wrap._value=val;return wrap;
 }
 function init(){
   if(document.getElementById('nox40-learning-observatory'))return;
   const main=document.querySelector('main')||document.body;
   const root=make('section','nox40-observatory');root.id='nox40-learning-observatory';root.setAttribute('aria-label','Три измерения обучения NOX с подтверждёнными источниками');
   const header=make('header','nox40-heading');
   const h=make('h2','', 'NOX · СИНАПТИЧЕСКОЕ РАЗВИТИЕ');const summary=make('span','nox40-status','HOLD · ОЖИДАЕМ ПОДТВЕРЖДЁННЫЕ ДАННЫЕ');
   header.append(h,summary);
   const cards=make('div','nox40-grid');const views={};
   for(const [id,title,desc] of config){
     const card=make('article','nox40-card'+(id==='overall'?' nox40-overall':''));
     const ring=circle(id,title),txt=make('div','nox40-card-caption');
     const h3=make('h3','',title),detail=make('p','',desc),meta=make('small','nox40-proof','Ожидается проверенный источник');
     txt.append(h3,detail,meta);card.append(ring,txt);cards.append(card);views[id]={ring,meta};
   }
   const notice=make('p','nox40-notice','Загрузка GPU и число выполненных задач НЕ являются процентом приобретённых знаний. 100% означает приёмку утверждённой программы, а не абсолютный интеллект.');
   const row=make('div','nox40-bottom');const update=make('button','nox40-update','ОБНОВИТЬ ПОКАЗАТЕЛИ');update.type='button';
   const source=make('span','nox40-time','Источник: NOX OneHost · нет свежей квитанции');row.append(source,update);
   root.append(header,cards,notice,row);
   const parent=document.querySelector('#training-stage'); if(parent?.parentNode)parent.parentNode.insertBefore(root,parent);else main.prepend(root);
   const CIRC=2*Math.PI*54;
   function paint(k,data){
     const v=views[k],ok=data?.state==='VERIFIED'&&Number.isFinite(data.percent)&&data.percent>=0&&data.percent<=100;
     const p=ok?data.percent:null;
     v.ring._arc.setAttribute('stroke-dasharray',`${p===null?0:(CIRC*p/100).toFixed(2)} ${CIRC.toFixed(2)}`);
     v.ring._arc.classList.toggle('nox40-valid',ok);
     v.ring._value.textContent=p===null?'—':((p%1)?p.toFixed(1):p.toFixed(0))+'%';
     v.ring._value.setAttribute('aria-label',k+': '+(p===null?'нет подтверждённых данных':p+' процентов'));
     v.meta.textContent=ok?('Проверено: '+String(data.passed??'—')+'/'+String(data.total??'—')+' · источник доступен'):
        ('HOLD · '+String(data?.reason||data?.state||'НЕТ КВИТАНЦИИ').slice(0,90));
     if(k==='overall'&&data?.state==='VERIFIED')v.meta.textContent='30% знания + 35% навыки + 35% веса';
   }
   let busy=false;
   async function refresh(){
     if(busy)return;busy=true;update.disabled=true;
     try{
       const ctrl=new AbortController(),timeout=setTimeout(()=>ctrl.abort(),6500);
       let response;
       try{response=await fetch('./nox-learning-3axes-dashboard.json',{cache:'no-store',credentials:'same-origin',signal:ctrl.signal})}finally{clearTimeout(timeout)}
       if(!response.ok)throw new Error('HTTP '+response.status);
       const d=await response.json();
       if(d?.schema!==SCHEMA||!d.axes||!d.overall)throw new Error('BAD_PROOF_SCHEMA');
       for(const [key] of config)paint(key,key==='overall'?d.overall:d.axes[key]);
       const ready=Object.values(d.axes).filter(x=>x?.state==='VERIFIED').length;
       summary.textContent=ready===3?'3/3 ОСИ ИМЕЮТ ДОКАЗАТЕЛЬСТВА':'HOLD · ПОДТВЕРЖДЕНЫ '+ready+'/3';
       source.textContent='Источник: '+String(d.at_utc||'ВРЕМЯ НЕИЗВЕСТНО').slice(0,32)+' · только native квитанции';
       root.dataset.proof='native-or-hold';
     }catch(e){
       for(const [key] of config)paint(key,{state:'HOLD',reason:'SOURCE_UNAVAILABLE'});
       summary.textContent='HOLD · НЕТ ФИЗИЧЕСКОЙ КВИТАНЦИИ';
       source.textContent='Источник: недоступен; не показываем вымышленные проценты';
     }finally{update.disabled=false;busy=false}
   }
   update.addEventListener('click',refresh);
   refresh();const interval=setInterval(()=>{if(!document.hidden)refresh()},45000);
   window.addEventListener('pagehide',()=>clearInterval(interval),{once:true});
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
