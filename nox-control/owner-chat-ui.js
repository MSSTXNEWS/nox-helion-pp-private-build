/* Real executor activity and photo/video jobs inside the original Resonance. */
(()=>{
  'use strict';
  if(window.NOX_NATIVE_OWNER!==true||window.__NOX_OWNER_LIVE_UI)return;
  window.__NOX_OWNER_LIVE_UI=true;
  const E=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const terminal=new Set(['COMPLETED','FAILED','CANCELLED','BLOCKED']);
  async function api(path,data){
    const ac=new AbortController(),timer=setTimeout(()=>ac.abort(),12000);
    try{
      const r=await fetch(path,{method:data===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',signal:ac.signal,
        headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});
      const result=await r.json();if(!r.ok)throw Error(result.reason||result.error||'HTTP_'+r.status);return result;
    }finally{clearTimeout(timer);}
  }
  function reserveReturnBanner(){
    const banner=document.querySelector('body.nox-v24 > .nox-v28-pc-return');
    if(!banner)return;
    // The preserved WEB29 return bar is in normal flow above a fixed stage.
    // Reserve its real height so it cannot cover the first dialog control.
    const update=()=>{
      const box=banner.getBoundingClientRect();
      const shown=box.width>0&&box.height>0&&getComputedStyle(banner).display!=='none';
      const bottom=shown&&Number.isFinite(box.bottom)?Math.max(0,Math.min(window.innerHeight,Math.ceil(box.bottom))):0;
      document.documentElement.style.setProperty('--nox-owner-top-inset',bottom+'px');
      window.__NOX_OWNER_LAYOUT_FIX='RETURN_BANNER_INSET_V1';
    };
    update();
    if(typeof ResizeObserver==='function'){const observer=new ResizeObserver(update);observer.observe(banner);}
    window.addEventListener('resize',update,{passive:true});
  }
  function attach(){
    const header=document.querySelector('.v24-top'),main=document.querySelector('.v24-main');
    if(!header||!main)return;
    const style=E('style');style.textContent=`
      body.nox-v24 .v24-stage{top:var(--nox-owner-top-inset,0px)}
      body.nox-v24 .v24-app{min-height:0;max-height:100%;overflow:hidden}
      body.nox-v24 .v24-main{min-height:0;overflow:hidden}
      body.nox-v24 .v24-column{min-height:min(220px,40vh);min-width:0;flex:1 1 0;overflow:hidden}
      body.nox-v24 .v24-stream{flex:1 1 0;min-height:0}
      body.nox-v24 .v24-composer{flex:0 0 auto}
      .nox-owner-status-stack{flex:0 1 auto;min-height:0;max-height:min(28vh,280px);overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#6e604d transparent}
      .nox-live-strip{display:flex;flex-wrap:wrap;align-items:center;gap:7px;padding:9px 13px;margin:0 0 6px;color:#e9d8bd;font:12px system-ui}
      .nox-live-chip{padding:5px 8px;border-radius:9px;background:#151b22bb;border:1px solid #43464c;white-space:nowrap}
      .nox-live-chip[data-state=busy]{border-color:#d7a563;color:#ffe0a6;box-shadow:0 0 12px #d9a25720}
      .nox-live-actions{display:flex;gap:7px;margin-left:auto}.nox-live-btn{min-height:36px;padding:6px 13px;border:1px solid #947044;border-radius:10px;background:#29221dcc;color:#f5d5a3;cursor:pointer}
      .nox-media-panel{position:fixed;z-index:500;inset:10vh max(4vw,calc((100vw - 840px)/2)) auto;background:#111821f5;border:1px solid #a67c48;border-radius:18px;padding:22px;color:#ebddc8;box-shadow:0 25px 100px #000c;max-height:80vh;overflow:auto;font:14px system-ui}
      .nox-media-panel[hidden]{display:none}.nox-media-panel textarea{display:block;width:100%;min-height:100px;background:#090f17;color:#f4e6cf;border:1px solid #51515a;border-radius:10px;margin:13px 0;padding:12px;box-sizing:border-box}
      .nox-media-panel h2{margin:0 0 12px;font:600 20px system-ui}.nox-media-panel img,.nox-media-panel video{display:block;max-width:100%;max-height:48vh;border-radius:10px;margin-top:14px}
      .nox-media-panel button:disabled{opacity:.5;cursor:default}.nox-media-status{white-space:pre-wrap;line-height:1.5;margin:12px 0}.nox-media-links{display:flex;gap:12px;margin-top:12px}
      @media(max-width:600px){.nox-live-strip{gap:5px;padding:6px}.nox-live-chip{font-size:10px}.nox-media-panel{inset:6vh 3vw auto}.nox-live-actions{width:100%;margin-left:0}}
    `;document.head.append(style);reserveReturnBanner();
    const strip=E('div',undefined,'nox-live-strip'),label=E('span','Исполнители'),chips=E('span');chips.style.display='contents';
    const actions=E('div',undefined,'nox-live-actions'),image=E('button','Фото','nox-live-btn'),video=E('button','Видео','nox-live-btn');
    image.type=video.type='button';actions.append(image,video);strip.append(label,chips,actions);header.after(strip);
    // Both existing panels share a bounded scrolling area. Their contents and
    // open state never determine the space left for the composer/Stop control.
    const statusStack=E('section',undefined,'nox-owner-status-stack');
    statusStack.setAttribute('aria-label','Состояние и отчёты NOX');strip.after(statusStack);
    window.__NOX_OWNER_COMPOSER_LAYOUT='BOUNDED_REPORTS_SCROLL_V1';
    const reports=E('details',undefined,'nox-owner-reports'),reportTitle=E('summary','Отчёты NOX'),reportList=E('div');
    // PRESERVE_REPORTS_OPEN_STATE_V1: polling never overrides the owner's choice.
    reports.open=true;reportTitle.setAttribute('aria-live','polite');
    reports.append(reportTitle,reportList);statusStack.append(reports);
    const reportStyle=E('style');reportStyle.textContent='.nox-owner-reports{margin:0 12px 10px;color:#cbd7e3;font:12px system-ui}.nox-owner-reports summary{padding:8px;cursor:pointer;color:#d8bc87}.nox-owner-report{border-left:2px solid #a3824e;background:#111b25b8;border-radius:0 9px 9px 0;padding:11px 13px;margin:7px 0;line-height:1.55}.nox-owner-report p{margin:5px 0}.nox-owner-report small{color:#90a2b5}';document.head.append(reportStyle);
    const inventory=E('details',undefined,'nox-owner-reports'),inventoryTitle=E('summary','Загрузки · проверяю файлы'),inventoryBody=E('div');
    inventory.dataset.noxDownloadInventory='1';inventory.append(inventoryTitle,inventoryBody);reports.before(inventory);
    const progress=E('details',undefined,'nox-owner-reports'),progressTitle=E('summary','Прогресс программы · проверяю квитанции'),progressBody=E('div');
    progress.dataset.noxWorkProgress='1';progress.open=true;progress.append(progressTitle,progressBody);reports.before(progress);
    let workProgressBusy=false;
    async function refreshWorkProgress(){
      if(workProgressBusy||document.hidden)return;workProgressBusy=true;
      try{
        const value=await api('/api/ui/work-progress');
        const age=Date.now()/1000-Number(value.observed_at);
        const ids=value.supplemental_accepted_task_ids;
        if(value.schema!=='NOX_OWNER_WORK_PROGRESS_V1'||value.state!=='OBSERVED'
          ||value.frozen_295_count!==295||!Number.isSafeInteger(value.receipt_done_count)
          ||value.receipt_done_count<0||value.receipt_done_count>295
          ||!Number.isSafeInteger(value.supplemental_accepted_count)
          ||!Array.isArray(ids)||ids.length!==value.supplemental_accepted_count
          ||!Number.isFinite(age)||age < -5||age>45)throw Error('UNAVAILABLE');
        progressTitle.textContent='Прогресс · квитанции '+value.receipt_done_count+'/295';
        progressBody.replaceChildren();
        progressBody.append(E('p','Зафиксированная база: 295 требований.'));
        progressBody.append(E('p','Подтверждено квитанциями: '+value.receipt_done_count+' / 295.'));
        progressBody.append(E('p','Дополнительные подтверждённые критерии, отдельно от квитанций: '
          +value.supplemental_accepted_count+(ids.length?' · '+ids.join(', '):' · нет')));
        progressBody.append(E('p','Эти данные не подтверждают установку на сервере или live-приёмку.'));
        const stamp=new Date(Number(value.observed_at)*1000);
        progressBody.append(E('small','Снимок: '+stamp.toLocaleString()+' · supplemental scan: '+value.supplemental_state));
      }catch{
        progressTitle.textContent='Прогресс программы · нет свежего подтверждения';
        progressBody.replaceChildren(E('p','Квитанции и supplemental-подтверждения сейчас недоступны.'));
      }finally{workProgressBusy=false;}
    }
    void refreshWorkProgress();setInterval(()=>void refreshWorkProgress(),30000);
    let downloadsBusy=false;
    const size=value=>(Number(value)/1073741824).toLocaleString(undefined,{maximumFractionDigits:2})+' ГиБ';
    async function refreshDownloads(){
      if(downloadsBusy||document.hidden)return;downloadsBusy=true;
      try{
        const [filesResult,engineResult]=await Promise.allSettled([api('/api/ui/downloads'),api('/api/ui/media')]);
        if(filesResult.status!=='fulfilled')throw Error('UNAVAILABLE');
        const value=filesResult.value,media=value.media,drive=value.drive_adapters;
        if(value.schema!=='NOX_OWNER_DOWNLOAD_INVENTORY_V1'||!media||!drive||!Array.isArray(media.assets)||!Array.isArray(drive.assets))throw Error('UNVERIFIED');
        const age=Date.now()/1000-Number(value.observed_at);
        if(!Number.isFinite(age)||age < -5||age>45)throw Error('STALE');
        const total=media.selected_files+drive.selected_files,verified=media.verified_files+drive.verified_files;
        inventoryTitle.textContent='Загрузки · проверено '+verified+'/'+total+' файлов';inventoryBody.replaceChildren();
        const caps=engineResult.status==='fulfilled'&&engineResult.value.schema==='NOX_OWNER_MEDIA_V1'?engineResult.value:null;
        for(const [kind,label] of [['image','Фото · SDXL-Lightning'],['video','Видео · Wan2.1']]){
          const rows=media.assets.filter(row=>row.kind===kind),ready=rows.filter(row=>row.state==='SHA_VERIFIED_CURRENT_FILE').length;
          const card=E('article',undefined,'nox-owner-report');card.append(E('b',label));
          card.append(E('p','Файлы: '+ready+'/'+rows.length+' проверены · '+size(rows.reduce((n,row)=>n+row.verified_bytes,0))));
          const engine=ready===rows.length&&rows.length>0&&caps?.[kind]===true;
          card.append(E('p',engine?'Движок доступен для генерации.':caps?'Движок сейчас недоступен.':'Доступность движка пока не подтверждена.'));
          const proof=media.generation_acceptance?.[kind];card.append(E('p',proof?.verified===true?'Пробная генерация, декодирование и выдача файла подтверждены.':'Пробная генерация пока не подтверждена.'));
          inventoryBody.append(card);
        }
        const adapters=E('article',undefined,'nox-owner-report');adapters.append(E('b','Адаптеры 3t724u · RAM'));
        adapters.append(E('p',drive.verified_files+'/'+drive.selected_files+' проверены · '+size(drive.verified_bytes)));
        adapters.append(E('p','Перенос не выполняет слияние весов. Включение этих обновлений в текущую модель пока не подтверждено.'));
        adapters.append(E('small','RAM — временная копия; состояние долговременного резерва проверяется отдельно.'));inventoryBody.append(adapters);
        const stamp=new Date(Number(value.observed_at)*1000),verification=verified>0?'Для отмеченных файлов полный SHA проверен при переносе; сейчас сверены идентификаторы.':'Файлы пока не подтверждены квитанциями и текущей проверкой.';
        inventoryBody.append(E('small','Проверено на сервере: '+stamp.toLocaleString()+'. '+verification));
      }catch{inventoryTitle.textContent='Загрузки · нет свежего подтверждения';inventoryBody.replaceChildren(E('p','Текущее состояние файлов недоступно. Проверка продолжится.'));}
      finally{downloadsBusy=false;}
    }
    void refreshDownloads();setInterval(()=>void refreshDownloads(),20000);
    let eventCursor=null,eventsBusy=false,eventCount=0;
    try{const n=Number(localStorage.getItem('nox.owner.events.cursor'));if(Number.isSafeInteger(n)&&n>0)eventCursor=n;}catch{}
    async function refreshEvents(){
      if(eventsBusy||document.hidden)return;eventsBusy=true;
      try{
        const value=await api('/api/ui/events?limit=20'+(eventCursor===null?'':'&cursor='+eventCursor));
        if(value.schema!=='NOX_OWNER_EVENTS_V1'||!Array.isArray(value.events)||!Number.isSafeInteger(value.next_cursor))return;
        for(const event of value.events){
          if(!Number.isSafeInteger(event.sequence)||typeof event.title!=='string'||typeof event.message!=='string')continue;
          if(reportList.querySelector('[data-event-sequence="'+event.sequence+'"]'))continue;
          const card=E('article',undefined,'nox-owner-report');card.dataset.eventSequence=String(event.sequence);
          const heading=E('b',event.title),message=E('p',event.message);
          const when=new Date(Number(event.created_at)*1000);const stamp=E('small',Number.isFinite(when.getTime())?when.toLocaleString():'');
          const task=event.task&&typeof event.task.id==='string'?event.task.id:'';if(task)stamp.textContent+=' · '+task;
          card.append(heading,message,stamp);reportList.append(card);eventCount++;
          while(reportList.childElementCount>60)reportList.firstElementChild.remove();
        }
        eventCursor=value.next_cursor;try{localStorage.setItem('nox.owner.events.cursor',String(eventCursor));}catch{}
        const nextTitle=eventCount?'Отчёты NOX · '+eventCount:'Отчёты NOX · ожидаю события';
        if(reportTitle.textContent!==nextTitle)reportTitle.textContent=nextTitle;
      }catch{if(!eventCount)reportTitle.textContent='Отчёты NOX · подключение';}
      finally{eventsBusy=false;}
    }
    void refreshEvents();setInterval(()=>void refreshEvents(),5000);
    const panel=E('section',undefined,'nox-media-panel');panel.hidden=true;panel.setAttribute('aria-label','Фото и видео NOX');
    const title=E('h2','NOX · Фото'),description=E('p','Опишите результат. Генерация выполняется на сервере NOX.'),prompt=E('textarea');prompt.maxLength=1500;prompt.placeholder='Что создать?';
    const row=E('div',undefined,'nox-live-actions'),go=E('button','Создать','nox-live-btn'),cancel=E('button','Остановить','nox-live-btn'),close=E('button','Закрыть','nox-live-btn');
    go.type=cancel.type=close.type='button';cancel.disabled=true;row.append(go,cancel,close);
    const status=E('p','Проверяю движок…','nox-media-status'),output=E('div'),links=E('div',undefined,'nox-media-links');
    panel.append(title,description,prompt,row,status,output,links);document.body.append(panel);
    let kind='image',job=null,poll=null,running=false;
    const names={QUEUED:'Задание в очереди',YIELDING_TRAINING:'Сохраняю обучение и освобождаю GPU',WAITING_RESOURCES:'Ожидаю свободные ресурсы',RUNNING:'Генерирую',SUBMITTING:'Передаю задание движку',CANCEL_REQUESTED:'Остановка запрошена',COMPLETED:'Готово · файл проверен',CANCELLED:'Остановлено',FAILED:'Ошибка генерации',BLOCKED:'Генерация приостановлена'};
    async function availability(){
      go.disabled=true;
      try{const c=await api('/api/ui/media');go.disabled=!c[kind];status.textContent=c[kind]?'Движок доступен.':
        'Движок ещё не готов: '+(c[kind+'_reason']||c.reason||c.state||'идёт установка');}
      catch{status.textContent='Движок ещё подключается. Обновите проверку чуть позже.';}
    }
    async function open(which){kind=which;title.textContent='NOX · '+(kind==='image'?'Фото':'Видео');panel.hidden=false;
      if(!running){output.replaceChildren();links.replaceChildren();prompt.value=document.getElementById('prompt')?.value||'';await availability();}prompt.focus();}
    image.addEventListener('click',()=>void open('image'));video.addEventListener('click',()=>void open('video'));close.addEventListener('click',()=>{panel.hidden=true;});
    function show(result){
      status.textContent=names[result.state]||result.state;
      if(result.reason)status.textContent+='\n'+result.reason;
      if(result.state==='COMPLETED'&&result.generation_verified===true){
        output.replaceChildren();links.replaceChildren();
        for(const file of result.outputs||[]){
          const valid=typeof file.url==='string'&&/^\/api\/ui\/media\/jobs\/[a-f0-9]{32}\/outputs\/\d+$/.test(file.url);
          if(!valid)continue;
          const media=E(kind==='video'?'video':'img');media.src=file.url;
          if(kind==='video'){media.controls=true;media.preload='metadata';}else media.alt='Изображение, созданное NOX';output.append(media);
          const link=E('a','Открыть файл');link.href=file.url;link.target='_blank';link.rel='noopener';links.append(link);
        }
      }
    }
    async function check(){
      if(!job)return;
      try{const value=await api('/api/ui/media/jobs/'+job.id);show(value);
        if(terminal.has(value.state)){running=false;cancel.disabled=true;go.disabled=false;clearInterval(poll);poll=null;}}
      catch{status.textContent='Связь временно недоступна. Проверка продолжится.';}
    }
    go.addEventListener('click',async()=>{
      if(running||!prompt.value.trim())return;go.disabled=true;output.replaceChildren();links.replaceChildren();
      try{job=await api('/api/ui/media/jobs',{kind,prompt:prompt.value.trim()});running=true;cancel.disabled=false;show(job);poll=setInterval(()=>void check(),2500);}
      catch(e){status.textContent='Не удалось запустить: '+e.message;go.disabled=false;}
    });
    cancel.addEventListener('click',async()=>{if(job&&running){cancel.disabled=true;try{show(await api('/api/ui/media/jobs/'+job.id+'/cancel',{}));}catch(e){status.textContent=e.message;cancel.disabled=false;}}});
    async function refresh(){
      if(document.visibilityState==='hidden')return;
      try{const value=await api('/api/ui/executors');chips.replaceChildren();
        if(value.state==='MODEL_UPDATE'||value.state==='HOLD_MAINTENANCE_UNKNOWN'){
          label.textContent=value.state==='MODEL_UPDATE'?'Модель обновляется · состояние процессов требует проверки':'Обслуживание · статус STOP не подтверждён';
          window.dispatchEvent(new CustomEvent('nox:workers',{detail:{online:false,busy:0,state:value.state}}));
          return;
        }
        label.textContent=value.state==='OBSERVED'?'Исполнители · по файлу статуса':'Состояние обновляется';
        window.dispatchEvent(new CustomEvent('nox:workers',{detail:{online:value.state==='OBSERVED',busy:(value.workers||[]).filter(x=>x.status==='busy').length}}));
        for(const [index,worker] of (value.workers||[]).entries()){
          const known=value.state==='OBSERVED',busy=worker.status==='busy';const chip=E('span',String(index+1)+' · '+(known?(busy?'работает':'свободен'):'нет свежих данных'),'nox-live-chip');chip.dataset.state=known&&busy?'busy':'idle';chip.title=worker.task_id||worker.id;chips.append(chip);
        }}catch{label.textContent='Исполнители · нет связи';window.dispatchEvent(new CustomEvent('nox:workers',{detail:{online:false,busy:0}}));}
    }
    void refresh();setInterval(()=>void refresh(),10000);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',attach,{once:true});else attach();
})();
