/* NOX MEDIA CHAT V1: one chat, same-origin OneHost media jobs, no second backend.
 * Assumes existing authenticated /api/ui/media routes and actual engine weights.
 * Never returns synthetic images, clips, completion or GPU telemetry.
 */
(() => {
  'use strict';
  const NAME = 'NOX_MEDIA_CHAT_V1';
  if (window.__NOX_MEDIA_CHAT_V1) return;
  window.__NOX_MEDIA_CHAT_V1 = true;
  const API = '/api/ui/media';
  const PENDING = 'nox-resonance-media-pending-v1';
  const ID = /^[0-9a-f]{32}$/;
  const OUTPUT = /^(\/api\/ui\/media\/jobs\/)([0-9a-f]{32})(\/outputs\/)(\d+)$/;
  const CATEGORIES = { image: 'Изображение', video: 'Видео' };
  const MODES = {image: 'Фото', video: 'Видео'};
  const TERMINAL = new Set(['COMPLETED','FAILED','CANCELLED','BLOCKED']);
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const plain = value => String(value == null ? '' : value).replace(/[\x00-\x1f\x7f]/g, ' ').slice(0, 220);
  const make = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function pendingMedia(value) {
    try {
      if (value === null) sessionStorage.removeItem(PENDING);
      else if (value) sessionStorage.setItem(PENDING, JSON.stringify(value));
      else return JSON.parse(sessionStorage.getItem(PENDING));
    } catch { return null; }
    return null;
  }
  function mediaRequestId() {
    return Array.from(crypto.getRandomValues(new Uint8Array(16)),
      byte => byte.toString(16).padStart(2,'0')).join('');
  }
  async function request(url, options = {}) {
    if (!url.startsWith(API) || new URL(url, location.href).origin !== location.origin) throw Error('HOLD_INVALID_MEDIA_ROUTE');
    const timeout = new AbortController();
    const abort = () => timeout.abort();
    options.signal?.addEventListener('abort', abort, { once: true });
    const timer = setTimeout(abort, 18000);
    try {
      const response = await fetch(url, {credentials:'same-origin', cache:'no-store', ...options,
        signal: timeout.signal, headers: {...(options.headers || {}), 'Accept':'application/json'}});
      let value = null;
      try { value = await response.json(); } catch { throw Error('HOLD_MEDIA_NON_JSON_' + response.status); }
      if (!response.ok) {
        const failure=Error(plain(value?.reason || value?.error || 'HOLD_HTTP_' + response.status));
        failure.status=response.status;
        throw failure;
      }
      return value;
    } catch(e) {
      if (e.name === 'AbortError') throw Error('HOLD_MEDIA_REQUEST_TIMEOUT');
      throw e;
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener('abort', abort);
    }
  }
  function description(state) {
    return ({QUEUED:'В очереди', YIELDING_TRAINING:'Сохраняется checkpoint обучения',
      WAITING_RESOURCES:'Ожидание свободной GPU', RUNNING:'Создаю', SUBMITTING:'Передаю движку',
      CANCEL_REQUESTED:'Останавливаю', COMPLETED:'Готово', CANCELLED:'Остановлено',
      BLOCKED:'Невозможно выполнить', FAILED:'Ошибка'})[state] || plain(state || 'Проверка');
  }
  function prepare() {
    const form = document.getElementById('chatForm');
    const input = document.getElementById('prompt');
    const stream = document.getElementById('messages');
    if (!form || !input || !stream || document.getElementById('noxMediaToolbar')) return;
    let mode = null;
    let active = null;
    let pending = pendingMedia();
    let pendingBody = null;
    if (!pending || typeof pending.requestId !== 'string' || !ID.test(pending.requestId) || !Object.hasOwn(MODES,pending.kind)) pending=null;
    const bar = make('div','nox-media-toolbar');bar.id='noxMediaToolbar';
    bar.setAttribute('aria-label','Создание фото и видео через Резонанс');
    const label=make('span','nox-media-brand','NOX · STUDIO');
    const state=make('span','nox-media-engine','Движки: проверка…');state.setAttribute('role','status');
    const photo=make('button','nox-media-mode','◈ Фото');photo.type='button';photo.dataset.kind='image';photo.setAttribute('aria-pressed','false');
    const video=make('button','nox-media-mode','▣ Видео');video.type='button';video.dataset.kind='video';video.setAttribute('aria-pressed','false');
    const reset=make('button','nox-media-reset','Текст');reset.type='button';reset.setAttribute('aria-pressed','true');
    bar.append(label,reset,photo,video,state);
    form.parentNode.insertBefore(bar, form);
    const setMode = next => {
      mode=next; photo.setAttribute('aria-pressed',String(mode==='image'));
      video.setAttribute('aria-pressed',String(mode==='video'));
      reset.setAttribute('aria-pressed',String(!mode));
      input.placeholder= mode==='image' ? 'Опиши изображение для генерации…'
        : mode==='video' ? 'Опиши сцену будущего видео…' : 'Сообщение NOX…';
      input.focus();
    };
    photo.addEventListener('click',()=>setMode(mode==='image'?null:'image'));
    video.addEventListener('click',()=>setMode(mode==='video'?null:'video'));
    reset.addEventListener('click',()=>setMode(null));
    const bubble = (kind,prompt) => {
      const root=make('section','nox-media-result');root.setAttribute('aria-label', CATEGORIES[kind]);
      const heading=make('div','nox-media-result-header');
      heading.append(make('strong','', 'NOX · '+ CATEGORIES[kind]),make('small','',plain(prompt)));
      const info=make('p','nox-media-status','Проверка движка…');info.setAttribute('role','status');
      const output=make('div','nox-media-output');
      const actions=make('div','nox-media-actions');
      root.append(heading,info,output,actions);stream.appendChild(root);
      root.scrollIntoView({block:'nearest',behavior:'auto'});
      return {root,info,output,actions};
    };
    function addOutput(slot,job,item,index) {
      if (!ID.test(job.id) || !item || typeof item.url !== 'string') throw Error('HOLD_MEDIA_OUTPUT_ID');
      const url=new URL(item.url,location.origin);
      if (url.origin!==location.origin || !OUTPUT.test(url.pathname) || url.pathname!==`${API}/jobs/${job.id}/outputs/${index}` || url.search || url.hash)
        throw Error('HOLD_MEDIA_OUTPUT_URL');
      const isPhoto=job.kind==='image';
      const media=make(isPhoto?'img':'video','nox-media-preview');
      media.src=url.pathname;
      if(isPhoto){media.alt='Сгенерированное NOX изображение';media.loading='lazy';}
      else{media.controls=true;media.preload='metadata';media.playsInline=true;}
      const anchor=make('a','nox-media-download','Открыть файл');
      anchor.href=url.pathname;anchor.target='_blank';anchor.rel='noopener';
      const itemBox=make('div','nox-media-output-item');itemBox.append(media,anchor);
      slot.output.append(itemBox);
    }
    async function watch(job, slot) {
      if(!ID.test(job.id)) throw Error('HOLD_MEDIA_JOB_ID');
      const cancel=make('button','nox-media-cancel','STOP');cancel.type='button';slot.actions.append(cancel);
      cancel.addEventListener('click',async()=>{
        cancel.disabled=true;
        try{await request(`${API}/jobs/${job.id}/cancel`,{method:'POST'});slot.info.textContent='Остановка запрошена';}
        catch(e){slot.info.textContent='STOP: '+plain(e.message);cancel.disabled=false;}
      });
      let pause=1800;let last='';
      const until=Date.now()+36*60*1000;
      try {
        while(Date.now()<until){
          if(document.visibilityState==='hidden')pause=Math.min(8000,pause*1.2);
          const snapshot=await request(`${API}/jobs/${job.id}`);
          if(snapshot.id!==job.id||snapshot.kind!==job.kind)throw Error('HOLD_MEDIA_JOB_SCOPE');
          const message=description(snapshot.state)+' · '+plain(snapshot.reason||'');
          if(message!==last){slot.info.textContent=message;last=message;}
          if(TERMINAL.has(snapshot.state)){
            if(snapshot.state==='COMPLETED'){
              if(snapshot.generation_verified!==true || !Array.isArray(snapshot.outputs) || !snapshot.outputs.length)
                throw Error('HOLD_MEDIA_OUTPUT_NOT_VERIFIED');
              snapshot.outputs.forEach((entry,index)=>addOutput(slot,snapshot,entry,index));
              slot.info.textContent='✓ Проверенный результат · '+snapshot.outputs.length+' файл(ов)';
            }
            pending=null;
            pendingBody=null;
            pendingMedia(null);
            return;
          }
          await sleep(pause);
          pause=Math.min(5000,pause*1.07);
        }
        throw Error('HOLD_MEDIA_POLL_TIMEOUT_CHECK_JOB');
      } finally { cancel.remove(); }
    }
    const postMedia = body => request(API+'/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body});
    async function reconnect(receipt, slot) {
      let job;
      try { job=await request(`${API}/requests/${receipt.requestId}`); }
      catch(error){
        if(error.message!=='MEDIA_JOB_NOT_FOUND'||!pendingBody)throw error;
        job=await postMedia(pendingBody);
      }
      if(!job || !ID.test(job.id) || job.kind!==receipt.kind) throw Error('HOLD_MEDIA_RECEIPT');
      await watch(job,slot);
    }
    function reconnectAction(slot) {
      const retry=make('button','nox-media-reset','Восстановить задачу');retry.type='button';
      slot.actions.append(retry);
      retry.addEventListener('click',async()=>{
        if(active || !pending)return;
        active=true;retry.disabled=true;
        try{await reconnect(pending,slot);retry.remove();}
        catch(error){
          slot.info.textContent=error.message==='MEDIA_JOB_NOT_FOUND'
            ? 'Сервер пока не подтвердил получение запроса.'
            : 'Связь с задачей не восстановлена · '+plain(error.message);
        }
        finally{active=false;retry.disabled=false;}
      });
      return retry;
    }
    function parseInput(raw) {
      let text=raw.trim(),kind=mode;
      let found=/^\s*\/(image|photo|img|video|film)\s*[:\-]?\s*/i.exec(text);
      if(found){kind=/video|film/i.test(found[1])?'video':'image';text=text.slice(found[0].length).trim();}
      else if(!kind){
        found=/^(?:нарисуй|сгенерируй\s+(?:картинку|изображение|фото)|создай\s+(?:картинку|изображение|фото))\s+[:\-]?\s*/i.exec(text);
        if(found){kind='image';text=text.slice(found[0].length).trim();}
        else{
          found=/^(?:сгенерируй\s+видео|создай\s+видео|сделай\s+видеоролик)\s+[:\-]?\s*/i.exec(text);
          if(found){kind='video';text=text.slice(found[0].length).trim();}
        }
      }
      return {kind,prompt:text};
    }
    form.addEventListener('submit',async e=>{
      const raw=input.value;
      const data=parseInput(raw);
      if(!data.kind)return;
      e.preventDefault();e.stopImmediatePropagation();
      if(!data.prompt){state.textContent='Опиши, что создать';return;}
      if(data.prompt.length>2000){state.textContent='Сократи описание до 2000 символов';return;}
      if(active||pending){state.textContent='Заверши или восстанови текущую медиазадачу';return;}
      const slot=bubble(data.kind,data.prompt);
      active=true;
      try{
        const cap=await request(API);
        if(cap[data.kind]!==true)throw Error(cap[data.kind+'_reason']||cap.reason||'HOLD_MEDIA_ENGINE_NOT_READY');
        if(cap.idempotency_v1!==true)throw Error('HOLD_MEDIA_RECONNECT_NOT_SUPPORTED');
        slot.info.textContent='Создаю задачу…';
        const requestId=mediaRequestId();
        const payload={kind:data.kind,prompt:data.prompt,client_request_id:requestId};
        if(data.kind==='image'){payload.width=1024;payload.height=1024;}
        else{payload.width=512;payload.height=320;payload.frames=17;payload.fps=8;}
        pending={requestId,kind:data.kind};pendingMedia(pending);
        pendingBody=JSON.stringify(payload);
        let job;
        try { job=await postMedia(pendingBody); }
        catch(error){
          if([400,401,403,409,415,422].includes(error.status)){
            pending=null;pendingBody=null;pendingMedia(null);
          }
          throw error;
        }
        if(!job||!ID.test(job.id)||job.kind!==data.kind)throw Error('HOLD_MEDIA_RECEIPT');
        input.value='';state.textContent='Задача '+job.id.slice(0,8);
        await watch(job,slot);
      }catch(error){
        slot.info.textContent='HOLD · '+plain(error.message || 'MEDIA_UNKNOWN');
        state.textContent='Медиадвижок не подтвердил результат';
        if(pending)reconnectAction(slot);
      }
      finally{active=false;}
    },true);
    if(pending){
      const slot=bubble(pending.kind,'Восстановление медиазадачи');
      reconnectAction(slot).click();
    }
    request(API).then(cap=>{
      const ok=Object.entries(MODES).filter(([kind])=>cap[kind]===true).map(([,name])=>name);
      state.textContent=ok.length?'Доступно: '+ok.join(' · '):'Медиадвижки: ожидание установки';
      if(cap.image!==true)photo.title=plain(cap.image_reason||cap.reason||'Модель ещё не установлена');
      if(cap.video!==true)video.title=plain(cap.video_reason||cap.reason||'Модель ещё не установлена');
    }).catch(()=>{state.textContent='OneHost · media HOLD (не подключено)';});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',prepare,{once:true});
  else prepare();
})();
