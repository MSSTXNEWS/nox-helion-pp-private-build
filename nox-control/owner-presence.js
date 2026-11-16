/* NOX visual presence. Animation follows real UI/network events, not claimed thought. */
(()=>{
 'use strict';
 if(window.NOX_NATIVE_OWNER!==true||window.__NOX_OWNER_PRESENCE)return;
 window.__NOX_OWNER_PRESENCE=true;
 function attach(){
  const strip=document.querySelector('.nox-live-strip'),main=document.querySelector('.v24-main');
  if(!main)return;
  const box=document.createElement('section');box.className='nox-presence';box.setAttribute('aria-label','Состояние NOX');
  const canvas=document.createElement('canvas');canvas.setAttribute('aria-hidden','true');
  const caption=document.createElement('div');caption.className='nox-presence-caption';
  const title=document.createElement('b');title.textContent='NOX · РЕЗОНАНС';
  const label=document.createElement('span');label.textContent='Проверяю связь…';label.setAttribute('role','status');
  caption.append(title,label);box.append(canvas,caption);
  const style=document.createElement('style');style.textContent=`
   .nox-presence{position:relative;isolation:isolate;min-height:112px;height:clamp(112px,17vh,172px);margin:0 12px 10px;border-radius:18px;overflow:hidden;border:1px solid #d4aa6330;background:radial-gradient(ellipse at 65% 48%,#102842 0%,#0c1723 38%,#080d14 76%);box-shadow:inset 0 0 34px #0008}
   .nox-presence canvas{position:absolute;width:100%;height:100%;inset:0;opacity:.92}
   .nox-presence-caption{position:absolute;left:22px;top:50%;transform:translateY(-50%);display:grid;gap:9px;color:#ddbd85;text-shadow:0 2px 12px #000;font:12px system-ui;pointer-events:none;max-width:45%}
   .nox-presence-caption b{font-size:11px;letter-spacing:.21em;font-weight:600}.nox-presence-caption span{color:#c3d1df;line-height:1.5}
   .nox-presence[data-phase=offline]{filter:saturate(.3)}
   @media(max-width:600px){.nox-presence{margin:0 6px 8px;height:112px}.nox-presence-caption{left:14px;max-width:44%;font-size:11px}.nox-presence-caption b{font-size:9px;letter-spacing:.12em}}
  `;document.head.append(style);if(strip)strip.after(box);else main.prepend(box);
  const ctx=canvas.getContext('2d',{alpha:true});if(!ctx)return;
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
  let width=1,height=1,phase='connecting',busy=0,last=0,frame=0,started=performance.now();
  const labels={connecting:'Проверяю связь…',idle:'На связи · готов к задачам',working:'Выполняю фоновые задачи',waiting:'Обрабатываю запрос',speaking:'Передаю ответ',offline:'Связь временно недоступна',error:'Нужна проверка результата',stopped:'Ответ остановлен',updating:'Модель обновляется · состояние процессов требует проверки',maintenance_unknown:'Обслуживание · STOP требует проверки'};
  function set(next){phase=next;box.dataset.phase=next;label.textContent=labels[next]||labels.idle;if(reduced.matches)draw(performance.now());}
  function resize(){const r=box.getBoundingClientRect(),ratio=Math.min(devicePixelRatio||1,1.5);width=r.width;height=r.height;canvas.width=Math.max(1,Math.round(width*ratio));canvas.height=Math.max(1,Math.round(height*ratio));ctx.setTransform(ratio,0,0,ratio,0,0);draw(performance.now());}
  function draw(now){
   const t=(now-started)/1000,active=phase==='waiting'||phase==='speaking',speed=active?1:.23;
   ctx.clearRect(0,0,width,height);const cx=width*.69,cy=height*.5,base=Math.min(height*.39,width*.19);
   const hue=phase==='speaking'?182:phase==='waiting'?202:phase==='offline'?215:193;
   const glow=ctx.createRadialGradient(cx,cy,0,cx,cy,base*1.85);glow.addColorStop(0,`hsla(${hue},74%,55%,.17)`);glow.addColorStop(.55,'rgba(188,145,80,.045)');glow.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=glow;ctx.fillRect(0,0,width,height);
   ctx.save();ctx.translate(cx,cy);ctx.rotate(t*speed*.055);
   const sectors=active?8:6;
   for(let s=0;s<sectors;s++){
    ctx.save();ctx.rotate(s*Math.PI*2/sectors);
    for(let band=0;band<4;band++){
     ctx.beginPath();
     for(let p=0;p<=45;p++){
      const u=p/45,angle=u*Math.PI*.7+(band*.23)+Math.sin(t*speed*.38)*.12;
      const radius=base*(.2+u*.94)*(1+.085*Math.sin(u*9+t*speed+band));
      const x=Math.cos(angle)*radius,y=Math.sin(angle)*radius*(.48+.13*band);
      if(p===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);
     }
     ctx.strokeStyle=band%2?`hsla(${hue},85%,72%,${active?.16:.09})`:'rgba(225,183,107,.16)';ctx.lineWidth=.7;ctx.stroke();
    }
    ctx.restore();
   }
   for(let i=0;i<180;i++){
    const ring=(i%5+1)/5,a=i*2.399963+t*speed*(.12+.04*(i%3)),pulse=1+.055*Math.sin(t*speed*1.7+i);
    const radius=base*(.17+ring*.94)*pulse,x=Math.cos(a)*radius,y=Math.sin(a)*radius*(.58+.18*Math.cos(i*.13+t*.2));
    const r=.65+(i%11===0?1.1:0)+(active?.25:0);ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);
    ctx.fillStyle=i%4===0?'rgba(240,198,129,.82)':`hsla(${hue},80%,78%,${.28+.36*(.5+.5*Math.sin(t*speed+i))})`;ctx.fill();
   }
   ctx.beginPath();ctx.arc(0,0,base*.13*(1+.07*Math.sin(t*speed*2)),0,Math.PI*2);ctx.strokeStyle='rgba(255,222,164,.7)';ctx.lineWidth=1;ctx.stroke();ctx.restore();
  }
  function tick(now){frame=0;if(document.hidden||reduced.matches)return;const interval=phase==='waiting'||phase==='speaking'?33:66;if(now-last>=interval){last=now;draw(now);}frame=requestAnimationFrame(tick);}
  function resume(){if(!frame&&!document.hidden&&!reduced.matches)frame=requestAnimationFrame(tick);else if(reduced.matches)draw(performance.now());}
  window.addEventListener('nox:native-phase',event=>{const next=event.detail?.phase;if(Object.hasOwn(labels,next))set(next);});
  window.addEventListener('nox:workers',event=>{const value=event.detail||{};busy=Number(value.busy)||0;
   if(value.state==='MODEL_UPDATE'){set('updating');return;}
   if(value.state==='HOLD_MAINTENANCE_UNKNOWN'){set('maintenance_unknown');return;}
   if(phase==='waiting'||phase==='speaking')return;set(value.online?(busy?'working':'idle'):'offline');});
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&frame){cancelAnimationFrame(frame);frame=0;}else resume();});
  reduced.addEventListener?.('change',()=>{if(frame){cancelAnimationFrame(frame);frame=0;}resume();});
  new ResizeObserver(resize).observe(box);resize();resume();
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',attach,{once:true});else attach();
})();
