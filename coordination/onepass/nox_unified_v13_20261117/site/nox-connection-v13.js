/* NOX V13 — evidence-only connection indicator in the canonical HOME navigation.
   It does not assert that workers, models, STOP or GPU are available. No second backend. */
(()=>{'use strict';
 if(window.top!==window.self||window.NOX_CONNECTION_V13)return;
 let chip=null,last='UNKNOWN';
 const local=/^(file:|data:)$/.test(location.protocol);
 const statusMap={pending:['…','ПРОВЕРКА'],ok:['●','API ОТВЕЧАЕТ'],partial:['◐','ОТВЕТ API'],hold:['○','НЕТ СВЯЗИ'],auth:['◌','НУЖЕН ВХОД'],offline:['○','ЛОКАЛЬНЫЙ ФАЙЛ']};
 function present(kind,detail){last=kind; if(!chip)return;const [glyph,label]=statusMap[kind]||statusMap.hold;
  chip.dataset.noxConnection=kind;chip.replaceChildren();
  const mark=document.createElement('span');mark.className='nox-connection-glyph-v13';mark.setAttribute('aria-hidden','true');mark.textContent=glyph;
  const word=document.createElement('span');word.className='nox-connection-word-v13';word.textContent=label;
  chip.append(mark,word);chip.title=detail||label;chip.setAttribute('aria-label','NOX: '+(detail||label));
 }
 let controller=null,token=0;
 async function check(){if(!chip||document.hidden)return;
  if(local){present('offline','Просмотр файла без запущенного NOX. Серверные функции не подтверждены.');return;}
  if(!/^https?:$/.test(location.protocol)){present('hold','Протокол не поддерживает проверку OneHost');return;}
  const seq=++token;controller?.abort();controller=new AbortController();
  const pending=controller;const timer=setTimeout(()=>pending.abort(),4500);
  try{
   const reply=await fetch('/api/nox/status',{cache:'no-store',credentials:'same-origin',headers:{Accept:'application/json'},signal:controller.signal});
   if(seq!==token)return;
   if(reply.status===401||reply.status===403){present('auth','OneHost требует авторизации');return;}
   if(!reply.ok)throw Error('HTTP '+reply.status);
   const ct=reply.headers.get('content-type')||'';if(!/json/i.test(ct))throw Error('Endpoint returned non-JSON');
   const body=await reply.json();
   if(seq!==token)return;
   if(!body||typeof body!=='object'||Array.isArray(body)||!Object.keys(body).length||body.error||body.ok===false)throw Error('OneHost status not verified');
   const explicit=body.ok===true||body.ready===true||['ok','online','healthy','ready'].includes(String(body.status||'').toLowerCase());
   present(explicit?'ok':'partial',explicit?'OneHost API ответил. Работа чата, STOP, GPU и обучения требует отдельной проверки.':'OneHost вернул JSON, но готовность сервисов не подтверждена.');
  }catch(err){if(seq===token)present('hold','OneHost status: '+String(err?.message||err).slice(0,100));}
  finally{clearTimeout(timer);}
 }
 function mount(){const header=document.getElementById('noxSharedHeaderV10');if(!header)return;
  chip=document.createElement('output');chip.className='nox-connection-v13';chip.setAttribute('role','status');chip.setAttribute('aria-live','polite');
  header.appendChild(chip);present('pending');void check();
  setInterval(()=>{if(!document.hidden)void check();},30000);
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)void check();});
 window.NOX_CONNECTION_V13=Object.freeze({version:'13.0',endpoint:'/api/nox/status',getStatus:()=>last,refresh:check,claimsNativeE2E:false});
})();
