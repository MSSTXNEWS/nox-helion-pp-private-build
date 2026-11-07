/* NOX_VOICE_LOCAL_ONLY_V1 · in-browser RU/ES, no cloud STT fallback, no auto-send. */
(()=>{
'use strict';
const form=document.getElementById('chatForm'), prompt=document.getElementById('prompt');
if(!form||!prompt)return;
const panel=document.createElement('div');
panel.className='nox-voice-control';panel.setAttribute('role','group');
panel.setAttribute('aria-label','Локальный голос NOX RU/ES');
const label=document.createElement('label');label.textContent='Язык · ';
const lang=document.createElement('select');lang.setAttribute('aria-label','Язык голоса');
for(const [name,value] of [['Русский','ru-RU'],['Español','es-ES']]){
 const o=document.createElement('option');o.value=value;o.textContent=name;lang.appendChild(o)
}
label.appendChild(lang);
const start=document.createElement('button');start.type='button';start.textContent='🎙 Локальный микрофон';
const stop=document.createElement('button');stop.type='button';stop.textContent='STOP · голос';stop.disabled=true;
const speak=document.createElement('button');speak.type='button';speak.textContent='Озвучить ответ';
const status=document.createElement('span');status.setAttribute('role','status');status.setAttribute('aria-live','polite');status.textContent='Голос выключен';
panel.append(label,start,stop,speak,status);
form.before(panel);
let recognition=null,session=0,lastRecognized='';
function hold(msg){status.textContent=msg;}
function abort(){
 session++;
 const old=recognition;recognition=null;
 try{old?.abort()}catch{}
 start.disabled=false;stop.disabled=true;
}
function available(){
 return window.isSecureContext && (window.SpeechRecognition || window.webkitSpeechRecognition);
}
start.onclick=async()=>{
 if(recognition)return;
 const Ctor=available();
 if(!Ctor || typeof Ctor.available!=='function'){
   hold('NOX_VOICE_LOCAL_STT_UNAVAILABLE_HOLD · облачный сервис запрещён');
   return;
 }
 let id=++session;
 start.disabled=true;stop.disabled=false;
 hold('Проверка установленного локального распознавания '+lang.value);
 try{
   const a=await Ctor.available({langs:[lang.value],processLocally:true});
   if(id!==session)return;
   if(a!=='available'){
     hold('NOX_VOICE_LOCAL_LANGUAGE_NOT_READY_HOLD · '+String(a));
     start.disabled=false;stop.disabled=true;return;
   }
   const r=new Ctor();
   if(!('processLocally' in r)){
     hold('NOX_VOICE_ON_DEVICE_POLICY_HOLD');
     start.disabled=false;stop.disabled=true;return;
   }
   r.processLocally=true;r.lang=lang.value;
   r.continuous=false;r.interimResults=false;r.maxAlternatives=1;
   recognition=r;
   r.onresult=event=>{
     if(id!==session)return;
     const words=String(event.results?.[0]?.[0]?.transcript||'').trim();
     if(!words || words.length>4000){hold('NOX_VOICE_EMPTY_HOLD');return}
     const old=prompt.value;
     if(old.length+words.length+1>32000){hold('NOX_VOICE_PROMPT_LIMIT_HOLD');return}
     prompt.value=old+(old&&!/\s$/.test(old)?' ':'')+words;
     lastRecognized=words;
     hold('Речь распознана локально. Текст сохранён в черновике — SEND отдельно.');
     prompt.focus();
   };
   r.onerror=e=>{if(id===session)hold('NOX_VOICE_STT_HOLD: '+String(e.error||'unknown'))};
   r.onend=()=>{if(id===session){recognition=null;start.disabled=false;stop.disabled=true}};
   r.start();
   hold('Локальная запись началась · '+lang.value+' · STOP отменяет');
 }catch(e){
   if(id===session){
     recognition=null;start.disabled=false;stop.disabled=true;
     hold('NOX_VOICE_LOCAL_ERROR_HOLD: '+String(e.name||'unavailable'));
   }
 }
};
stop.onclick=()=>{abort();hold('STOP · микрофон выключен; текст не отправлен')};
lang.onchange=()=>{abort();hold('Язык '+lang.value+' · микрофон выключен')};
speak.onclick=()=>{
 if(!('speechSynthesis' in window)){hold('NOX_VOICE_TTS_UNAVAILABLE_HOLD');return}
 const messages=[...document.querySelectorAll('#messages .msg.nox .body')];
 const answer=messages.at(-1)?.textContent?.trim()||'';
 if(!answer){hold('Нет ответа для озвучивания');return}
 const voices=speechSynthesis.getVoices();
 const selected=voices.find(v=>v.localService===true && v.lang.toLowerCase()===lang.value.toLowerCase());
 if(!selected){hold('NOX_VOICE_LOCAL_TTS_MISSING_HOLD · '+lang.value);return}
 speechSynthesis.cancel();
 const utterance=new SpeechSynthesisUtterance(answer.slice(0,5000));
 utterance.voice=selected;utterance.lang=lang.value;
 utterance.onerror=()=>hold('NOX_VOICE_TTS_ENGINE_HOLD');
 utterance.onend=()=>hold('Озвучивание завершено');
 speechSynthesis.speak(utterance);
 hold('Локальное озвучивание · '+lang.value);
};
window.addEventListener('pagehide',()=>{abort();try{speechSynthesis.cancel()}catch{}});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&recognition)abort()});
})();
