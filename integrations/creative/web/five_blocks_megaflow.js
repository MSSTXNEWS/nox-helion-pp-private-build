// Additive NOX Creative Studio B01-B05 bridge. No new HOME, model engine, server, or database.
(() => {
 'use strict';
 if (window.NOXCS5MegaFlow || !document.getElementById('screen-five') || typeof rpc!=='function') return;
 const get=id=>document.getElementById(id);
 const sources=['books','openlibrary','crossref','openalex'];
 const stopStatuses=new Set(['ERROR','FAILED','HOLD','CANCELLED','STOPPED','OFFLINE','TIMEOUT','DENIED','UNAVAILABLE']);
 let current=null;
 const screen=get('screen-five'),btn=get('cs5-pipeline');
 if(!btn) return;
 const panel=document.createElement('section');panel.className='panel';panel.id='cs5-megaflow';
 const label=document.createElement('h2');label.textContent='NOX · CREATIVE B01–B05 · SINGLE FLOW';
 const status=document.createElement('pre');status.setAttribute('role','status');
 status.textContent='Готово к запуску · без автопубликации, скачивания и платежей';
 panel.append(label,status);screen.querySelector('.panel')?.append(panel);
 const check=r=>{if(current!==r||r.cancelled)throw Error('CS5_STOP_OR_SUPERSEDED_HOLD');};
 const note=(r,s,t)=>{r.log.push(s+': '+t);status.textContent='Project '+r.project+' · '+r.log.join('\n');};
 const id=()=>{const x=String(get('cs5-project')?.value||'').trim();if(!/^[a-z0-9_-]{1,48}$/i.test(x))throw Error('CS5_PROJECT_ID_HOLD');if(get('project'))get('project').value=x;return x;};
 const safeUrl=x=>{try{const u=new URL(x);return u.protocol==='https:'&&!u.username&&!u.password?u.href:'';}catch{return '';}};
 async function worker(r,action,payload,stage){
   check(r);const result=await rpc(action,payload);check(r);
   if(!result||typeof result!=='object'||result.ok===false||result.error)throw Error(stage+'_WORKER_HOLD');
   const state=String(result.status||'').toUpperCase();
   if(!state||stopStatuses.has(state)||/^FAILED|^ERROR|^HOLD/.test(state))throw Error(stage+'_'+(state||'NO_STATUS'));
   note(r,stage,state);return result;
 }
 async function execute(){
   if(current){status.textContent='HOLD: мегамаршрут уже запущен';return;}
   let project;try{project=id();}catch(e){status.textContent=String(e.message||e);return;}
   const r={project,cancelled:false,log:[]};current=r;btn.disabled=true;
   try{
     const query=String(get('cs5-research-query')?.value||get('cs5-text')?.value||'').trim().slice(0,160);
     if(!query||/[\u0000-\u001f]/.test(query))throw Error('B01_RESEARCH_QUERY_REQUIRED');
     note(r,'B01','Запрос 4 открытых исследовательских каталогов');
     const fetched=await Promise.allSettled(sources.map(async source=>{
       const a=await worker(r,'cs5_research',{project_id:project,source,query},'B01_'+source);
       if(!Array.isArray(a.items))throw Error('B01_ITEMS_HOLD');return {source,items:a.items.slice(0,8)};
     }));
     check(r);
     const records=[];let failures=0;
     for(const f of fetched){if(f.status!=='fulfilled'){failures++;continue;}
       for(const x of f.value.items){if(x&&typeof x==='object')records.push({
         title:String(x.title||'Без названия').slice(0,140),
         source:f.value.source,url:safeUrl(x.source_url),detail:String(x.detail||'').slice(0,140)
       });}}
     if(!records.length)throw Error('B01_NO_PROVIDER_EVIDENCE');
     note(r,'B01','метаданных '+records.length+', ошибок источников '+failures);
     const lines=['NOX · Creative Brief · '+project,'Тема: '+query,
       'Источники — публичные метаданные, не проверенные факты и не лицензии.',
       ...records.slice(0,8).map((x,i)=>(i+1)+'. '+x.title+' ['+x.source+'] '+x.url),
       'Создать оригинальные историю, 3 сцены и музыкальный план; проверить авторские права.',
       'Нет разрешения на внешнюю публикацию, платежи или загрузку весов.'];
     const brief=lines.join('\n').slice(0,3000);get('cs5-text').value=brief;
     note(r,'B02','Черновик подготовлен');
     await worker(r,'cs5_append',{project_id:project,block:'B02',kind:'idea',text:brief},'B02_JOURNAL');
     const story=await worker(r,'storyboard',{project_id:project,prompt:brief,kind:'movie',scenes:3},'B03_STORY');
     if(['QUEUED','ACCEPTED','PENDING','RUNNING'].includes(String(story.status).toUpperCase()))note(r,'B03','Сценарий ещё не подтверждён файлом');
     await worker(r,'create_text',{project_id:project,prompt:brief,kind:'sound'},'B03_AUDIO');
     await worker(r,'project_files',{project_id:project},'B03_ASSETS');
     await worker(r,'cs5_overview',{},'B04_MODEL_CENTER');
     note(r,'B04','Веса не скачиваются, используется штатный ModelCenter');
     const brand='Рабочий бренд проекта '+project+'. Тема: '+query+'. Права, публикации, продажи и доходы не подтверждены.';
     await worker(r,'cs5_append',{project_id:project,block:'B05',kind:'brand',text:brand},'B05_BRAND');
     const exported=await worker(r,'cs5_export',{project_id:project},'B05_MARKDOWN');
     note(r,'FINISH','Источник/сценарий/план/черновик; экспорт '+String(exported.file||'локальный')+'. Это не готовый фильм и не E07.');
   }catch(e){note(r,'HOLD',String(e?.message||e));}
   finally{current=null;btn.disabled=false;}
 }
 async function stop(){
   if(!current){get('stop')?.click();return;}
   if(!confirm('Отправить STOP штатному Creative Worker?'))return;
   const r=current;r.cancelled=true;note(r,'STOP','Отмена новых этапов');
   try{const ack=await rpc('stop');note(r,'STOP_ACK',String(ack?.status||'НЕТ ПОДТВЕРЖДЕНИЯ'));}
   catch(e){note(r,'STOP_HOLD',String(e.message||e));}
 }
 window.NOXCS5MegaFlow=Object.freeze({run:execute,stop});
})();