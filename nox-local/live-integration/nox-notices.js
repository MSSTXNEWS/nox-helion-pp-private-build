/* One notifications control on top of the original Cinema HUD; no extra telemetry boxes. */
(()=>{'use strict';
function init(){const root=document.getElementById('nox-cinema-hud');if(!root)return;
const head=root.querySelector('.ch-head');if(!head||head.querySelector('[data-nox-push]'))return;
const btn=document.createElement('button');btn.type='button';btn.className='ch-bell';btn.dataset.noxPush='1';btn.textContent='PUSH';btn.title='Подключить Web Push с разрешения пользователя';head.append(btn);
btn.addEventListener('click',async()=>{
  const tell=t=>{const d=root.querySelector('.ch-message');if(d)d.textContent=t;};
  if(!('Notification'in window)||!('serviceWorker'in navigator)||!('PushManager'in window)){tell('Web Push недоступен в этом браузере');return}
  try{
    const stat=await fetch('/api/push/status',{cache:'no-store'});if(!stat.ok)throw Error('API '+stat.status);
    const s=await stat.json();if(s.webpush_server!=='READY'||!s.public_key){tell('Web Push HOLD: сначала локальный VAPID и отправитель');return}
    const perm=await Notification.requestPermission();if(perm!=='granted'){tell('Разрешение на уведомления не предоставлено');return}
    const reg=await navigator.serviceWorker.register('./sw.js');
    function key(s){const pad='='.repeat((4-s.length%4)%4);return Uint8Array.from(atob((s+pad).replace(/-/g,'+').replace(/_/g,'/')),x=>x.charCodeAt(0))}
    let sub=await reg.pushManager.getSubscription();if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:key(s.public_key)});
    const result=await fetch('/api/push/subscribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(sub.toJSON())});
    tell(result.ok?'Web Push: подписка принята; доставка ещё не проверена':'Web Push: сервер отклонил подписку');
  }catch(e){tell('Web Push HOLD: '+e.message)}
 });}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(init,90));else setTimeout(init,90);
})();