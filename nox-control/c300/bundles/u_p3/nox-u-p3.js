/* U: живые данные P3 на странице «Система»: шкала голода + статус обучения в шапке, ECharts-карточка (GPU/VRAM/ОЗУ/голод, holdout CE), леджер, инспектор. Данные: /svc/p3st/* (прокси на :18230). Цвета через --ds-*. */
(function(){ if(window.__uP3)return; window.__uP3=1;
 const B='/svc/p3st/';const $=(s,r)=>(r||document).querySelector(s);
 const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
 async function g(p){try{const r=await fetch(B+p,{cache:'no-store'});return r.ok?await r.json():null}catch(e){return null}}
 const css=document.createElement('style');css.textContent=`
#u-p3h{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;margin:-8px 0 8px;font-size:14px;color:var(--ds-ink,#e6e7ea)}
#u-p3h .hg{display:flex;align-items:center;gap:8px;min-height:32px}
#u-p3h .ubar{width:140px;height:10px;border-radius:6px;background:color-mix(in srgb,var(--ds-ink,#e6e7ea) 14%,transparent);overflow:hidden}
#u-p3h .ubar i{display:block;height:100%;width:0;border-radius:6px;background:var(--ds-ok,#6fcf97);transition:width .6s ease,background .6s}
#u-p3h .ubar i.mid{background:var(--ds-acc,#9aa3b2)}#u-p3h .ubar i.hi{background:var(--ds-bad,#eb5757)}
#u-p3h .tr{opacity:.9;max-width:62ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#u-p3c .row{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
#u-p3c .ch{height:220px;min-width:0}#u-p3c .lg{font-size:13px;opacity:.85;margin-top:8px;line-height:1.5}
#u-p3c .ok{color:var(--ds-ok,#6fcf97)}#u-p3c .bad{color:var(--ds-bad,#eb5757)}
@media(max-width:768px){#u-p3h .ubar{width:100px}#u-p3c .ch{height:200px}}`;document.head.appendChild(css);
 let charts={},inited=0;
 function ec(id,opt){const e=$('#'+id);if(!e||!window.echarts)return;let c=charts[id];if(!c){c=charts[id]=echarts.init(e,null,{renderer:'canvas'});new ResizeObserver(()=>c.resize()).observe(e)}c.setOption(opt,true)}
 const cv=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim()||null;
 function colors(){return{acc:cv('--ds-acc')||'#9aa3b2',ink:cv('--ds-ink')||'#e6e7ea',ok:cv('--ds-ok')||'#6fcf97',bad:cv('--ds-bad')||'#eb5757'}}
 function gauge(name,val,max,unit,col,C){return{series:[{type:'gauge',min:0,max:max,radius:'92%',progress:{show:true,width:12,itemStyle:{color:col}},axisLine:{lineStyle:{width:12,color:[[1,'rgba(128,128,128,.22)']]}},axisTick:{show:false},splitLine:{show:false},axisLabel:{show:false},pointer:{show:false},anchor:{show:false},title:{offsetCenter:[0,'62%'],color:C.ink,fontSize:13},detail:{valueAnimation:true,offsetCenter:[0,'8%'],fontSize:24,color:C.ink,formatter:function(v){return Math.round(v)+unit}},data:[{value:val,name:name}]}],animationDuration:700}}
 async function tick(){
  const [L,T,H,Lg,I]=await Promise.all([g('system/live'),g('train/status'),g('hunger'),g('ledger'),g('inspector')]);
  const C=colors();
  const hs=(H&&H.scale_0_100)!=null?H.scale_0_100:(L&&L.hunger&&L.hunger.scale_0_100);
  const bar=$('#u-p3h .ubar i');if(bar&&hs!=null){bar.style.width=Math.max(2,hs)+'%';bar.className=hs>66?'hi':hs>33?'mid':''}
  const hv=$('#u-p3h .hv');if(hv)hv.textContent=hs!=null?(hs+'/100'+(H&&H.hours!=null?' · '+H.hours+' ч':'')+(H&&H.active_search?' · поиск':'')):'нет данных';
  const tr=$('#u-p3h .tr');if(tr){tr.textContent=(T&&T.status_line)||(L&&L.train)||'Обучение: нет данных';tr.title=tr.textContent}
  if(!$('#u-p3c'))return;
  if(L&&L.gpu){const g_=L.gpu;ec('u-g1',gauge('VRAM',Math.round(100*g_.mem_used_mb/g_.mem_total_mb),100,'%',C.acc,C));ec('u-g2',gauge('GPU °C',g_.temp,100,'°',g_.temp>80?C.bad:C.ok,C));ec('u-g3',gauge('ОЗУ',Math.round(100*(1-L.ram_avail_gb/L.ram_total_gb)),100,'%',C.acc,C))}
  if(hs!=null)ec('u-g4',gauge('Голод',hs,100,'',hs>66?C.bad:hs>33?C.acc:C.ok,C));
  if(T&&T.holdout_last){const d=T.holdout_last;ec('u-g5',{grid:{left:44,right:14,top:24,bottom:26},tooltip:{trigger:'axis'},xAxis:{type:'category',data:d.map((_,i)=>i+1),axisLabel:{color:C.ink}},yAxis:{type:'value',scale:true,axisLabel:{color:C.ink},splitLine:{lineStyle:{color:'rgba(128,128,128,.2)'}}},series:[{type:'line',smooth:true,data:d,areaStyle:{opacity:.18},lineStyle:{color:C.acc},itemStyle:{color:C.acc}}].concat(T.holdout_ref!=null?[{type:'line',data:d.map(()=>T.holdout_ref),symbol:'none',lineStyle:{type:'dashed',color:C.bad},tooltip:{show:false}}]:[]),title:{text:'holdout CE (пунктир: эталон)',textStyle:{color:C.ink,fontSize:13},left:6,top:0}})}
  const lg=$('#u-p3lg');if(lg){lg.innerHTML=
   (T?'Шаг <b>'+esc(T.step)+'/'+esc(T.steps_target)+'</b> · loss '+esc(T.loss)+' · выигрыш к эталону '+esc(T.gain_vs_ref)+(T.no_gain?' <span class="bad">нет прироста</span>':'')+'<br>':'')+
   (Lg?'Леджер: '+esc(Lg.entries)+' записей, цепочка '+(Lg.ok?'<span class="ok">цела</span>':'<span class="bad">нарушена на '+esc(Lg.broken_at)+'</span>')+'<br>':'')+
   (I?'Инспектор: '+(I.ok?'<span class="ok">ок</span>':'<span class="bad">замечания</span>')+(I.notes&&I.notes.length?' · '+I.notes.slice(0,3).map(esc).join('; '):'')+'<br>':'')+
   (L&&L.queues?'Очереди: '+esc(JSON.stringify(L.queues))+' · доноры '+esc(L.donor_slots&&L.donor_slots.busy)+'/'+esc(L.donor_slots&&L.donor_slots.n):'')}
 }
 function init(){if(inited)return;inited=1;
  const ph=$('.ph');if(ph){const h=document.createElement('div');h.id='u-p3h';h.innerHTML='<div class="hg"><span>Голод</span><span class="ubar" role="progressbar" aria-label="Шкала голода"><i></i></span><span class="hv">…</span></div><div class="hg tr" aria-live="polite">…</div>';ph.insertAdjacentElement('afterend',h)}
  const grid=document.querySelector('#tiles');if(grid){const s=document.createElement('section');s.className='card c12';s.id='u-p3c';s.innerHTML='<h2>NOX: обучение и ресурсы <span class="r mono">P3 · живые данные</span></h2><div class="row"><div id="u-g1" class="ch"></div><div id="u-g2" class="ch"></div><div id="u-g3" class="ch"></div><div id="u-g4" class="ch"></div></div><div id="u-g5" class="ch" style="margin-top:10px"></div><div id="u-p3lg" class="lg"></div>';grid.insertAdjacentElement('afterend',s)}
  tick();setInterval(function(){if(!document.hidden)tick()},10000)}
 const go=()=>{if(window.echarts)init();else{const s=document.createElement('script');s.src='./vendor/nox-extra/echarts.min.js';s.onload=init;s.onerror=init;document.head.appendChild(s)}};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);else go();
})();
