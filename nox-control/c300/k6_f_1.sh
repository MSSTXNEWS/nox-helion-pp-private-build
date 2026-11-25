echo "C300: k6_f_1"
S=/workspace/nox/web/site; V=$S/vendor; cd $S; TS=$(date +%s)
# reveal css из npm
mkdir -p /tmp/k6v/rv && cd /tmp/k6v/rv && rm -rf package
U=$(curl -fsSL https://registry.npmjs.org/reveal.js/latest | python3 -c "import json,sys;print(json.load(sys.stdin)['dist']['tarball'])"); curl -fsSL "$U" | tar xz
cp package/dist/reveal.css $V/reveal.js/ ; cp package/dist/theme/black.css $V/reveal.js/theme-black.css; cp package/LICENSE $V/reveal.js/LICENSE 2>/dev/null; ls -la $V/reveal.js | awk '{print $5,$9}'; cd $S
# фикс stop в motionlib
python3 - <<'PY'
p='nox-k6-motionlib.js';s=open(p,encoding='utf-8').read()
if "delete el.dataset.lib" not in s:
    s=s.replace("function clean(el){if(!el)return;","function clean(el){if(!el)return;delete el.dataset.lib;",1);open(p,'w',encoding='utf-8').write(s);print('lib fixed')
PY
cat > nox-k6-ui.css <<'K6EOF'
.k6-pop{position:fixed;z-index:60;background:rgba(24,18,18,.97);border:1px solid rgba(255,255,255,.22);border-radius:12px;padding:6px;max-height:40vh;overflow:auto;color:#efe6df;font-size:14px}
.k6-pop button{display:flex;width:100%;min-height:44px;align-items:center;gap:8px;text-align:left;background:none;border:0;border-radius:8px;color:inherit;font-size:14px;padding:0 10px;cursor:pointer}
.k6-pop button[aria-selected=true],.k6-pop button:hover,.k6-pop button:focus-visible{background:rgba(233,180,101,.3);outline:0}
.k6-pop small{font-size:12px;opacity:.7;margin-left:auto}
.k6-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}
.k6-grid .grid-stack-item-content{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.18);border-radius:10px;overflow:auto;padding:8px;font-size:13px;color:#efe6df}
.k6-big{font-size:32px;font-weight:700;line-height:1.2}
.k6-tb{width:100%;border-collapse:collapse;font-size:12px}.k6-tb td{padding:4px;border-bottom:1px solid rgba(255,255,255,.12)}
.k6-cy{width:100%;height:58vh;min-height:300px;border:1px solid rgba(255,255,255,.18);border-radius:10px}
.k6-rv{width:100%;height:50vh;min-height:280px;position:relative;border-radius:10px;overflow:hidden}
.k6-rv .reveal .slides section{font-size:22px;text-align:left}.k6-rv .reveal h2{font-size:30px}
.k6-kar{margin:8px 0;padding:8px;border:1px solid rgba(255,255,255,.18);border-radius:12px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;font-size:14px}
.k6-kar input[type=range]{min-height:44px;flex:1;min-width:140px}
.k6-in{min-height:44px;font-size:14px;padding:0 10px}
K6EOF
cat > nox-k6-mention.js <<'K6EOF'
/* K6 №85: @-упоминания в поле чата (fuse.js + tinykeys). Источники: события/дела (nox.tasks.v1), новости, заметки и контакты (nox.k6.*). Контекст уходит в /api/chat вместе с сообщением. API: K6mention.compose(text) */
(function(){ const ta=document.getElementById('input'); if(!ta||window.K6mention||!window.K4)return;
 const NK='nox.k6.notes.v1',CK='nox.k6.contacts.v1';
 const ls=function(k){try{return JSON.parse(localStorage.getItem(k)||'[]')}catch(e){return[]}};
 let pop,items=[],idx=0,ctx={},fuse=null,news=[];
 K4.news().then(function(a){news=a.slice(0,20).map(function(n){return{k:String(n.title||'').slice(0,60),t:'новость',c:String(n.title||'')+' '+String(n.summary||n.description||'').slice(0,200)}}).filter(function(x){return x.k})});
 function src(){ const d=new Date(),a=[{k:'Сегодня',t:'событие',c:'Сегодня '+d.toLocaleDateString('ru')+', '+d.toLocaleTimeString('ru').slice(0,5)}];
  K4.tasks().forEach(function(t){a.push({k:String(t.title).slice(0,60),t:'событие',c:t.title+(t.due?' ('+t.due+')':'')+(t.date?' '+t.date:'')})});
  ls(NK).forEach(function(n){a.push({k:n.title,t:'заметка',c:n.text})});ls(CK).forEach(function(n){a.push({k:n.name,t:'контакт',c:n.name+' '+(n.info||'')})});return a.concat(news)}
 function close(){if(pop){pop.remove();pop=null}items=[]}
 function paint(){ if(!pop){pop=document.createElement('div');pop.className='k6-pop';pop.id='k6-mn';pop.setAttribute('role','listbox');document.body.appendChild(pop)}
  const r=ta.getBoundingClientRect();pop.style.left=Math.max(8,r.left)+'px';pop.style.width=Math.min(380,window.innerWidth-16)+'px';pop.style.bottom=(window.innerHeight-r.top+6)+'px';
  pop.innerHTML='';items.forEach(function(it,i){const b=document.createElement('button');b.type='button';b.setAttribute('role','option');b.setAttribute('aria-selected',i===idx?'true':'false');b.innerHTML='<span>@'+K4.esc(it.k)+'</span><small>'+it.t+'</small>';
   b.addEventListener('mousedown',function(e){e.preventDefault();pick(i)});pop.appendChild(b)})}
 function query(){ const v=ta.value.slice(0,ta.selectionStart),m=/(^|\s)@([^\s@]*)$/.exec(v);return m?m[2]:null}
 function update(){ const q=query();if(q===null){close();return}
  const all=src();let res;
  if(q&&window.NOX_fuse_js){const F=K4.glob(window.NOX_fuse_js);try{res=new F(all,{keys:['k','c'],threshold:.4}).search(q).map(function(r){return r.item})}catch(e){res=null}}
  if(!res)res=q?all.filter(function(x){return(x.k+x.c).toLowerCase().indexOf(q.toLowerCase())>=0}):all;
  items=res.slice(0,6);if(q)items.push({k:q,t:'новая заметка',c:q,mk:1});idx=0;paint()}
 function pick(i){ const it=items[i];if(!it)return;if(it.mk){const a=ls(NK);a.push({title:it.k,text:it.c});localStorage.setItem(NK,JSON.stringify(a))}
  const pos=ta.selectionStart,v=ta.value,st=v.slice(0,pos).lastIndexOf('@');ta.value=v.slice(0,st)+'@'+it.k+' '+v.slice(pos);const np=st+it.k.length+2;ta.setSelectionRange(np,np);ctx['@'+it.k]=it.c;close();ta.focus();ta.dispatchEvent(new Event('input',{bubbles:true}))}
 function compose(t){ const ks=Object.keys(ctx).filter(function(k){return t.indexOf(k)>=0});if(!ks.length||t.indexOf('[Контекст упоминаний]')>=0)return t;
  return t+'\n\n[Контекст упоминаний]\n'+ks.map(function(k){return '- '+k+': '+ctx[k]}).join('\n')}
 function inject(){ ta.value=compose(ta.value);ctx={}}
 ta.addEventListener('input',update);ta.addEventListener('blur',function(){setTimeout(close,150)});
 ta.addEventListener('keydown',function(e){ if(pop&&(e.key==='Enter'||e.key==='Tab')&&!e.isComposing){e.preventDefault();e.stopImmediatePropagation();pick(idx);return}
  if(!pop&&e.key==='Enter'&&!e.shiftKey&&!e.isComposing)inject()},true);
 const tk=window.NOX_tinykeys&&(window.NOX_tinykeys.tinykeys||window.NOX_tinykeys.default);
 if(tk)tk(ta,{ArrowDown:function(e){if(pop){e.preventDefault();idx=(idx+1)%items.length;paint()}},ArrowUp:function(e){if(pop){e.preventDefault();idx=(idx-1+items.length)%items.length;paint()}},Escape:function(){close()}});
 const f=document.getElementById('form');if(f){f.addEventListener('submit',inject,true);f.addEventListener('click',function(e){if(e.target.closest('button[type=submit],#send,.send'))inject()},true)}
 window.K6mention={compose:compose,items:function(){return items},ctx:function(){return ctx}};
})();
K6EOF
cat > nox-k6-dash.js <<'K6EOF'
/* K6 №86: дашборд из перетаскиваемых панелей (gridstack + echarts): график, таблица, число. Данные /api/pc-metrics. API: K6dash.add('chart'|'table'|'num') */
(function(){ if(window.K6dash||!window.K4)return; const LK='nox.k6.dash.v1'; let grid,d,hist=[],cur={},timer;
 function flat(o,p,r){r=r||{};Object.keys(o||{}).forEach(function(k){const v=o[k];if(typeof v==='number')r[(p?p+'.':'')+k]=v;else if(v&&typeof v==='object'&&(p||'').split('.').length<3)flat(v,(p?p+'.':'')+k,r)});return r}
 async function tick(){ const t0=performance.now();let m={};try{const r=await fetch('/api/pc-metrics',{cache:'no-store'});if(r.ok)m=flat(await r.json())}catch(e){}
  m['latency_ms']=Math.round(performance.now()-t0);cur=m;const k=Object.keys(m)[0];hist.push(m[k]);if(hist.length>40)hist.shift();render()}
 function render(){ if(!d)return;d.querySelectorAll('[data-k6]').forEach(function(e){const t=e.dataset.k6,ks=Object.keys(cur);
  if(t==='num')e.innerHTML='<div class="k6-big">'+(cur[ks[0]]!=null?cur[ks[0]]:'—')+'</div><small>'+K4.esc(ks[0]||'')+'</small>';
  else if(t==='table')e.innerHTML='<table class="k6-tb">'+ks.slice(0,12).map(function(k){return '<tr><td>'+K4.esc(k)+'</td><td>'+cur[k]+'</td></tr>'}).join('')+'</table>';
  else if(t==='chart'&&window.echarts){ if(!e._ch)e._ch=echarts.init(e);e._ch.setOption({animation:false,grid:{left:34,right:8,top:10,bottom:20},xAxis:{type:'category',data:hist.map(function(_,i){return i}),show:false},yAxis:{type:'value'},series:[{type:'line',smooth:true,showSymbol:false,data:hist}],backgroundColor:'transparent'});e._ch.resize()}})}
 function save(){ if(!grid)return;localStorage.setItem(LK,JSON.stringify(grid.engine.nodes.map(function(n){return{t:n.el.querySelector('[data-k6]').dataset.k6,x:n.x,y:n.y,w:n.w,h:n.h}})))}
 function add(t,o){ if(!grid)return;o=o||{};grid.addWidget({x:o.x,y:o.y,w:o.w||4,h:o.h||3,content:'<div data-k6="'+t+'" style="width:100%;height:100%"></div>'});render();save()}
 async function open(){ if(!d){d=K4.modal('k6-dash-d','Дашборд системы');
   d.innerHTML='<div class="k6-row"><button type="button" class="k4-btn" data-a="chart">+ График</button><button type="button" class="k4-btn" data-a="table">+ Таблица</button><button type="button" class="k4-btn" data-a="num">+ Число</button><button type="button" class="k4-btn" data-a="clr">Очистить</button></div><div class="grid-stack k6-grid" id="k6-gs" style="min-height:300px"></div>';
   const l=document.createElement('link');l.rel='stylesheet';l.href='./vendor/gridstack/gridstack.min.css';document.head.appendChild(l);
   await K4.load('./vendor/gridstack/gridstack-all.js');if(!window.echarts)await K4.load('./vendor/echarts/echarts.min.js');
   grid=GridStack.init({column:12,cellHeight:70,margin:6,float:false},d.querySelector('#k6-gs'));grid.on('change resizestop dragstop',function(){save();d.querySelectorAll('[data-k6=chart]').forEach(function(e){e._ch&&e._ch.resize()})});
   let saved=[];try{saved=JSON.parse(localStorage.getItem(LK)||'[]')}catch(e){}if(!saved.length)saved=[{t:'num',x:0,y:0,w:3,h:2},{t:'chart',x:3,y:0,w:5,h:3},{t:'table',x:8,y:0,w:4,h:3}];
   saved.forEach(function(s){add(s.t,s)});
   d.addEventListener('click',function(e){const b=e.target.closest('button[data-a]');if(!b)return;if(b.dataset.a==='clr'){grid.removeAll();save()}else add(b.dataset.a)})}
  d.show();tick();clearInterval(timer);timer=setInterval(function(){d.open?tick():clearInterval(timer)},3000)}
 K4.fab('k6-dash','Дашборд','grid-1x2',open);window.K6dash={open:open,add:add,count:function(){return grid?grid.engine.nodes.length:0}};
})();
K6EOF
cat > nox-k6-mindmap.js <<'K6EOF'
/* K6 №87: карта-ум по теме (cytoscape), узлы раскрываются по касанию, подтемы строит ИИ через K4.ask. API: K6map.build(тема), K6map.count() */
(function(){ if(window.K6map||!window.K4)return; let d,cy,n=0;
 const FB=['Определение','История','Ключевые понятия','Применение','Риски','Источники'];
 async function subs(t){ const el=document.createElement('div');try{await K4.ask('Дай ровно 6 подтем по теме «'+t+'». Каждая подтема на отдельной строке, 1-4 слова, без нумерации и пояснений.',el)}catch(e){}
  const a=String(el.textContent||'').split('\n').map(function(s){return s.replace(/^[\s\-*•\d.)]+/,'').trim()}).filter(function(s){return s.length>1&&s.length<50});return a.length>=3?a.slice(0,6):FB}
 async function expand(id){ const nd=cy.getElementById(id);if(nd.data('open'))return;nd.data('open',1);const a=await subs(nd.data('label'));
  a.forEach(function(s){const i='n'+(++n);cy.add([{data:{id:i,label:s}},{data:{id:'e'+i,source:id,target:i}}])});cy.layout({name:'breadthfirst',directed:true,spacingFactor:1.1,animate:true,animationDuration:250}).run();cy.fit(undefined,30)}
 async function build(t){ await K4.load('./vendor/cytoscape/dist/cytoscape.min.js');const box=d.querySelector('#k6-cy');if(cy)cy.destroy();n=0;
  cy=cytoscape({container:box,elements:[{data:{id:'n0',label:t}}],style:[{selector:'node',style:{label:'data(label)',color:'#fff','font-size':13,'text-valign':'center','background-color':'#7a4b2a','shape':'round-rectangle',width:'label',height:44,padding:'14px','border-width':1,'border-color':'#e9b465'}},{selector:'edge',style:{width:2,'line-color':'#c89a63'}}]});
  cy.on('tap','node',function(e){expand(e.target.id())});await expand('n0')}
 function open(){ if(!d){d=K4.modal('k6-map-d','Карта по теме');d.innerHTML='<div class="k6-row"><input id="k6-mt" class="k4-in k6-in" aria-label="Тема" placeholder="Тема, например: квантовые вычисления" style="flex:1;min-width:200px"><button type="button" class="k4-btn pri" id="k6-mg">Построить</button></div><div class="k4-muted" style="font-size:12px">Коснитесь узла, чтобы раскрыть его.</div><div id="k6-cy" class="k6-cy"></div>';
   d.querySelector('#k6-mg').addEventListener('click',function(){const t=d.querySelector('#k6-mt').value.trim();if(t)build(t)});d.querySelector('#k6-mt').addEventListener('keydown',function(e){if(e.key==='Enter')d.querySelector('#k6-mg').click()})}d.show()}
 K4.fab('k6-map','Карта темы','diagram-3',open);window.K6map={open:function(){open();return d},build:async function(t){open();await build(t)},count:function(){return cy?cy.nodes().length:0}};
})();
K6EOF
cat > nox-k6-slides.js <<'K6EOF'
/* K6 №88: слайды из документа с озвучкой (reveal.js + speechSynthesis). Заголовки и тезисы формирует ИИ (K4.ask), без ответа — делим по абзацам. API: K6slides.make(текст), K6slides.count() */
(function(){ if(window.K6slides||!window.K4)return; let d,rv,say=false;
 function local(t){ return t.split(/\n\s*\n/).map(function(s){return s.trim()}).filter(Boolean).slice(0,12).map(function(p){const ln=p.split('\n');const first=ln[0].replace(/^#+\s*/,'');return{h:first.slice(0,70),b:(ln.length>1?ln.slice(1):p.split(/(?<=[.!?])\s+/).slice(1)).slice(0,4)}})}
 async function parse(t){ const el=document.createElement('div');try{await K4.ask('Сделай из текста 5-8 слайдов. Формат строго: каждая строка = «Заголовок | тезис; тезис; тезис». Без нумерации.\n\n'+t.slice(0,4000),el)}catch(e){}
  const a=String(el.textContent||'').split('\n').filter(function(s){return s.indexOf('|')>0}).map(function(s){const p=s.split('|');return{h:p[0].replace(/^[\s\-*•\d.)]+/,'').trim(),b:p[1].split(';').map(function(x){return x.trim()}).filter(Boolean)}});return a.length>=2?a:local(t)}
 async function make(t){ const sl=await parse(t),box=d.querySelector('#k6-rv');
  box.innerHTML='<div class="reveal"><div class="slides">'+sl.map(function(s){return '<section><h2>'+K4.esc(s.h)+'</h2><ul>'+s.b.map(function(x){return '<li>'+K4.esc(x)+'</li>'}).join('')+'</ul></section>'}).join('')+'</div></div>';
  await K4.load('./vendor/reveal.js/reveal.js.iife.js');const R=K4.glob(window.NOX_reveal_js);rv=new R(box.querySelector('.reveal'),{embedded:true,hash:false,controls:true,progress:true,keyboard:false,touch:true});await rv.initialize();return sl.length}
 function speak(){ if(!say||!rv||!window.speechSynthesis)return;const s=rv.getCurrentSlide();const u=new SpeechSynthesisUtterance(s?s.innerText:'');u.lang='ru-RU';u.onend=function(){if(!say)return;if(rv.isLastSlide()){say=false;return}rv.next();setTimeout(speak,250)};speechSynthesis.cancel();speechSynthesis.speak(u)}
 function open(){ if(!d){d=K4.modal('k6-sl-d','Слайды из документа');d.innerHTML='<label class="k4-muted" for="k6-st">Текст документа</label><textarea id="k6-st" class="k4-in" rows="5" style="width:100%;padding:10px;font-size:14px"></textarea><div class="k6-row"><button type="button" class="k4-btn pri" id="k6-sg">Собрать слайды</button><button type="button" class="k4-btn" id="k6-sp">Озвучить</button><button type="button" class="k4-btn" id="k6-ss">Стоп</button></div><div id="k6-rv" class="k6-rv"></div>';
   d.querySelector('#k6-sg').addEventListener('click',function(){const t=d.querySelector('#k6-st').value.trim();if(t)make(t)});
   d.querySelector('#k6-sp').addEventListener('click',function(){say=true;speak()});d.querySelector('#k6-ss').addEventListener('click',function(){say=false;window.speechSynthesis&&speechSynthesis.cancel()});
   const l=document.createElement('link');l.rel='stylesheet';l.href='./vendor/reveal.js/reveal.css';document.head.appendChild(l);const l2=document.createElement('link');l2.rel='stylesheet';l2.href='./vendor/reveal.js/theme-black.css';document.head.appendChild(l2)}
  const ed=document.getElementById('edCode');const ta=d.querySelector('#k6-st');if(ed&&!ta.value)ta.value=String(ed.value||ed.textContent||'').slice(0,4000);d.show()}
 K4.fab('k6-slides','Слайды','easel',open);window.K6slides={open:function(){open();return d},make:async function(t){open();return make(t)},count:function(){return rv?rv.getTotalSlides():0}};
})();
K6EOF
cat > nox-k6-karaoke.js <<'K6EOF'
/* K6 №89: караоке: ползунок громкости вокала (центр стерео) поверх #mAud. Контекст — Tone (vendor/tone), центр вычитается через mid/side. API: K6kar.setVocal(0..1), K6kar.state() */
(function(){ const au=document.getElementById('mAud'); if(!au||window.K6kar||!window.K4)return; let g=null,on=false,vocal=1;
 async function init(){ if(g)return g;await K4.load('./vendor/tone/tone.iife.js');const T=K4.glob(window.NOX_tone)||window.NOX_tone;const ctx=(T.getContext?T.getContext():T.context).rawContext;
  const src=ctx.createMediaElementSource(au),sp=ctx.createChannelSplitter(2),mg=ctx.createGain(),sg=ctx.createGain(),inv=ctx.createGain(),mx=ctx.createChannelMerger(2),l=ctx.createGain(),r=ctx.createGain(),mid=ctx.createGain(),side=ctx.createGain(),sinv=ctx.createGain();
  l.gain.value=.5;r.gain.value=.5;sinv.gain.value=-.5;src.connect(sp);sp.connect(l,0);sp.connect(r,1);sp.connect(sinv,0);
  const rr=ctx.createGain();rr.gain.value=.5;sp.connect(rr,1);
  l.connect(mg);r.connect(mg);sinv.connect(sg);rr.connect(sg);inv.gain.value=-1;sg.connect(inv);
  mg.connect(mx,0,0);mg.connect(mx,0,1);sg.connect(mx,0,0);inv.connect(mx,0,1);mx.connect(ctx.destination);g={ctx:ctx,mid:mg,side:sg,src:src};return g}
 async function apply(){ const o=await init();if(o.ctx.state==='suspended')try{await o.ctx.resume()}catch(e){}o.mid.gain.value=on?vocal:1;o.side.gain.value=1}
 const bar=document.createElement('div');bar.className='k6-kar';bar.id='k6-kar';
 bar.innerHTML='<button type="button" class="k4-btn" id="k6-kt" aria-pressed="false">Караоке: выкл</button><label for="k6-kr">Вокал</label><input type="range" id="k6-kr" min="0" max="100" value="100" aria-label="Громкость вокала"><span id="k6-kv">100%</span>';
 au.insertAdjacentElement('afterend',bar);
 const bt=bar.querySelector('#k6-kt'),rg=bar.querySelector('#k6-kr'),vv=bar.querySelector('#k6-kv');
 function ui(){bt.textContent='Караоке: '+(on?'вкл':'выкл');bt.setAttribute('aria-pressed',on);vv.textContent=Math.round(vocal*100)+'%';rg.value=Math.round(vocal*100)}
 async function setVocal(v){vocal=Math.max(0,Math.min(1,v));on=true;ui();try{await apply()}catch(e){vv.textContent='недоступно: '+String(e.message||e).slice(0,40)}}
 bt.addEventListener('click',async function(){on=!on;ui();try{await apply()}catch(e){vv.textContent='недоступно'}});
 rg.addEventListener('input',function(){setVocal(rg.value/100)});
 window.K6kar={setVocal:setVocal,state:function(){return{on:on,vocal:vocal,mid:g?g.mid.gain.value:null,side:g?g.side.gain.value:null}}};
})();
K6EOF
add(){ f=$1.html; [ -f $f ] || { echo "no $f"; return; }
 grep -q "nox-k6-$2.js" $f && { echo "have $f $2"; return; }
 cp $f $f.bak_k6_$TS; tag=""
 grep -q "nox-k4-core.js" $f || tag="<script src=\"./nox-k4-core.js?v=k4a\" defer></script>"
 grep -q "nox-k6-ui.css" $f || tag="$tag<link rel=\"stylesheet\" href=\"./nox-k6-ui.css?v=k6a\">"
 tag="$tag<script src=\"./nox-k6-$2.js?v=k6a\" defer></script>"
 python3 - "$f" "$tag" <<'PY'
import sys
f,t=sys.argv[1],sys.argv[2]
s=open(f,encoding='utf-8').read();i=s.rfind('</body>')
open(f,'w',encoding='utf-8').write(s[:i]+t+s[i:] if i>=0 else s+t)
PY
 echo "added $2 -> $f"; }
add chat mention; add system dash; add knowledge mindmap; add pdf slides; add music karaoke
echo "K6: №85 @-упоминания (fuse.js+tinykeys)" >> qa/rework/chat.fixed
echo "K6: №86 дашборд панелей (gridstack+echarts)" >> qa/rework/system.fixed
echo "K6: №87 карта-ум (cytoscape)" >> qa/rework/knowledge.fixed
echo "K6: №88 слайды с озвучкой (reveal.js+speechSynthesis)" >> qa/rework/pdf.fixed
echo "K6: №89 караоке, ползунок вокала (tone)" >> qa/rework/music.fixed
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
$PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
C=[
("chat","""(async()=>{await new Promise(r=>setTimeout(r,1500));const t=document.getElementById('input');t.focus();t.value='привет @';t.setSelectionRange(8,8);t.dispatchEvent(new Event('input',{bubbles:true}));await new Promise(r=>setTimeout(r,300));const p=document.getElementById('k6-mn');const n=p?p.querySelectorAll('button').length:0;const h=p?Math.min(...[...p.querySelectorAll('button')].map(b=>b.getBoundingClientRect().height)):0;p.querySelector('button').dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));const v=t.value;const c=K6mention.compose(v);return JSON.stringify({n,h,v,ok:c.includes('Контекст упоминаний')})})()"""),
("system","""(async()=>{await new Promise(r=>setTimeout(r,1500));document.querySelector('#k4-fab [data-id=k6-dash],#k4-fab button').click();K6dash.open&&0;await K6dash.open();await new Promise(r=>setTimeout(r,1500));const a=K6dash.count();K6dash.add('num');await new Promise(r=>setTimeout(r,500));const d=document.getElementById('k6-dash-d');return JSON.stringify({a,b:K6dash.count(),chart:!!d.querySelector('canvas,svg'),tb:!!d.querySelector('.k6-tb')})})()"""),
("knowledge","""(async()=>{await new Promise(r=>setTimeout(r,1500));await K6map.build('Космос');const a=K6map.count();return JSON.stringify({a})})()"""),
("pdf","""(async()=>{await new Promise(r=>setTimeout(r,1500));const n=await K6slides.make('Введение\\nЭто первый абзац. Он важен.\\n\\nГлава два\\nВторой абзац. Детали тут.\\n\\nИтог\\nКонец. Спасибо.');await new Promise(r=>setTimeout(r,500));return JSON.stringify({n,t:K6slides.count(),sec:document.querySelectorAll('#k6-rv section').length,sp:!!window.speechSynthesis})})()"""),
("music","""(async()=>{await new Promise(r=>setTimeout(r,1500));await K6kar.setVocal(0);await new Promise(r=>setTimeout(r,500));const s=K6kar.state();const b=document.getElementById('k6-kr').getBoundingClientRect().height;return JSON.stringify({s,b,txt:document.getElementById('k6-kv').textContent})})()"""),
]
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
    for w,h in((1440,900),(390,844)):
      for u,js in C:
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/'+u+'.html',wait_until='domcontentloaded',timeout=40000);await pg.wait_for_timeout(2500);r=await pg.evaluate(js)
        except Exception as e: r='EXC '+str(e)[:200]
        print('QA',w,u,r,'errs',len(errs),errs[:2]);await pg.close()
    await b.close()
asyncio.run(m())
QAEOF
echo "K6 f_1 done"
