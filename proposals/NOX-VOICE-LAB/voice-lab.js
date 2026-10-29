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
    let activeOperation=null,captureEpoch=0,capturePending=false,captureOutcome='discard',audioSelection=null;
    function setStatus(msg){status.textContent=msg;}
    function updateMode(){
      // Switching voice mode cancels the old microphone capture, not a hidden send.
      if(mode!==modes.value&&(recorder||capturePending))stopCapture(false);
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
      recorder=null;record.disabled=false;record.textContent='Записать 30 секунд';
      stop.disabled=!activeOperation;
    }
    function stopCapture(submit=false){
      // STOP is a privacy cancellation. Only the explicit Record->Send action
      // or 30-second maximum may submit; MediaRecorder.stop() still emits data.
      if(!recorder){
        if(!submit){captureEpoch++;capturePending=false;captureOutcome='discard';parts=[];stopStream();}
        return false;
      }
      captureOutcome=submit?'submit':'discard';
      if(submit){
        audioSelection={mode,direction:direction.value,level:level.value,
          voiceId:voice.value||null};
        record.disabled=true;stop.disabled=true;
      }else{
        captureEpoch++;parts=[];audioSelection=null;
      }
      const current=recorder;
      if(current.state!=='inactive')current.stop();
      if(!submit)stopStream(); // revoke microphone tracks immediately on STOP
      setStatus(submit?'Завершение записи для отправки':'Запись отменена: звук не передан');
      return true;
    }
    async function startCapture(){
      if(disposed||capturePending||stream||recorder||!navigator.mediaDevices?.getUserMedia||typeof MediaRecorder==='undefined'){
        setStatus('Запись недоступна: требуется HTTPS/разрешение и MediaRecorder');return;
      }
      record.disabled=true;stop.disabled=false;parts=[];
      const epoch=++captureEpoch;
      capturePending=true;captureOutcome='recording';audioSelection=null;
      try{
        const acquired=await navigator.mediaDevices.getUserMedia({
          audio:{echoCancellation:true,noiseSuppression:true},video:false});
        // STOP, navigation, hidden tab and destroy may occur before permission
        // resolves; never reuse a late stream or clobber a newer capture.
        if(disposed||document.hidden||epoch!==captureEpoch){
          acquired.getTracks().forEach(t=>t.stop());
          if(epoch===captureEpoch){capturePending=false;stopStream();}
          return;
        }
        stream=acquired;capturePending=false;
        const types=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/webm'];
        const supported=types.find(x=>MediaRecorder.isTypeSupported(x));
        const current=supported?new MediaRecorder(stream,{mimeType:supported}):new MediaRecorder(stream);
        recorder=current;let size=0;
        current.ondataavailable=e=>{
          if(disposed||epoch!==captureEpoch||captureOutcome==='discard'||!e.data||!e.data.size)return;
          size+=e.data.size;
          if(size>MAX_AUDIO_BYTES){
            stopCapture(false);setStatus('Лимит аудио превышен: запись отменена');return;
          }
          parts.push(e.data);
        };
        current.onstop=()=>{
          const shouldSend=!disposed&&!document.hidden&&epoch===captureEpoch&&
            captureOutcome==='submit'&&!!audioSelection;
          const selection=shouldSend?{...audioSelection}:null;
          const blob=shouldSend?new Blob(parts,{type:current.mimeType||'audio/webm'}):null;
          if(recorder===current){parts=[];audioSelection=null;stopStream();}
          if(selection&&blob.size>0&&blob.size<=MAX_AUDIO_BYTES){
            try{
              Promise.resolve(bridge.onAudio({audio:blob,...selection}))
                .catch(()=>{if(!disposed)setStatus('Ошибка локальной обработки аудио');});
              if(!disposed)setStatus('Аудио передано локальному обработчику NOX');
            }catch{if(!disposed)setStatus('Локальный обработчик отклонил аудио');}
          }
        };
        current.onerror=()=>{
          if(epoch===captureEpoch){stopCapture(false);setStatus('Ошибка микрофона: звук не передан');}
        };
        current.start(250);
        record.disabled=false;record.textContent='Отправить аудио';
        stop.disabled=false;
        timer=setTimeout(()=>{if(epoch===captureEpoch&&recorder===current)stopCapture(true);},MAX_AUDIO_MS);
        setStatus('Запись микрофона · STOP отменяет, «Отправить аудио» отправляет');
      }catch{
        if(epoch===captureEpoch){capturePending=false;stopStream();
          if(!disposed)setStatus('Микрофон недоступен или доступ запрещён');}
      }
    }
    async function dispatch(type,payload){
      try{setStatus('Команда передана локальному NOX');
        const response=await bridge.dispatch(type,payload);
        if(!disposed&&response?.error)setStatus('NOX: '+String(response.error).slice(0,100));
      }catch{if(!disposed)setStatus('Команда отклонена локальным NOX');}
    }
    record.onclick=()=>{if(recorder)stopCapture(true);else startCapture();};
    stop.onclick=()=>{if(recorder||capturePending)stopCapture(false);
      else if(activeOperation)dispatch('nox.voice.stop',{operationId:activeOperation});};
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
    // Changing call details invalidates consent tied to the old quote.
    number.oninput=()=>{consent.checked=false;};
    purpose.oninput=()=>{consent.checked=false;};
    modes.onchange=updateMode;updateMode();
    const visibility=()=>{if(document.hidden&&(recorder||capturePending))stopCapture(false);};
    document.addEventListener('visibilitychange',visibility);
    return Object.freeze({
      setVoices(items){
        voices=Array.isArray(items)?items.filter(x=>x&&VOICE_ID.test(x.id)&&x.installed===true).slice(0,40):[];
        voice.replaceChildren();const none=element('option','','Голос не выбран');none.value='';voice.append(none);
        voices.forEach(x=>{const o=element('option','',String(x.name||x.id).slice(0,100));o.value=x.id;voice.append(o);});
        updateMode();
      },
      setCallProvider(x){
        const label=typeof x?.priceLabel==='string'?x.priceLabel.trim():'';
        // Do not truncate an offered call tariff: a truncated quote is not
        // the full price the user was asked to approve.
        const validQuote=label.length>0&&label.length<=80&&!/[\x00-\x1f\x7f]/.test(label);
        const nextReady=x?.ready===true&&validQuote;
        const nextQuote=nextReady?label:null;
        // Provider quote changes require a fresh explicit user confirmation.
        if(nextQuote!==callPrice||nextReady!==providerReady)consent.checked=false;
        providerReady=nextReady;callPrice=nextQuote;
        cost.textContent=callPrice||'Тариф не определён';
      },
      setResponse(e){
        if(disposed||!e||typeof e!=='object')return;
        if(typeof e.text==='string')output.textContent=e.text.slice(0,12000);
        if(typeof e.status==='string')setStatus(e.status.slice(0,120));
        activeOperation=typeof e.operationId==='string'?e.operationId:null;
        if(activeOperation)stop.disabled=false;
        else if(!recorder&&!capturePending)stop.disabled=true;
      },
      destroy(){
        disposed=true;document.removeEventListener('visibilitychange',visibility);
        stopCapture(false);stopStream();surface.remove();
      }
    });
  }
  return Object.freeze({mount});
});