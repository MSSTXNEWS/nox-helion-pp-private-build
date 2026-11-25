echo "C300: k8_f_1"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
cat > nox-k8-ui.css <<'K8EOF'
.k8-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}
.k8-in{min-height:44px;padding:0 12px;border-radius:12px;border:1px solid rgba(255,255,255,.22);background:rgba(0,0,0,.35);color:#efe6df;font-size:14px;box-sizing:border-box;font-family:inherit;min-width:0}
.k8-st{font-size:12px;opacity:.8;margin:6px 0}
.k8-q{font-size:16px;margin:10px 0;min-height:44px;white-space:pre-wrap}
.k8-rt{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:8px 0}
.k8-rt .k4-btn{flex-direction:column;font-size:13px;padding:4px 6px;line-height:1.25}
.k8-rt .k4-btn small{font-size:12px;opacity:.8}
.k8-trk{fill:rgba(255,255,255,.12)}.k8-fil{fill:#e9b465}.k8-fil.warn{fill:#e08a3c}.k8-fil.bad{fill:#d9534f}
.k8-big{fill:#efe6df;font-size:16px;text-anchor:middle}
.k8-ring{display:block;margin:0 auto;width:160px;height:160px}
.k8-days{display:flex;align-items:flex-end;gap:2px;height:48px;margin:8px 0}.k8-days i{flex:1;background:rgba(233,180,101,.6);min-height:2px;border-radius:2px}
.k8-up{color:#6fd49b!important;transition:color 1.2s}.k8-dn{color:#ff8a80!important;transition:color 1.2s}
#k8-night{width:100%;height:auto;border-radius:12px;background:#0b0f1a;display:block}
.k8-chart{width:100%;height:300px}
.k8-ev{overflow:hidden;width:100%}
.k8-ec.k7-snap{overflow:visible;scroll-snap-type:none;display:flex;gap:12px;touch-action:pan-y pinch-zoom}
.k8-ec .k7-card{flex:0 0 min(320px,82%)}
sl-range.k8-rg{--thumb-size:22px;min-height:44px;width:100%}
K8EOF
cat > nox-k8-embla.js <<'K8EOF'
/* K8: карусель карточек №14 на embla-carousel (vendor). API K8embla.api() */
(function(){ if(window.K8embla||!window.K4)return; let api=null;
 async function wrap(box){ if(box._k8)return; box._k8=1;
  await K4.load('./vendor/embla-carousel/embla-carousel.iife.js');
  const g=window.NOX_embla_carousel,E=g&&(typeof g==='function'?g:(g.default||g.EmblaCarousel));
  if(!E||!box.parentNode)return;
  const vp=document.createElement('div');vp.className='k8-ev';box.parentNode.insertBefore(vp,box);vp.appendChild(box);box.classList.add('k8-ec');
  const a=E(vp,{align:'start',dragFree:true,containScroll:'trimSnaps'});api=a;
  const bar=document.createElement('div');bar.className='k8-row';
  bar.innerHTML='<button type="button" class="k4-btn" aria-label="Назад">←</button><button type="button" class="k4-btn" aria-label="Вперёд">→</button>';
  vp.parentNode.insertBefore(bar,vp.nextSibling);
  const b=bar.querySelectorAll('button');b[0].addEventListener('click',function(){a.scrollPrev()});b[1].addEventListener('click',function(){a.scrollNext()});
  const d=document.getElementById('k7-cards-d');if(d)d.addEventListener('sl-after-show',function(){a.reInit()})}
 new MutationObserver(function(){const b=document.getElementById('k7-cs');if(b&&!b._k8)wrap(b)}).observe(document.body,{childList:true,subtree:true});
 window.K8embla={api:function(){return api}};
})();
K8EOF
cat > nox-k8-anki.js <<'K8EOF'
/* K8 №35: карточки повторения с интервалами ts-fsrs (Снова/Трудно/Хорошо/Легко). API K8anki */
(function(){ if(window.K8anki||!window.K4)return;
 const SK='nox.k8.anki';let d,F=null,cur=null,opt=[];
 const pick=function(g,n){return g&&(g[n]||(g.default&&g.default[n]))};
 const SEED=[{id:'s1',q:'Какая клавиша открывает поиск везде?',a:'Alt+F'},{id:'s2',q:'Что показывает NOX, когда ядро занято?',a:'«NOX занят», страницы работают на запасных путях'},{id:'s3',q:'Что делает оценка «Снова» в FSRS?',a:'Карточка вернётся скоро, стабильность падает'}];
 function ld(){try{const j=JSON.parse(localStorage.getItem(SK)||'{}');return{cards:j.cards||{},custom:j.custom||[]}}catch(e){return{cards:{},custom:[]}}}
 function sv(s){localStorage.setItem(SK,JSON.stringify(s))}
 function deck(){const s=ld(),o=SEED.concat(s.custom);K4.tasks().slice(0,10).forEach(function(t){o.push({id:'t'+t.id,q:'Задача: что нужно сделать?',a:t.title})});
  try{JSON.parse(localStorage.getItem('nox.k7.saved')||'[]').slice(0,10).forEach(function(n,i){o.push({id:'n'+i+'_'+String(n.title).length,q:'Какая новость сохранена?',a:n.title})})}catch(e){}return o}
 function rev(c){c.due=new Date(c.due);if(c.last_review)c.last_review=new Date(c.last_review);return c}
 async function lib(){ if(F)return F; await K4.load('./vendor/ts-fsrs/ts-fsrs.iife.js');const T=window.NOX_ts_fsrs;const f=pick(T,'fsrs'),g=pick(T,'generatorParameters'),e=pick(T,'createEmptyCard');
  F=(f&&e)?{f:f(g?g({enable_fuzz:false}):undefined),e:e}:{fb:1};return F}
 function fmt(due,now){const m=Math.round((due-now)/60000);return m<60?Math.max(1,m)+' мин':m<1440?Math.round(m/60)+' ч':Math.round(m/1440)+' дн'}
 function fresh(L,now){return L.fb?{due:new Date(0),reps:0}:L.e(now)}
 async function scan(){const L=await lib(),s=ld(),now=new Date();let best=null,n=0;
  for(const x of deck()){let c=s.cards[x.id];c=c?rev(c):fresh(L,now);if(c.due<=now){n++;if(!best||c.due<best.c.due)best={x:x,c:c}}}
  return{best:best,n:n}}
 function options(c,now){ if(F.fb)return[0,1,3,7].map(function(dd,i){return{g:i+1,card:{due:new Date(+now+(dd?dd*864e5:6e4)),reps:(c.reps||0)+1},t:dd?dd+' дн':'1 мин'}});
  const rec=F.f.repeat(c,now);return[1,2,3,4].map(function(g){return{g:g,card:rec[g].card,t:fmt(rec[g].card.due,now)}})}
 const NM=['Снова','Трудно','Хорошо','Легко'];
 async function render(){const o=d.querySelector('#k8a-b'),r=await scan();cur=r.best;opt=[];d.querySelector('#k8a-c').textContent='К повторению: '+r.n;
  if(!cur){o.innerHTML='<div class="k8-q">На сегодня всё. Добавьте карточку ниже.</div>';return}
  o.innerHTML='<div class="k8-q" id="k8a-q"></div><div class="k8-q" id="k8a-a" hidden></div><div class="k8-row"><button type="button" class="k4-btn" id="k8a-sh">Показать ответ</button><button type="button" class="k4-btn" id="k8a-ai">Подсказка ИИ</button></div><div class="k8-rt" id="k8a-rt" hidden></div><div class="k8-st" id="k8a-o"></div>';
  o.querySelector('#k8a-q').textContent=cur.x.q;o.querySelector('#k8a-a').textContent=cur.x.a;
  o.querySelector('#k8a-sh').addEventListener('click',reveal);
  o.querySelector('#k8a-ai').addEventListener('click',function(){K4.ask('Кратко объясни для запоминания: '+cur.x.q+' — '+cur.x.a,o.querySelector('#k8a-o'))})}
 function reveal(){ if(!cur)return false;const o=d.querySelector('#k8a-b');opt=options(cur.c,new Date());
  o.querySelector('#k8a-a').hidden=false;const rt=o.querySelector('#k8a-rt');rt.hidden=false;rt.innerHTML='';
  opt.forEach(function(p,i){const b=document.createElement('button');b.type='button';b.className='k4-btn';b.innerHTML=NM[i]+'<small>'+p.t+'</small>';b.addEventListener('click',function(){rate(p.g)});rt.appendChild(b)});return true}
 async function rate(g){ if(!cur||!opt.length)return false;const p=opt.filter(function(x){return x.g===g})[0];if(!p)return false;const s=ld();s.cards[cur.x.id]=p.card;sv(s);await render();return true}
 async function open(){ if(!d){d=K4.modal('k8-anki-d','Карточки повторения');
   d.innerHTML='<div class="k8-st" id="k8a-c"></div><div id="k8a-b"></div><div class="k8-row"><input id="k8a-nq" class="k8-in" style="flex:1;min-width:120px" aria-label="Вопрос" placeholder="Вопрос"><input id="k8a-na" class="k8-in" style="flex:1;min-width:120px" aria-label="Ответ" placeholder="Ответ"><button type="button" class="k4-btn" id="k8a-add">Добавить</button></div>';
   d.querySelector('#k8a-add').addEventListener('click',function(){const q=d.querySelector('#k8a-nq'),a=d.querySelector('#k8a-na');if(!q.value.trim()||!a.value.trim())return;const s=ld();s.custom.push({id:'c'+Date.now(),q:q.value.trim(),a:a.value.trim()});sv(s);q.value='';a.value='';render()})}
  d.show();await lib();await render()}
 K4.fab('k8-anki-b','Повторить','cards',open);
 window.K8anki={open:open,reveal:reveal,rate:rate,intervals:function(){return opt.map(function(p){return p.t})},stats:async function(){const r=await scan();return{due:r.n,lib:F&&!F.fb?'ts-fsrs':'fallback'}}};
})();
K8EOF
cat > nox-k8-budget.js <<'K8EOF'
/* K8 №31: круговой «бюджет месяца» с остатком по дням (d3-shape). API K8budget */
(function(){ if(window.K8budget||!window.K4)return;
 const SK='nox.k8.budget';let d,A=null;
 const pick=function(g,n){return g&&(g[n]||(g.default&&g.default[n]))};
 function ld(){try{const j=JSON.parse(localStorage.getItem(SK)||'{}');return{limit:+j.limit||0,items:Array.isArray(j.items)?j.items:[]}}catch(e){return{limit:0,items:[]}}}
 function sv(s){localStorage.setItem(SK,JSON.stringify(s))}
 const rub=function(v){return Math.round(v).toLocaleString('ru-RU')+' ₽'};
 function stat(){const s=ld(),m=K4.ymd(new Date()).slice(0,7),it=s.items.filter(function(x){return String(x.d).slice(0,7)===m});
  const spent=it.reduce(function(a,x){return a+(+x.a||0)},0),n=new Date(),dim=new Date(n.getFullYear(),n.getMonth()+1,0).getDate(),left=dim-n.getDate()+1,rest=s.limit-spent;
  return{limit:s.limit,spent:spent,rest:rest,days:left,perDay:left>0?rest/left:rest,pct:s.limit?Math.min(1,spent/s.limit):0,dim:dim,it:it}}
 function arc(p){const e=Math.min(.9999,Math.max(0,p))*Math.PI*2;
  if(A)return A().innerRadius(50).outerRadius(64).startAngle(0).endAngle(e)();
  const R=64,r=50,x=function(a,q){return(q*Math.sin(a)).toFixed(2)},y=function(a,q){return(-q*Math.cos(a)).toFixed(2)},l=e>Math.PI?1:0;
  return'M'+x(0,R)+' '+y(0,R)+'A'+R+' '+R+' 0 '+l+' 1 '+x(e,R)+' '+y(e,R)+'L'+x(e,r)+' '+y(e,r)+'A'+r+' '+r+' 0 '+l+' 0 '+x(0,r)+' '+y(0,r)+'Z'}
 function answer(q){const t=stat();if(!t.limit)return'Сначала задайте бюджет месяца.';q=q.toLowerCase();
  if(/остал|хватит|можно/.test(q))return'Осталось '+rub(Math.max(0,t.rest))+(t.rest<0?' (перерасход '+rub(-t.rest)+')':'')+', это около '+rub(Math.max(0,t.perDay))+' в день на '+t.days+' дн.';
  if(/потрат|расход/.test(q))return'Потрачено '+rub(t.spent)+' из '+rub(t.limit)+' ('+Math.round(t.pct*100)+'%).';return null}
 function draw(){if(!d)return;const t=stat(),f=d.querySelector('#k8b-f'),tx=d.querySelector('#k8b-t');d.querySelector('#k8b-tr').setAttribute('d',arc(1));
  f.setAttribute('d',arc(t.pct));f.setAttribute('class','k8-fil'+(t.pct>=.9?' bad':t.pct>=.7?' warn':''));
  tx.textContent=t.limit?Math.round(t.pct*100)+'%':'—';
  d.querySelector('#k8b-s').textContent=t.limit?'Остаток '+rub(t.rest)+' · около '+rub(Math.max(0,t.perDay))+' в день · дней '+t.days:'Задайте бюджет месяца';
  const by={};t.it.forEach(function(x){const k=+String(x.d).slice(8,10);by[k]=(by[k]||0)+(+x.a||0)});const mx=Math.max.apply(null,[1].concat(Object.values(by)));
  let h='';for(let i=1;i<=t.dim;i++)h+='<i title="'+i+'" style="height:'+Math.round((by[i]||0)/mx*100)+'%"></i>';d.querySelector('#k8b-days').innerHTML=h;
  d.querySelector('#k8b-l').value=t.limit||''}
 async function open(){ if(!d){await K4.load('./vendor/d3-shape/d3-shape.iife.js');A=pick(window.NOX_d3_shape,'arc')||null;d=K4.modal('k8-budget-d','Бюджет месяца');
   d.innerHTML='<svg class="k8-ring" viewBox="-70 -70 140 140" role="img" aria-label="Бюджет месяца"><path id="k8b-tr" class="k8-trk"></path><path id="k8b-f" class="k8-fil"></path><text id="k8b-t" class="k8-big" y="6"></text></svg><div id="k8b-s" class="k8-st" aria-live="polite"></div><div id="k8b-days" class="k8-days" aria-label="Траты по дням"></div>'+
   '<div class="k8-row"><input id="k8b-l" type="number" min="0" inputmode="numeric" class="k8-in" aria-label="Бюджет месяца" placeholder="Бюджет, ₽"><button type="button" class="k4-btn" id="k8b-sl">Задать</button></div>'+
   '<div class="k8-row"><input id="k8b-a" type="number" min="0" inputmode="numeric" class="k8-in" aria-label="Сумма" placeholder="Сумма" style="width:110px"><input id="k8b-n" class="k8-in" aria-label="На что" placeholder="На что" style="flex:1;min-width:100px"><button type="button" class="k4-btn" id="k8b-ad">Добавить</button></div>'+
   '<div class="k8-row"><input id="k8b-q" class="k8-in" aria-label="Вопрос" placeholder="сколько осталось" style="flex:1;min-width:140px"><button type="button" class="k4-btn" id="k8b-qg">Спросить</button></div><div id="k8b-o" class="k8-st" aria-live="polite"></div>';
   d.querySelector('#k8b-sl').addEventListener('click',function(){setLimit(d.querySelector('#k8b-l').value)});
   d.querySelector('#k8b-ad').addEventListener('click',function(){const a=d.querySelector('#k8b-a'),n=d.querySelector('#k8b-n');if(add(a.value,n.value)){a.value='';n.value=''}});
   const go=function(){const q=d.querySelector('#k8b-q'),o=d.querySelector('#k8b-o');if(!q.value.trim())return;ask(q.value,o)};
   d.querySelector('#k8b-qg').addEventListener('click',go);d.querySelector('#k8b-q').addEventListener('keydown',function(e){if(e.key==='Enter')go()})}
  d.show();draw()}
 function setLimit(v){const s=ld();s.limit=Math.max(0,+v||0);sv(s);draw();return s.limit}
 function add(a,n){a=+a;if(!(a>0))return false;const s=ld();s.items.push({d:K4.ymd(new Date()),a:a,n:String(n||'').slice(0,60)});sv(s);draw();return true}
 function ask(q,el){const r=answer(q);if(r){el.textContent=r;return r}const t=stat();K4.ask('Бюджет месяца: лимит '+t.limit+' ₽, потрачено '+t.spent+' ₽, дней осталось '+t.days+'. Вопрос: '+q,el);return null}
 K4.fab('k8-budget-b','Бюджет месяца','chart-donut',open);
 window.K8budget={open:open,setLimit:setLimit,add:add,stat:stat,answer:answer,ask:ask};
})();
K8EOF
cat > nox-k8-annot.js <<'K8EOF'
/* K8 №19: аннотации на графике трат: вертикальные линии событий (echarts markLine). API K8annot */
(function(){ if(window.K8annot||!window.K4)return;
 const MK='nox.k8.marks',BK='nox.k8.budget';let d,ch=null;
 function marks(){try{const j=JSON.parse(localStorage.getItem(MK)||'[]');return Array.isArray(j)?j:[]}catch(e){return[]}}
 function items(){try{return(JSON.parse(localStorage.getItem(BK)||'{}').items||[])}catch(e){return[]}}
 function opt(){const n=new Date(),m=K4.ymd(n).slice(0,7),dim=new Date(n.getFullYear(),n.getMonth()+1,0).getDate(),days=[],cum=[];let c=0;
  const by={};items().forEach(function(x){if(String(x.d).slice(0,7)===m){const k=+String(x.d).slice(8,10);by[k]=(by[k]||0)+(+x.a||0)}});
  for(let i=1;i<=dim;i++){c+=by[i]||0;days.push(String(i));cum.push(i<=n.getDate()?c:null)}
  const ml=marks().filter(function(x){return String(x.d).slice(0,7)===m}).map(function(x){return{xAxis:String(+String(x.d).slice(8,10)),label:{formatter:String(x.t).slice(0,24),fontSize:12,color:'#efe6df',position:'insideEndTop'}}});
  return{animation:false,textStyle:{fontSize:12,color:'#efe6df'},grid:{left:52,right:16,top:20,bottom:28},xAxis:{type:'category',data:days,axisLabel:{fontSize:12,color:'#efe6df'}},yAxis:{type:'value',axisLabel:{fontSize:12,color:'#efe6df'}},
   series:[{type:'line',data:cum,smooth:true,showSymbol:false,lineStyle:{color:'#e9b465'},areaStyle:{color:'rgba(233,180,101,.2)'},markLine:{symbol:'none',lineStyle:{color:'#d9534f',type:'dashed'},data:ml}}]}}
 function draw(){ if(!d||!window.echarts)return;const el=d.querySelector('#k8x-c');if(!ch||ch.isDisposed&&ch.isDisposed())ch=echarts.init(el);ch.setOption(opt(),true);ch.resize();
  d.querySelector('#k8x-s').textContent='Событий в этом месяце: '+opt().series[0].markLine.data.length}
 async function open(){ if(!d){await K4.load('./vendor/echarts/echarts.min.js');d=K4.modal('k8-annot-d','Траты и события');
   d.innerHTML='<div id="k8x-c" class="k8-chart" role="img" aria-label="График трат с событиями"></div><div id="k8x-s" class="k8-st"></div><div class="k8-row"><input id="k8x-d" type="date" class="k8-in" aria-label="Дата"><input id="k8x-t" class="k8-in" aria-label="Событие" placeholder="Событие" style="flex:1;min-width:120px"><button type="button" class="k4-btn" id="k8x-a">Пометить</button></div><div class="k8-st">График строится из трат в «Бюджет месяца».</div>';
   d.querySelector('#k8x-d').value=K4.ymd(new Date());
   d.querySelector('#k8x-a').addEventListener('click',function(){add(d.querySelector('#k8x-d').value,d.querySelector('#k8x-t').value)&&(d.querySelector('#k8x-t').value='')});
   d.addEventListener('sl-after-show',function(){setTimeout(draw,50)})}
  d.show();setTimeout(draw,350)}
 function add(dt,t){ if(!dt||!String(t||'').trim())return false;const a=marks();a.push({d:dt,t:String(t).trim()});localStorage.setItem(MK,JSON.stringify(a));draw();return true}
 K4.fab('k8-annot-b','События на графике','chart-line',open);
 window.K8annot={open:open,add:add,marks:marks,chart:function(){return ch}};
})();
K8EOF
cat > nox-k8-tick.js <<'K8EOF'
/* K8 №30: цифры «тикают» барабаном при изменении (финансы), зелёный/красный отблеск. API K8tick */
(function(){ if(window.K8tick)return;
 const RX=/^([−-]?)(\d[\d\s .,]*)(\s?(?:%|₽|\$|€))?$/;let root=null,tm=0;
 function parse(t){const m=RX.exec(String(t).trim());if(!m)return null;const v=parseFloat(m[2].replace(/[\s ]/g,'').replace(',','.'));if(isNaN(v))return null;return{v:(m[1]?-1:1)*v,suf:m[3]||'',dec:(m[2].split(/[.,]/)[1]||'').length}}
 function fmt(v,p){return(v<0?'−':'')+Math.abs(v).toLocaleString('ru-RU',{minimumFractionDigits:p.dec,maximumFractionDigits:p.dec})+p.suf}
 function roll(el,to,p,from,ms){p=p||parse(el.textContent)||{dec:0,suf:''};from=from!=null?from:(el._k8v||0);ms=ms||700;el._k8a=true;const t0=performance.now();
  el.classList.remove('k8-up','k8-dn');el.classList.add(to>=from?'k8-up':'k8-dn');
  (function step(n){const k=Math.min(1,(n-t0)/ms),e=1-Math.pow(1-k,3);el.textContent=fmt(from+(to-from)*e,p);
   if(k<1)requestAnimationFrame(step);else{el.textContent=fmt(to,p);el._k8v=to;el._k8a=false;setTimeout(function(){el.classList.remove('k8-up','k8-dn')},1200)}})(t0)}
 function scan(){ if(!root)return 0;let n=0;const all=root.querySelectorAll('*');
  for(let i=0;i<all.length&&i<600;i++){const el=all[i];if(el.children.length||el._k8a)continue;const p=parse(el.textContent);if(!p)continue;
   if(el._k8v==null){el._k8v=p.v;continue}if(p.v!==el._k8v){roll(el,p.v,p,el._k8v);n++}}return n}
 K4_ready();function K4_ready(){const go=function(){root=document.getElementById('fiMain')||document.getElementById('page');if(!root)return;scan();
   new MutationObserver(function(){clearTimeout(tm);tm=setTimeout(scan,150)}).observe(root,{childList:true,subtree:true,characterData:true})};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);else setTimeout(go,300)}
 window.K8tick={roll:roll,scan:scan,parse:parse,fmt:fmt,root:function(){return root}};
})();
K8EOF
cat > nox-k8-night.js <<'K8EOF'
/* K8 №25: ночная сторона Земли с терминатором (suncalc), ползунок времени. API K8night */
(function(){ if(window.K8night||!window.K4)return;
 const W=720,H=360,ST=6;let d,gp=null,hrs=0;
 const pick=function(g,n){return g&&(g[n]||(g.default&&g.default[n]))};
 const NODES=[['S1',46.81,-71.21],['S2',39.8,-98.6]];
 function draw(h){hrs=+h||0;const c=d&&d.querySelector('#k8-night');if(!c||!gp)return null;const x=c.getContext('2d'),t=new Date(Date.now()+hrs*36e5);
  x.fillStyle='#16324f';x.fillRect(0,0,W,H);let best=-9,bl=0,bo=0,nt=0,all=0;
  for(let j=0;j<H;j+=ST)for(let i=0;i<W;i+=ST){const lon=-180+(i+ST/2)/W*360,lat=90-(j+ST/2)/H*180,a=gp(t,lat,lon).altitude;all++;if(a>best){best=a;bl=lat;bo=lon}
   const al=a>.05?0:a<-.25?.72:.72*(.05-a)/.3;if(a<0)nt++;if(al>0){x.fillStyle='rgba(2,4,14,'+al.toFixed(2)+')';x.fillRect(i,j,ST,ST)}}
  x.strokeStyle='rgba(255,255,255,.14)';x.lineWidth=1;for(let lo=-180;lo<=180;lo+=30){const px=(lo+180)/360*W;x.beginPath();x.moveTo(px,0);x.lineTo(px,H);x.stroke()}
  for(let la=-60;la<=60;la+=30){const py=(90-la)/180*H;x.beginPath();x.moveTo(0,py);x.lineTo(W,py);x.stroke()}
  const sx=(bo+180)/360*W,sy=(90-bl)/180*H;x.fillStyle='#ffd36b';x.beginPath();x.arc(sx,sy,8,0,6.2832);x.fill();
  x.font='12px sans-serif';x.fillStyle='#efe6df';NODES.forEach(function(n){const px=(n[2]+180)/360*W,py=(90-n[1])/180*H;x.fillStyle='#e9b465';x.beginPath();x.arc(px,py,4,0,6.2832);x.fill();x.fillStyle='#efe6df';x.fillText(n[0],px+7,py+4)});
  const r={sunLat:Math.round(bl),sunLon:Math.round(bo),night:Math.round(nt/all*100),time:t};
  d.querySelector('#k8n-s').textContent='Время '+t.toLocaleString('ru-RU',{hour:'2-digit',minute:'2-digit',day:'2-digit',month:'2-digit'})+' · Солнце над '+r.sunLat+'°, '+r.sunLon+'° · ночь на '+r.night+'% планеты';return r}
 async function open(){ if(!d){await K4.load('./vendor/suncalc/suncalc.iife.js');gp=pick(window.NOX_suncalc,'getPosition');d=K4.modal('k8-night-d','Ночная сторона Земли');
   d.innerHTML='<canvas id="k8-night" width="'+W+'" height="'+H+'" role="img" aria-label="Карта дня и ночи"></canvas><div id="k8n-s" class="k8-st" aria-live="polite"></div><label class="k8-st" for="k8n-r">Сдвиг по времени, часов</label><div id="k8n-w"></div>';
   const w=d.querySelector('#k8n-w');let r;
   if(customElements.get('sl-range')){r=document.createElement('sl-range');r.className='k8-rg';r.min=-12;r.max=24;r.step=1;r.value=0;r.id='k8n-r';r.addEventListener('sl-input',function(){draw(r.value)})}
   else{r=document.createElement('input');r.type='range';r.className='k8-in';r.style.width='100%';r.min=-12;r.max=24;r.step=1;r.value=0;r.id='k8n-r';r.addEventListener('input',function(){draw(r.value)})}
   w.appendChild(r)}
  d.show();draw(hrs)}
 K4.fab('k8-night-b','День и ночь','moon',open);
 window.K8night={open:open,draw:function(h){return draw(h)}};
})();
K8EOF
add(){ f=$1.html; [ -f $f ] || { echo "no $f"; return; }
 grep -q "nox-k8-$2.js" $f && { echo "have $f $2"; return; }
 cp $f $f.bak_k8_$TS; tag=""
 grep -q "nox-k4-core.js" $f || tag="<script src=\"./nox-k4-core.js?v=k4a\" defer></script>"
 grep -q "nox-k8-ui.css" $f || tag="$tag<link rel=\"stylesheet\" href=\"./nox-k8-ui.css?v=k8a\">"
 tag="$tag<script src=\"./nox-k8-$2.js?v=k8a\" defer></script>"
 python3 - "$f" "$tag" <<'PYX'
import sys
f,t=sys.argv[1],sys.argv[2]
s=open(f,encoding='utf-8').read();i=s.rfind('</body>')
open(f,'w',encoding='utf-8').write(s[:i]+t+s[i:] if i>=0 else s+t)
PYX
 echo "added $2 -> $f"; }
# find -> fuse.js (правка K7 с бэкапом)
if ! grep -q "k8fuse" nox-k7-find.js; then cp nox-k7-find.js nox-k7-find.js.bak_k8_$TS
python3 - <<'PYX'
f='nox-k7-find.js';s=open(f,encoding='utf-8').read()
a=" async function search(q){ if(!idx)await build();const w="
new=""" let FZ=null,fz_for=null;
 async function k8fuse(){ if(FZ&&fz_for===idx)return FZ; await K4.load('./vendor/fuse.js/fuse.js.iife.js');const g=window.NOX_fuse_js,C=g&&(typeof g==='function'?g:(g.default||g.Fuse));if(!C)return null;
  FZ=new C(idx,{keys:[{name:'t',weight:2},{name:'x',weight:1},{name:'k',weight:.5}],threshold:.38,ignoreLocation:true,minMatchCharLength:2});fz_for=idx;return FZ}
 async function search(q){ if(!idx)await build();if(!q.trim())return idx.slice(0,10);const F=await k8fuse();if(F)return F.search(q.trim(),{limit:12}).map(function(h){return h.item});return searchOld(q)}
 async function searchOld(q){ if(!idx)await build();const w="""
if a in s and 'k8fuse' not in s:
    open(f,'w',encoding='utf-8').write(s.replace(a,new,1));print('find patched')
else: print('find NOT patched')
PYX
fi
add training anki; add finance budget; add finance annot; add finance tick; add atlas night; add index embla
echo "K8: №35 карточки Anki на ts-fsrs (anki)" >> qa/rework/training.fixed
echo "K8: №31 круговой бюджет месяца (budget)" >> qa/rework/finance.fixed
echo "K8: №19 аннотации на графике (annot)" >> qa/rework/finance.fixed
echo "K8: №30 цифры-барабан (tick)" >> qa/rework/finance.fixed
echo "K8: №25 ночная сторона с терминатором (night)" >> qa/rework/atlas.fixed
echo "K8: №15 find на fuse.js; №14 cards на embla (embla)" >> qa/rework/index.fixed
echo "K8: fuse.js 7.5.0 и embla-carousel 8.6.0 уже в vendor настоящими (26 и 18 КБ), подключены к find и cards" >> vendor/VENDOR_INDEX.md
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 260 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
MB="Math.min(...[...document.querySelectorAll('%s button,%s input')].filter(x=>x.offsetParent!==null&&x.getBoundingClientRect().height>0).map(x=>Math.round(x.getBoundingClientRect().height)))"
T={'training':('K8anki',"""(async()=>{const o={};await K8anki.open();await new Promise(r=>setTimeout(r,500));o.s=await K8anki.stats();o.rev=K8anki.reveal();o.iv=K8anki.intervals();o.rate=await K8anki.rate(3);o.s2=await K8anki.stats();o.minh=%s;return JSON.stringify(o)})()""" % (MB%('#k8-anki-d','#k8-anki-d'))),
 'finance':('K8budget',"""(async()=>{const o={};await K8budget.open();K8budget.setLimit(30000);K8budget.add(1500,'тест');K8budget.add(900,'тест2');o.st=K8budget.stat();o.ans=K8budget.answer('сколько осталось');o.minh=%s;
 await K8annot.open();await new Promise(r=>setTimeout(r,900));K8annot.add(new Date().toISOString().slice(0,10),'событие');o.mk=K8annot.marks().length;o.chart=!!(K8annot.chart()&&K8annot.chart().getOption);
 const e=document.getElementById('fiMain')||document.body;const t=document.createElement('span');t.id='k8t';t.textContent='100';e.appendChild(t);K8tick.scan();t.textContent='250';K8tick.scan();o.tickcls=t.className;await new Promise(r=>setTimeout(r,1000));o.tick=t.textContent;t.remove();return JSON.stringify(o)})()""" % (MB%('#k8-budget-d','#k8-budget-d'))),
 'atlas':('K8night',"""(async()=>{const o={};await K8night.open();await new Promise(r=>setTimeout(r,600));o.a=K8night.draw(0);o.b=K8night.draw(12);o.minh=%s;return JSON.stringify(o)})()""" % (MB%('#k8-night-d','#k8-night-d'))),
 'index':('K7cards',"""(async()=>{const o={};await K7cards.open();await new Promise(r=>setTimeout(r,1500));const c=document.querySelectorAll('#k7-cs .k7-card').length;o.cards=c;const a=window.K8embla&&K8embla.api();o.embla=!!a;if(a){o.slides=a.slideNodes().length;try{a.scrollNext()}catch(e){}}
 const f=await K7find.search('новост');o.find=f.length;const g=await K7find.search('нвости');o.fuzzy=g.length;return JSON.stringify(o)})()""")}
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=[])
    for w,h in((1440,900),(390,844)):
      for pg_ in ('training','finance','atlas','index'):
        if pg_=='index' and w==390: continue
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/%s.html'%pg_,wait_until='domcontentloaded',timeout=40000);await pg.wait_for_function('window.%s'%T[pg_][0],timeout=15000);await pg.wait_for_timeout(1500)
          r=await asyncio.wait_for(pg.evaluate(T[pg_][1]),50);print('QA',w,pg_,r,'errs',errs[:3])
        except Exception as e: print('QA EXC',w,pg_,str(e)[:300],errs[:3])
        await pg.close()
    await b.close()
asyncio.run(m())
QAEOF
echo "K8: пакет 1 (№35 anki, №31 budget, №19 annot, №30 tick, №25 night) + №15 find на fuse.js, №14 cards на embla. Файлы site/nox-k8-<имя>.js, общий nox-k8-ui.css; бэкапы *.bak_k8_<ts>." >> $S/K8_LOG.md
echo "K8 f1 done"
