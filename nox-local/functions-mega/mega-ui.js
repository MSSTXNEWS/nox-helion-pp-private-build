/* NOX LOCAL functional HUD + notification adapter. Existing chat/STOP handlers remain original. */
(()=>{'use strict';
const $=(s,r=document)=>r.querySelector(s);
const p=location.pathname.toLowerCase();const page=p.endsWith('chat.html')?'chat':p.endsWith('training.html')?'training':'home';
const node=(t,c,txt)=>{let n=document.createElement(t);if(c)n.className=c;if(txt!==undefined)n.textContent=txt;return n};
const base=node('section','nox-addons');base.setAttribute('aria-label','NOX живые системные приборы');
const h=node('header');h.append(node('strong','','NOX / LIVE INSTRUMENTS'));
const actions=node('div','nox-notify');
const bell=node('button','','♧');bell.type='button';bell.title='События и разрешения уведомлений';bell.setAttribute('aria-label','Открыть уведомления');actions.append(bell);
const swBtn=node('button','','PUSH');swBtn.title='Подписка Web Push, если поддерживается и настроен VAPID';swBtn.type='button';actions.append(swBtn);h.append(actions);base.append(h);
const dials=node('div','nox-dials');base.append(dials);
for(let i=0;i<3;i++){let g=node('div','nox-dial');dials.append(g)}
const vals=node('div','nox-hud-values','CPU: Н/Д · GPU: Н/Д · RAM: Н/Д · TEMP: Н/Д · VRAM: Н/Д');base.append(vals);
const info=node('div','nox-small','Загрузка реальных датчиков…');base.append(info);
const events=node('div','nox-events');events.hidden=true;events.setAttribute('role','log');base.append(events);
const container=page==='chat'?$('.details')||document.body:page==='training'?$('.training-grid article:last-child')||document.body:document.querySelector('.bottom-dock')||document.querySelector('.panel-bottom')||document.body;
container.append(base);
let chart=null, series=[],lastWarn=false,previousOllama=null;
const chartLib=window.echarts;
if(chartLib){dials.querySelectorAll('.nox-dial').forEach((g,i)=>{chartLib.init(g,null,{renderer:'canvas',devicePixelRatio:Math.min(devicePixelRatio||1,1.5)});});series=[...dials.children].map(g=>chartLib.getInstanceByDom(g))}
else {dials.textContent='ECharts не загружен — диаграммы HOLD';dials.classList.add('nox-small')}
const num=x=>x===null||x===undefined||x===''||!Number.isFinite(Number(x))?null:Number(x);
function gauge(name,value,color){return {animation:true,animationDurationUpdate:500,series:[{type:'gauge',startAngle:210,endAngle:-30,center:['50%','54%'],radius:'92%',min:0,max:100,progress:{show:value!==null,width:7,roundCap:true,itemStyle:{color}},pointer:{show:false},axisLine:{lineStyle:{width:7,color:[[1,'rgba(200,212,218,0.12)']]}},axisTick:{show:true,distance:-12,length:2,lineStyle:{color:'#8e9a9d'}},splitLine:{show:false},axisLabel:{show:false},anchor:{show:false},title:{show:true,fontSize:10,color:'#afb8bb',offsetCenter:[0,'-12%']},detail:{show:true,fontSize:14,color:'#e9e5df',offsetCenter:[0,'19%'],formatter:()=>value===null?'Н/Д':Math.round(value)+'%'},data:[{value:value??0,name}]}]}}
function log(msg,{push=false}={}){const e=node('p','',new Date().toLocaleTimeString('ru-RU')+' · '+msg);events.prepend(e);while(events.children.length>14)events.lastChild.remove();info.textContent=msg;if(push&&'Notification'in window&&Notification.permission==='granted'&&document.hidden){try{new Notification('NOX HELION',{body:msg,tag:'nox-event'})}catch(_){}}}
bell.onclick=async()=>{events.hidden=!events.hidden;if(!events.hidden){if('Notification'in window&&Notification.permission==='default'){try{let r=await Notification.requestPermission();log(r==='granted'?'Уведомления Windows включены':'Без системных уведомлений, журнал работает')}catch(_){log('Системные уведомления недоступны')}}}};
function b64URLtoBytes(s){const pad='='.repeat((4-s.length%4)%4);const raw=atob((s+pad).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from(raw,c=>c.charCodeAt(0))}
swBtn.onclick=async()=>{
  if(!('serviceWorker'in navigator)||!('PushManager'in window)||!('Notification'in window)){log('Web Push недоступен браузеру: HOLD');return}
  try{const registration=await navigator.serviceWorker.register('./sw.js');const r=await fetch('/api/push/status',{cache:'no-store'});const data=await r.json();if(data.webpush_server!=='READY'||!data.public_key){log('Web Push HOLD: серверная доставка и VAPID не настроены');return}
  if((await Notification.requestPermission())!=='granted'){log('Web Push: разрешение не предоставлено');return}
  let sub=await registration.pushManager.getSubscription();if(!sub)sub=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64URLtoBytes(data.public_key)});
  const saved=await fetch('/api/push/subscribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(sub.toJSON())});log(saved.ok?'Web Push подписка сохранена':'Web Push подписка не принята');
  }catch(e){log('Web Push: '+e.message)}
};
async function tick(){if(document.hidden)return;
 try{const [r,s]=await Promise.all([fetch('/api/pc-metrics',{cache:'no-store'}),fetch('/api/status',{cache:'no-store'})]);let x=await r.json();let cpu=num(x.cpu_percent),gpu=num(x.gpu_percent),ram=num(x.ram_percent),temp=num(x.cpu_temperature_c??x.gpu_temperature_c),vram=num(x.vram_used_gb);let vtotal=num(x.vram_total_gb);
 const gs=[['CPU',cpu,'#d9a664'],['GPU',gpu,'#7cb5c3'],['RAM',ram,'#a6a2d8']];series.forEach((g,i)=>g.setOption(gauge(...gs[i]),true));
 vals.textContent=`CPU: ${cpu===null?'Н/Д':cpu+'%'} · GPU: ${gpu===null?'Н/Д':gpu+'%'} · RAM: ${ram===null?'Н/Д':ram+'%'} · TEMP: ${temp===null?'Н/Д':temp+'°C'} · VRAM: ${vram===null?'Н/Д':vram+'/'+(vtotal??'?')+' GB'}`;
 const hot=temp!==null&&temp>=65;if(hot&&!lastWarn)log('Температура 65°C+: проверь нагрузку, обучение автоматически НЕ останавливается',{push:true});lastWarn=hot;
 if(!hot)info.textContent=x.gpu_source||'Локальная телеметрия (недоступные поля: Н/Д)';
 if(s.ok){let o=await s.json(),online=!!o.ollama_online;if(previousOllama!==null&&online!==previousOllama)log(online?'Ollama подключена':'Ollama OFFLINE',{push:true});previousOllama=online;}
 }catch(e){info.textContent='Телеметрия HOLD: '+e.message}
}
setInterval(tick,6500);tick();if('ResizeObserver'in window) new ResizeObserver(()=>series.forEach(g=>g.resize())).observe(dials);
if(page==='training'){
 const slot=node('section','nox-addons');slot.style.marginTop='10px';
 slot.append(node('header','','TRAINER / CHECKPOINTS · READ ONLY'));
 const message=node('div','nox-small','Проверка исходного тренера…');slot.append(message);
 const controls=node('div');controls.style.cssText='display:flex;gap:6px;flex-wrap:wrap;margin-top:9px';
 for(const label of ['START','PAUSE','RESUME','STOP','ROLLBACK']){let b=node('button','',label);b.type='button';b.disabled=true;b.title='HOLD до подтверждённого API существующего тренера';controls.append(b)}
 slot.append(controls);container.append(slot);
 const graph=node('div');graph.style.height='140px';slot.append(graph);
 fetch('/api/training/status').then(x=>x.json()).then(x=>{
  message.textContent=`${x.status} · ${x.reason} · checkpoints: ${x.checkpoints.length}`;
  if(x.log?.samples?.length&&window.echarts){const e=window.echarts.init(graph);e.setOption({backgroundColor:'transparent',textStyle:{color:'#cbd2d7'},xAxis:{type:'category',data:x.log.samples.map((_,i)=>i),axisLabel:{show:false}},yAxis:{type:'value',scale:true},series:[{type:'line',showSymbol:false,smooth:false,data:x.log.samples.map(v=>v.loss??v.train_loss??null),lineStyle:{color:'#d7a164',width:2}}],grid:{top:12,left:55,right:14,bottom:25}})}
 }).catch(e=>message.textContent='Trainer HOLD: '+e.message);
}
window.NOX_ADDONS={notify:log,update:tick};
})();