/* NOX HELION · CINEMA HUD. ECharts source-based speedometer/radar with real-only Windows metrics.
   Runs locally and never changes device state, models, weights or SQLite. */
(()=>{'use strict';
 if(window.NOXCinemaHUD)return;
 const PAGE=document.body.classList.contains('chat-v5')?'chat':document.body.classList.contains('nox-home')?'home':'other';
 const el=(tag,cls,txt)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(txt!==undefined)n.textContent=txt;return n};
 const hud=el('section','cinema-hud'); hud.id='nox-cinema-hud'; hud.setAttribute('aria-label','Живые приборы компьютера');
 const header=el('div','ch-head');header.append(el('span','ch-kicker','NOX / SYSTEM TELEMETRY'));
 const notify=el('button','ch-bell','♧');notify.type='button';notify.title='События и уведомления';notify.setAttribute('aria-label','Открыть уведомления');header.append(notify);hud.append(header);
 const chart=el('div','ch-mainchart');hud.append(chart);
 const labels=el('div','ch-labels');
 const vals={};for(const [key,name] of [['cpu','CPU'],['gpu','GPU'],['ram','RAM']]){
   const c=el('div','ch-value');c.append(el('small','',name));vals[key]=el('strong','','Н/Д');c.append(vals[key]);labels.append(c);
 }hud.append(labels);
 const details=el('div','ch-details');const side={};
 for(const [key,name] of [['temp','TEMP'],['vram','VRAM'],['gpuSource','SENSOR']]){
   const n=el('span','');n.append(el('small','',name));side[key]=el('b','','Н/Д');n.append(side[key]);details.append(n);
 }hud.append(details);
 const message=el('div','ch-message','Датчики ожидают подключение');hud.append(message);
 const drawer=el('div','ch-drawer');drawer.hidden=true;drawer.setAttribute('role','log');hud.append(drawer);
 let chartObj=null, history={cpu:[],gpu:[],ram:[]}, lastOllama=null, lastDanger=false, lastRequest=0;
 function log(txt,push=false){const line=el('div','ch-entry',new Date().toLocaleTimeString('ru-RU')+' · '+txt);drawer.prepend(line);while(drawer.children.length>10)drawer.lastChild.remove();message.textContent=txt;notify.classList.add('has-event');if(push&&'Notification'in window&&Notification.permission==='granted'&&document.hidden){try{new Notification('NOX HELION',{body:txt,tag:'nox-status'})}catch(e){}}}
 notify.onclick=async()=>{drawer.hidden=!drawer.hidden;notify.classList.remove('has-event');if(!drawer.hidden&&'Notification'in window&&Notification.permission==='default'){try{const s=await Notification.requestPermission();log(s==='granted'?'Windows уведомления разрешены':'События остаются внутри NOX')}catch(e){log('Уведомления доступны внутри NOX')}}};
 const container=PAGE==='chat'&&document.querySelector('.details')?document.querySelector('.details'):document.body;
 if(PAGE==='chat')container.prepend(hud);else container.append(hud);
 const gauge=(name,value,x,color)=>({type:'gauge',center:[x,'43%'],radius:'40%',startAngle:205,endAngle:-25,min:0,max:100,splitNumber:5,
   axisLine:{lineStyle:{width:6,color:[[1,'rgba(152,165,171,.13)']]}},progress:{show:value!==null,width:6,roundCap:true,itemStyle:{color}},
   pointer:{show:value!==null,length:'51%',width:2,icon:'path://M0,-1 L1,1 L0,10 L-1,1 Z',itemStyle:{color}},anchor:{show:value!==null,size:5,showAbove:true,itemStyle:{color}},
   axisTick:{distance:-10,length:3,lineStyle:{color:'rgba(208,220,220,.23)',width:1}},splitLine:{distance:-11,length:6,lineStyle:{color:'rgba(220,226,228,.42)',width:1}},axisLabel:{show:false},
   detail:{show:false},title:{show:false},data:[{value:value??0,name}]} );
 const E=window.echarts;
 if(E){try{chartObj=E.init(chart,null,{renderer:'canvas',devicePixelRatio:Math.min(window.devicePixelRatio||1,1.5)}); chartObj.setOption({animationDuration:700,backgroundColor:'transparent',series:[gauge('CPU',null,'17%','#d0a16a'),gauge('GPU',null,'50%','#8fc0cb'),gauge('RAM',null,'83%','#ad99d9')]});}catch(e){chartObj=null}}
 if(!chartObj){chart.classList.add('ch-no-chart');chart.textContent='ECharts · Н/Д';message.textContent='ECharts не загружен — графики недоступны';}
 function val(x){return Number.isFinite(Number(x))?Math.max(0,Math.min(100,Number(x))):null}
 function number(x){return x===null||x===undefined||!Number.isFinite(Number(x))?null:Number(x)}
 function render(raw){
   const c=number(raw.cpu_percent),g=number(raw.gpu_percent),r=number(raw.ram_percent),t=number(raw.cpu_temperature_c),gt=number(raw.gpu_temperature_c);
   vals.cpu.textContent=c===null?'Н/Д':Math.round(c)+'%';vals.gpu.textContent=g===null?'Н/Д':Math.round(g)+'%';vals.ram.textContent=r===null?'Н/Д':Math.round(r)+'%';
   side.temp.textContent=t!==null?t.toFixed(1)+'°C':gt!==null?gt.toFixed(1)+'°C':'Н/Д';
   const vm=number(raw.vram_used_gb),vmt=number(raw.vram_total_gb);
   side.vram.textContent=vm!==null?(vm.toFixed(1)+'/'+(vmt!==null?vmt.toFixed(1):'?')+' GB'):'Н/Д';
   side.gpuSource.textContent=raw.gpu_source||'Н/Д';side.gpuSource.title=raw.gpu_source||'Sensor unavailable';
   if(chartObj){chartObj.setOption({series:[gauge('CPU',c===null?null:val(c),'17%','#d0a16a'),gauge('GPU',g===null?null:val(g),'50%','#8fc0cb'),gauge('RAM',r===null?null:val(r),'83%','#ad99d9')]})}
   const isDanger=t!==null&&t>=85;
   if(isDanger&&!lastDanger)log('ВНИМАНИЕ: CPU '+t.toFixed(1)+' °C. Снизьте вычислительную нагрузку.',true);
   lastDanger=isDanger;
   if(!isDanger)message.textContent='Реальные показатели Windows · '+new Date().toLocaleTimeString('ru-RU');
   hud.classList.toggle('ch-thermal-alert',isDanger);
 }
 async function tick(){
  if(document.hidden)return;
  if(Date.now()-lastRequest<4500)return;
  lastRequest=Date.now();
  try{
    const [a,b]=await Promise.all([fetch('/api/pc-metrics',{cache:'no-store'}),fetch('/api/status',{cache:'no-store'})]);
    if(!a.ok)throw Error('No telemetry endpoint');render(await a.json());
    if(b.ok){const s=await b.json(),online=!!s.ollama_online;if(lastOllama!==null&&lastOllama!==online)log(online?'Ollama подключена':'Ollama недоступна',true);lastOllama=online;}
  }catch(e){message.textContent='Датчики: Н/Д · проверьте локальный сервер';}
 }
 if(typeof ResizeObserver!=='undefined'&&chartObj){new ResizeObserver(()=>chartObj.resize()).observe(chart)}
 if(chartObj)window.addEventListener('resize',()=>chartObj.resize());
 tick();const poll=setInterval(tick,6500);
 window.NOXCinemaHUD={refresh:tick,stop(){clearInterval(poll);chartObj?.dispose()},notify:log};
})();