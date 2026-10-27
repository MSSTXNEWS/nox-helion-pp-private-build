/* NOX V16 VOICE LAB — secondary-screen client only; zero network calls / no LLM duplication.
 * Privileged operations MUST be validated by the existing native host.
 * Audio capture requires a direct user click and browser permission; recording never autostarts.
 */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports) module.exports=api;
  else root.NoxVoiceLab=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const MODES=new Set(['translate','maestro','call']);
  const DIRECTIONS=new Set(['ru-es','es-ru']);
  const LEVELS=new Set(['A1','A2','B1','B2','C1','C2']);
  const VOICE_ID=/^[\w.:-]{1,96}$/;
  const PHONE=/^\+?[0-9 ()-]{5,28}$/;
  const MAX_AUDIO_BYTES=16*1024*1024;
  const MAX_AUDIO_MS=30000;
  function element(tag,cls,text){
    const x=document.createElement(tag);
    if(cls)x.className=cls;
    if(text!==undefined)x.textContent=String(text);
    return x;
  }
  function field(label,control){
    const w=element('label','nox-voice-field');
    w.append(element('span','',label),control);
    return w;
  }
  function select(entries){
    const x=element('select');for(const [value,label] of entries){
      const o=element('option','',label);o.value=value;x.append(o);
    }return x;
  }
  function mount(target,bridge){
    if(typeof document==='undefined'||!target||target.nodeType!==1)throw Error('NOX_VOICE_INVALID_MOUNT');
    if(!bridge||typeof bridge.dispatch!=='function'||typeof bridge.onAudio!=='function')throw Error('NOX_VOICE_TRUSTED_HOST_REQUIRED');
    const surface=element('section','nox-voice-lab nox-cinema-panel');
    surface.setAttribute('aria-label','NOX Voice Lab');
    const head=element('header','nox-voice-head');
    head.append(element('strong','','NOX · VOICE LAB'));
    const status=element('output','nox-voice-status','Не подключено');
    status.setAttribute('aria-live','polite');head.append(status);
    const modes=select([['translate','Переводчик RU↔ES'],['maestro','MAESTRO · Испанский'],['call','Звонки']]);
    const direction=select([['ru-es','Русский → Español'],['es-ru','Español → Русский']]);
    const level=select([...LEVELS].map(x=>[x,x]));
    level.value='A1';
    const voice=select([['','Голос не выбран']]);
    const phrase=element('textarea','nox-voice-phrase');
    phrase.rows=3;phrase.maxLength=4000;phrase.placeholder='Введите текст или используйте микрофон';
    const controls=element('div','nox-voice-settings');
    const modeField=field('Раздел',modes), directionField=field('Направление',direction),
      levelField=field('Уровень ученика',level),voiceField=field('Голос',voice);
    controls.append(modeField,directionField,levelField,voiceField);
    const callSection=element('div','nox-voice-call');callSection.hidden=true;
    const number=element('input');number.type='tel';number.autocomplete='off';number.placeholder='+34 ...';
    const purpose=element('input');purpose.type='text';purpose.maxLength=220;purpose.placeholder='Для чего звонок';
    const consent=element('input');consent.type='checkbox';
    const consentLabel=field('Подтверждаю номер, цель, стоимость и согласие на AI-уведомление',consent);
    const cost=element('div','nox-voice-cost','Тариф не определён');
    callSection.append(field('Номер',number),field('Цель звонка',purpose),cost,consentLabel);
    const buttons=element('div','nox-voice-actions');
    const record=element('button','','Записать 30 секунд');
    const stop=element('button','','STOP');stop.disabled=true;
    const send=element('button','','Выполнить');const replay=element('button','','Озвучить');
    replay.disabled=true;buttons.append(record,stop,send,replay);
    const output=element('output','nox-voice-output','Ответ и статус появятся после подтверждённого события от локального NOX');
    output.setAttribute('aria-live','polite');
    surface.append(head,controls,callSection,phrase,buttons,output);target.append(surface);
    let mode='translate',providerReady=false,callPrice=null,voices=[],recorder=null,stream=null,timer=0,parts=[],disposed=false;
    let activeOperation=null;
    function setStatus(msg){status.textContent=msg;}
    function updateMode(){
      mode=modes.value;callSection.hidden=mode!=='call';
      levelField.hidden=mode!=='maestro';
      directionField.hidden=mode==='call';
      phrase.hidden=mode==='call';
      replay.disabled=voice.value===''||mode==='call';
      send.textContent=mode==='call'?'Набрать с подтверждением':mode==='maestro'?'Ответить учителю':'Перевести';
    }
    function stopStream(){
      if(timer){clearTimeout(timer);timer=0;}
      if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;}
      recorder=null;record.disabled=false;stop.disabled=true;
    }
    function stopCapture(){
      if(!recorder){stopStream();return false;}
      if(recorder.state!=='inactive')recorder.stop();else stopStream();
      setStatus('Остановка записи');return true;
    }
    async function startCapture(){
      if(disposed||stream||recorder||!navigator.mediaDevices?.getUserMedia||typeof MediaRecorder==='undefined'){
        setStatus('Запись недоступна: требуется HTTPS/разрешение и MediaRecorder');return;
      }
      record.disabled=true;parts=[];
      try{
        stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
        if(disposed){stopStream();return;}
        const types=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/webm'];
        const supported=types.find(x=>MediaRecorder.isTypeSupported(x));
        recorder=supported?new MediaRecorder(stream,{mimeType:supported}):new MediaRecorder(stream);
        let size=0;
        recorder.ondataavailable=e=>{
          if(disposed||!e.data||!e.data.size)return;
          size+=e.data.size;
          if(size>MAX_AUDIO_BYTES){parts=[];setStatus('Лимит аудио превышен');stopCapture();return;}
          parts.push(e.data);
        };
        recorder.onstop=()=>{
          const blob=new Blob(parts,{type:recorder?.mimeType||'audio/webm'});
          const audioMode=mode;parts=[];stopStream();
          if(!disposed&&blob.size>0&&blob.size<=MAX_AUDIO_BYTES){
            Promise.resolve(bridge.onAudio({audio:blob,mode:audioMode,direction:direction.value,
              level:level.value,voiceId:voice.value||null})).catch(()=>setStatus('Ошибка локальной обработки аудио'));
            setStatus('Аудио передано локальному обработчику NOX');
          }
        };
        recorder.onerror=()=>{setStatus('Ошибка микрофона');stopStream();};
        recorder.start(250);stop.disabled=false;timer=setTimeout(stopCapture,MAX_AUDIO_MS);
        setStatus('Запись микрофона · максимум 30 секунд');
      }catch{stopStream();setStatus('Микрофон недоступен или доступ запрещён');}
    }
    async function dispatch(type,payload){
      try{setStatus('Команда передана локальному NOX');
        const response=await bridge.dispatch(type,payload);
        if(!disposed&&response?.error)setStatus('NOX: '+String(response.error).slice(0,100));
      }catch{if(!disposed)setStatus('Команда отклонена локальным NOX');}
    }
    record.onclick=startCapture;
    stop.onclick=()=>{if(recorder)stopCapture();else if(activeOperation)dispatch('nox.voice.stop',{operationId:activeOperation});};
    send.onclick=()=>{
      if(mode==='call'){
        if(!providerReady){setStatus('SIP/телефонный провайдер не подключён');return;}
        const num=number.value.trim(),why=purpose.value.trim();
        if(!PHONE.test(num)||why.length<3||!consent.checked||!callPrice){
          setStatus('Нужны номер, цель, подтверждённый тариф и согласие');return;
        }
        dispatch('nox.calls.dial.request',{number:num,purpose:why,quotedPrice:callPrice,
          userConfirmed:true,voiceId:voice.value||null});
        consent.checked=false;return;
      }
      const text=phrase.value.trim();
      if(!text){setStatus('Введите текст или используйте микрофон');return;}
      dispatch(mode==='maestro'?'nox.maestro.text':'nox.translate.text',
       {text,direction:direction.value,level:level.value,voiceId:voice.value||null});
    };
    replay.onclick=()=>{
      const text=output.textContent.trim();
      if(text&&voice.value)dispatch('nox.voice.speak',{text,voiceId:voice.value});
    };
    modes.onchange=updateMode;updateMode();
    const visibility=()=>{if(document.hidden&&recorder)stopCapture();};
    document.addEventListener('visibilitychange',visibility);
    return Object.freeze({
      setVoices(items){
        voices=Array.isArray(items)?items.filter(x=>x&&VOICE_ID.test(x.id)&&x.installed===true).slice(0,40):[];
        voice.replaceChildren();const none=element('option','','Голос не выбран');none.value='';voice.append(none);
        voices.forEach(x=>{const o=element('option','',String(x.name||x.id).slice(0,100));o.value=x.id;voice.append(o);});
        updateMode();
      },
      setCallProvider(x){
        providerReady=x?.ready===true && typeof x?.priceLabel==='string'&&x.priceLabel.length>0;
        callPrice=providerReady?x.priceLabel.slice(0,80):null;cost.textContent=callPrice||'Тариф не определён';
      },
      setResponse(e){
        if(!e||typeof e!=='object')return;
        if(typeof e.text==='string')output.textContent=e.text.slice(0,12000);
        if(typeof e.status==='string')setStatus(e.status.slice(0,120));
        activeOperation=typeof e.operationId==='string'?e.operationId:null;
        if(activeOperation)stop.disabled=false;
        else if(!recorder)stop.disabled=true;
      },
      destroy(){
        disposed=true;document.removeEventListener('visibilitychange',visibility);
        if(recorder)stopCapture();stopStream();surface.remove();
      }
    });
  }
  return Object.freeze({mount});
});