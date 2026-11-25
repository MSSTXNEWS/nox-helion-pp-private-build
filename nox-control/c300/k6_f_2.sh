echo "C300: k6_f_2"
S=/workspace/nox/web/site; V=$S/vendor; cd $S; TS=$(date +%s)
mkdir -p /tmp/k6v/cm && cd /tmp/k6v/cm && rm -rf package
U=$(curl -fsSL https://registry.npmjs.org/codemirror/5.65.16 | python3 -c "import json,sys;print(json.load(sys.stdin)['dist']['tarball'])"); curl -fsSL "$U" | tar xz
cp package/lib/codemirror.css $V/codemirror/codemirror.css; cp package/LICENSE $V/codemirror/LICENSE 2>/dev/null; ls -la $V/codemirror | awk '{print $5,$9}'; cd $S
cat >> nox-k6-ui.css <<'K6EOF'
.k6-wide::part(panel){--width:min(96vw,1100px)}
.k6-sp{min-height:420px}.k6-sp .grid-stack-item-content{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.18);border-radius:10px;overflow:hidden;display:flex;flex-direction:column}
.k6-sp select{min-height:44px;font-size:14px;background:#201816;color:#efe6df;border:0;border-bottom:1px solid rgba(255,255,255,.18);padding:0 10px}
.k6-sp iframe{flex:1;border:0;width:100%;background:#111}
.k6-live{display:grid;grid-template-columns:1fr 1fr;gap:10px}@media(max-width:700px){.k6-live{grid-template-columns:1fr}}
.k6-live iframe{width:100%;height:42vh;min-height:260px;border:1px solid rgba(255,255,255,.18);border-radius:10px;background:#fff}
.k6-live .CodeMirror{height:42vh;min-height:260px;font-size:13px;border-radius:10px}
.k6-bn{min-height:300px;max-height:50vh;overflow:auto;background:#fff;color:#111;border-radius:10px;padding:8px}
.k6-st{font-size:12px;opacity:.8;min-height:18px}
K6EOF
cat > nox-k6-split.js <<'K6EOF'
/* K6 №90: сплит-вид, два раздела бок о бок (gridstack, iframe). API: K6split.open(a,b), K6split.count() */
(function(){ if(window.K6split||!window.K4)return; const P=[['chat','Чат'],['calendar','Календарь'],['memory','Память'],['music','Музыка'],['photo','Фото'],['assistant','Помощник'],['knowledge','Знания'],['system','Система'],['pdf','PDF'],['studio','Студия'],['index','Главная']];let d,grid;
 function pane(sel){ const el=document.createElement('div');el.className='grid-stack-item';el.innerHTML='<div class="grid-stack-item-content"><select class="k6-in" aria-label="Раздел">'+P.map(function(p){return '<option value="'+p[0]+'"'+(p[0]===sel?' selected':'')+'>'+p[1]+'</option>'}).join('')+'</select><iframe title="Раздел" loading="lazy" src="./'+sel+'.html?split=1"></iframe></div>';
  el.querySelector('select').addEventListener('change',function(e){el.querySelector('iframe').src='./'+e.target.value+'.html?split=1'});return el}
 function open(a,b){ if(!d){d=K4.modal('k6-sp-d','Сплит: два раздела');d.classList.add('k6-wide');d.innerHTML='<div class="grid-stack k6-sp" id="k6-spg"></div>';
   const l=document.createElement('link');l.rel='stylesheet';l.href='./vendor/gridstack/gridstack.min.css';document.head.appendChild(l);return K4.load('./vendor/gridstack/gridstack-all.js').then(function(){
    grid=GridStack.init({column:12,cellHeight:60,margin:4,float:false},d.querySelector('#k6-spg'));const nar=window.innerWidth<700;
    let s=['chat','memory'];try{s=JSON.parse(localStorage.getItem('nox.k6.split.v1'))||s}catch(e){}s=[a||s[0],b||s[1]];
    s.forEach(function(x,i){grid.addWidget(pane(x),{x:nar?0:i*6,y:nar?i*6:0,w:nar?12:6,h:nar?6:9})});localStorage.setItem('nox.k6.split.v1',JSON.stringify(s));d.show();return d})}
  if(a&&grid){const f=d.querySelectorAll('select');if(f[0]){f[0].value=a;f[0].dispatchEvent(new Event('change'))}if(b&&f[1]){f[1].value=b;f[1].dispatchEvent(new Event('change'))}}
  d.show();return Promise.resolve(d)}
 K4.fab('k6-split','Сплит','layout-split',function(){open()});window.K6split={open:open,count:function(){return d?d.querySelectorAll('iframe').length:0},srcs:function(){return d?[].map.call(d.querySelectorAll('iframe'),function(f){return f.getAttribute('src')}):[]}};
})();
K6EOF
cat > nox-k6-links.js <<'K6EOF'
/* K6 №91: обратные ссылки и полупрозрачный граф вокруг записи (cytoscape). Записи берутся из #core, #journal, #results и nox.k6.notes.v1; связи: [[ссылка]] и общие слова. API: K6links.build(текст,[корпус]), K6links.count() */
(function(){ if(window.K6links||!window.K4)return; let d,cy;
 function corpus(){ const a=[];['core','journal','results'].forEach(function(i){const e=document.getElementById(i);if(e)[].forEach.call(e.children,function(c){const t=(c.innerText||'').trim();if(t.length>5)a.push(t.slice(0,300))})});
  try{JSON.parse(localStorage.getItem('nox.k6.notes.v1')||'[]').forEach(function(n){a.push(n.title+' '+n.text)})}catch(e){}K4.tasks().forEach(function(t){a.push(t.title)});return a.slice(0,60)}
 function words(t){const m=String(t).toLowerCase().match(/[a-zа-яё0-9]{5,}/g)||[];return new Set(m)}
 async function build(text,corp){ await K4.load('./vendor/cytoscape/dist/cytoscape.min.js');corp=corp||corpus();const w=words(text),rel=[];
  corp.forEach(function(c,i){if(c===text)return;let s=0;words(c).forEach(function(x){if(w.has(x))s++});const ex=(text.match(/\[\[([^\]]+)\]\]/g)||[]).some(function(l){return c.toLowerCase().indexOf(l.slice(2,-2).toLowerCase())>=0});if(ex)s+=5;if(s>0)rel.push({i:i,s:s,c:c})});
  rel.sort(function(a,b){return b.s-a.s});const top=rel.slice(0,8),box=d.querySelector('#k6-lk');if(cy)cy.destroy();
  const el=[{data:{id:'c',label:text.slice(0,40)||'запись'}}];top.forEach(function(r,k){el.push({data:{id:'r'+k,label:r.c.slice(0,32),w:r.s}},{data:{id:'e'+k,source:'c',target:'r'+k}})});
  cy=cytoscape({container:box,elements:el,layout:{name:'concentric',concentric:function(n){return n.id()==='c'?2:1},levelWidth:function(){return 1},minNodeSpacing:30},style:[{selector:'node',style:{label:'data(label)',color:'#fff','font-size':12,'text-valign':'center','background-color':'#7a4b2a','shape':'round-rectangle',width:'label',height:44,padding:'12px',opacity:.55,'border-width':1,'border-color':'#e9b465','text-wrap':'ellipsis','text-max-width':160}},{selector:'#c',style:{opacity:1,'background-color':'#b4761f'}},{selector:'edge',style:{width:2,'line-color':'#c89a63',opacity:.4}}]});
  d.querySelector('#k6-lki').textContent=top.length?'Связанных записей: '+top.length:'Связей не найдено';return top.length}
 function open(t){ if(!d){d=K4.modal('k6-lk-d','Связи записи');d.classList.add('k6-wide');d.innerHTML='<div class="k6-st" id="k6-lki"></div><div id="k6-lk" class="k6-cy"></div>'}d.show();const c=corpus();return build(t||c[0]||'',c)}
 ['core','journal','results'].forEach(function(i){const e=document.getElementById(i);if(e)e.addEventListener('click',function(ev){const it=ev.target.closest('#'+i+' > *');if(it&&ev.target.closest('[data-k6links]'))open((it.innerText||'').trim())})});
 K4.fab('k6-links','Связи','share',function(){open()});window.K6links={open:open,build:async function(t,c){open(t);return build(t,c)},count:function(){return cy?cy.nodes().length:0}};
})();
K6EOF
cat > nox-k6-board.js <<'K6EOF'
/* K6 №92: холст заметок, карточки на бесконечном поле со стрелками (cytoscape: панорама и зум без границ). API: K6board.add(текст), K6board.link(a,b), K6board.arrange(), K6board.count() */
(function(){ if(window.K6board||!window.K4)return; const LK='nox.k6.canvas.v1';let d,cy,n=0,from=null,mode=false;
 function save(){ if(!cy)return;localStorage.setItem(LK,JSON.stringify({n:cy.nodes().map(function(x){return{id:x.id(),t:x.data('label'),p:x.position()}}),e:cy.edges().map(function(x){return[x.source().id(),x.target().id()]})}))}
 function add(t,p){ const id='c'+(++n);cy.add({data:{id:id,label:t},position:p||{x:80+Math.random()*320,y:60+Math.random()*220}});save();return id}
 function link(a,b){ if(a&&b&&a!==b){cy.add({data:{id:'l'+a+b+Date.now(),source:a,target:b}});save()}}
 function arrange(){ cy.layout({name:'cose',animate:false,nodeRepulsion:function(){return 9000}}).run();cy.fit(undefined,30);save()}
 function fromNotes(){ const a=[];['core','journal','results'].forEach(function(i){const e=document.getElementById(i);if(e)[].forEach.call(e.children,function(c){const t=(c.innerText||'').trim();if(t.length>5)a.push(t.slice(0,60))})});try{JSON.parse(localStorage.getItem('nox.k6.notes.v1')||'[]').forEach(function(x){a.push(x.title)})}catch(e){}return a.slice(0,30)}
 async function init(){ await K4.load('./vendor/cytoscape/dist/cytoscape.min.js');const box=d.querySelector('#k6-bd');if(cy)return;
  cy=cytoscape({container:box,elements:[],minZoom:.1,maxZoom:4,wheelSensitivity:.3,style:[{selector:'node',style:{label:'data(label)',color:'#1b1410','font-size':13,'text-valign':'center','text-halign':'center','text-wrap':'wrap','text-max-width':150,'background-color':'#f3dfa8',shape:'round-rectangle',width:170,height:60,'border-width':1,'border-color':'#b4761f'}},{selector:'node.sel',style:{'border-width':3,'border-color':'#d33'}},{selector:'edge',style:{width:2,'line-color':'#c89a63','target-arrow-shape':'triangle','target-arrow-color':'#c89a63','curve-style':'bezier'}}]});
  let s=null;try{s=JSON.parse(localStorage.getItem(LK))}catch(e){}if(s&&s.n)s.n.forEach(function(x){cy.add({data:{id:x.id,label:x.t},position:x.p});n=Math.max(n,+x.id.slice(1)||0)});if(s&&s.e)s.e.forEach(function(x,i){cy.add({data:{id:'le'+i,source:x[0],target:x[1]}})});
  cy.on('tap','node',function(e){const id=e.target.id();if(mode){if(!from){from=id;e.target.addClass('sel')}else{link(from,id);cy.nodes().removeClass('sel');from=null;mode=false}}});cy.on('dragfree','node',save)}
 async function open(){ if(!d){d=K4.modal('k6-bd-d','Холст заметок');d.classList.add('k6-wide');d.innerHTML='<div class="k6-row"><input id="k6-bt" class="k4-in k6-in" aria-label="Текст карточки" placeholder="Текст карточки" style="flex:1;min-width:160px"><button type="button" class="k4-btn" data-a="add">+ Карточка</button><button type="button" class="k4-btn" data-a="link" aria-pressed="false">Стрелка</button><button type="button" class="k4-btn" data-a="arr">Разложить заметки</button><button type="button" class="k4-btn" data-a="clr">Очистить</button></div><div class="k6-st" id="k6-bs">Стрелка: нажмите кнопку, затем две карточки.</div><div id="k6-bd" class="k6-cy"></div>';
   d.addEventListener('click',async function(e){const b=e.target.closest('button[data-a]');if(!b)return;const a=b.dataset.a;await init();
    if(a==='add'){const i=d.querySelector('#k6-bt');if(i.value.trim()){add(i.value.trim());i.value=''}}else if(a==='link'){mode=!mode;from=null;b.setAttribute('aria-pressed',mode)}else if(a==='clr'){cy.elements().remove();save()}else if(a==='arr'){if(!cy.nodes().length)fromNotes().forEach(function(t){add(t)});arrange()}})}
  d.show();await init();return d}
 K4.fab('k6-board','Холст','bounding-box',function(){open()});window.K6board={open:open,add:async function(t){await open();return add(t)},link:link,arrange:arrange,count:function(){return cy?cy.nodes().length:0},edges:function(){return cy?cy.edges().length:0}};
})();
K6EOF
cat > nox-k6-live.js <<'K6EOF'
/* K6 №93: живой предпросмотр сгенерированного интерфейса: ИИ (K4.ask) пишет HTML, справа iframe sandbox, слева редактор codemirror. API: K6live.build(описание), K6live.html() */
(function(){ if(window.K6live||!window.K4)return; let d,ed,fr,t;
 function tpl(desc){ const f=String(desc).replace(/^[^:]*:/,'').split(/[,;\n]/).map(function(s){return s.trim()}).filter(Boolean).slice(0,8);if(!f.length)f=['Имя','Email'];
  return '<!doctype html><meta charset="utf-8"><style>body{font:16px system-ui;padding:16px}label{display:block;margin:10px 0 4px}input,textarea,button{font:16px system-ui;min-height:44px;padding:0 10px;width:100%;box-sizing:border-box}button{margin-top:14px;background:#7a4b2a;color:#fff;border:0;border-radius:8px}</style><form>'+f.map(function(x,i){return '<label for="f'+i+'">'+K4.esc(x)+'</label><input id="f'+i+'" name="f'+i+'">'}).join('')+'<button type="submit">Отправить</button></form>'}
 function show(h){ fr.srcdoc=h;if(ed&&ed.getValue()!==h)ed.setValue(h)}
 async function build(desc){ const el=document.createElement('div');d.querySelector('#k6-ls').textContent='ИИ собирает интерфейс…';try{await K4.ask('Напиши один самодостаточный HTML-файл (встроенные CSS и JS, без внешних ресурсов, кнопки не ниже 44px, шрифт не меньше 12px) для описания: '+desc+'. Верни только код.',el)}catch(e){}
  let h=String(el.textContent||'');const m=/```(?:html)?\s*([\s\S]*?)```/.exec(h);if(m)h=m[1];const ok=/<(form|div|body|html|button|input|main)/i.test(h);d.querySelector('#k6-ls').textContent=ok?'Готово: правьте код слева, предпросмотр обновляется':'ИИ недоступен: показан шаблон по описанию';h=ok?h:tpl(desc);show(h);return h}
 async function open(){ if(!d){d=K4.modal('k6-lv-d','Живой предпросмотр интерфейса');d.classList.add('k6-wide');d.innerHTML='<div class="k6-row"><input id="k6-ld" class="k4-in k6-in" aria-label="Описание интерфейса" placeholder="Например: форма: имя, email, сообщение" style="flex:1;min-width:200px"><button type="button" class="k4-btn pri" id="k6-lg">Собрать</button></div><div class="k6-st" id="k6-ls"></div><div class="k6-live"><textarea id="k6-lt" aria-label="Код"></textarea><iframe id="k6-lf" title="Предпросмотр" sandbox="allow-scripts"></iframe></div>';
   const l=document.createElement('link');l.rel='stylesheet';l.href='./vendor/codemirror/codemirror.css';document.head.appendChild(l);await K4.load('./vendor/codemirror/codemirror.iife.js');
   fr=d.querySelector('#k6-lf');const C=K4.glob(window.NOX_codemirror);ed=C.fromTextArea(d.querySelector('#k6-lt'),{lineNumbers:false,lineWrapping:true});ed.on('change',function(){clearTimeout(t);t=setTimeout(function(){fr.srcdoc=ed.getValue()},300)});
   d.querySelector('#k6-lg').addEventListener('click',function(){const v=d.querySelector('#k6-ld').value.trim();if(v)build(v)})}
  d.show();setTimeout(function(){ed&&ed.refresh()},200);return d}
 K4.fab('k6-live','Собрать UI','window',function(){open()});window.K6live={open:open,build:async function(x){await open();return build(x)},html:function(){return fr?fr.srcdoc:''},sandbox:function(){return fr?fr.getAttribute('sandbox'):''}};
})();
K6EOF
cat > nox-k6-canvasdoc.js <<'K6EOF'
/* K6 №94: Canvas: справа редактируемый документ (BlockNote), ИИ переписывает выделение или текущий абзац через K4.ask. API: K6canvas.set(текст), K6canvas.text(), K6canvas.replace(новыйТекст), K6canvas.rewrite(инструкция) */
(function(){ if(window.K6canvas||!window.K4)return; let d,ed;
 const st=function(t){const e=d&&d.querySelector('#k6-cs');if(e)e.textContent=t};
 function cur(){ const sel=ed.getSelectedText?ed.getSelectedText():'';if(sel)return{sel:sel,block:null};const b=ed.getTextCursorPosition().block;return{sel:'',block:b,text:(b.content||[]).map(function(c){return c.text||''}).join('')}}
 function replace(t){ const c=cur();if(c.sel)ed.insertInlineContent(t);else ed.updateBlock(c.block,{type:'paragraph',content:t});return true}
 async function rewrite(ins){ const c=cur(),src=c.sel||c.text||'';if(!src){st('Выделите текст или поставьте курсор в абзац');return false}
  const el=document.createElement('div');st('ИИ переписывает…');try{await K4.ask('Перепиши текст. '+(ins||'Сделай понятнее и короче')+'. Верни только новый текст без пояснений.\n\n'+src,el)}catch(e){}
  const r=String(el.textContent||'').trim();if(!r||/^NOX\s+(занят|недоступен)/i.test(r)||r==='…'){st('ИИ недоступен, текст не изменён');return false}replace(r);st('Готово');return true}
 async function open(){ if(!d){d=K4.modal('k6-cv-d','Canvas: документ');d.classList.add('k6-wide');d.innerHTML='<div class="k6-row"><input id="k6-ci" class="k4-in k6-in" aria-label="Инструкция" placeholder="Как переписать: короче, формальнее…" style="flex:1;min-width:200px"><button type="button" class="k4-btn pri" id="k6-cr">Перепиши выделенное</button></div><div class="k6-st" id="k6-cs">Выделите текст в документе.</div><div id="k6-cb" class="k6-bn"></div>';
   const l=document.createElement('link');l.rel='stylesheet';l.href='./vendor/blocknote/blocknote.css';document.head.appendChild(l);await K4.load('./vendor/blocknote/blocknote.iife.js');
   const B=window.NOX_blocknote.BlockNoteEditor;ed=B.create();ed.mount(d.querySelector('#k6-cb'));d.querySelector('#k6-cr').addEventListener('click',function(){rewrite(d.querySelector('#k6-ci').value.trim())});
   const ta=document.getElementById('edCode');if(ta&&ta.value){ed.replaceBlocks(ed.document,String(ta.value).slice(0,3000).split('\n').map(function(s){return{type:'paragraph',content:s}}))}}
  d.show();return d}
 K4.fab('k6-canvas','Canvas','file-earmark-text',function(){open()});
 window.K6canvas={open:open,set:async function(t){await open();ed.replaceBlocks(ed.document,t.split('\n').map(function(s){return{type:'paragraph',content:s}}))},text:function(){return ed?ed.document.map(function(b){return(b.content||[]).map(function(c){return c.text||''}).join('')}).join('\n'):''},replace:replace,rewrite:rewrite,focusFirst:function(){ed.setTextCursorPosition(ed.document[0],'end')}};
})();
K6EOF
add(){ f=$1.html; [ -f $f ] || { echo "no $f"; return; }
 grep -q "nox-k6-$2.js" $f && { echo "have $f $2"; return; }
 cp $f $f.bak_k6_$TS; tag=""
 grep -q "nox-k4-core.js" $f || tag="<script src=\"./nox-k4-core.js?v=k4a\" defer></script>"
 grep -q "nox-k6-ui.css" $f || tag="$tag<link rel=\"stylesheet\" href=\"./nox-k6-ui.css?v=k6a\">"
 tag="$tag<script src=\"./nox-k6-$2.js?v=k6a\" defer></script>"
 python3 - "$f" "$tag" <<'PYX'
import sys
f,t=sys.argv[1],sys.argv[2]
s=open(f,encoding='utf-8').read();i=s.rfind('</body>')
open(f,'w',encoding='utf-8').write(s[:i]+t+s[i:] if i>=0 else s+t)
PYX
 echo "added $2 -> $f"; }
add index split; add memory links; add memory board; add studio live; add assistant canvasdoc
echo "K6: №90 сплит-вид (gridstack)" >> qa/rework/index.fixed
echo "K6: №91 связи записи (cytoscape); №92 холст заметок" >> qa/rework/memory.fixed
echo "K6: №93 живой предпросмотр UI (codemirror+iframe sandbox)" >> qa/rework/studio.fixed
echo "K6: №94 Canvas-документ (blocknote)" >> qa/rework/assistant.fixed
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 230 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
W="await new Promise(r=>setTimeout(r,1500));"
C=[
("index",W+"""await K6split.open('chat','memory');await new Promise(r=>setTimeout(r,1200));const sel=document.querySelectorAll('#k6-sp-d select');return JSON.stringify({n:K6split.count(),s:K6split.srcs(),h:Math.min(...[...sel].map(x=>x.getBoundingClientRect().height))})"""),
("memory",W+"""const n=await K6links.build('Проект NOX память заметки график',['NOX проект график связи','Погода сегодня','заметки память проект','Другое совсем']);await K6board.add('Идея А');const b=await K6board.add('Идея Б');K6board.link('c1','c2');await new Promise(r=>setTimeout(r,500));return JSON.stringify({n,nodes:K6links.count(),cards:K6board.count(),edges:K6board.edges()})"""),
("studio",W+"""const h=await K6live.build('форма: имя, email, сообщение');await new Promise(r=>setTimeout(r,800));return JSON.stringify({form:/<form/.test(h),sb:K6live.sandbox(),fr:K6live.html().length>50})"""),
("assistant",W+"""await K6canvas.set('Первый абзац\\nВторой абзац');await new Promise(r=>setTimeout(r,600));K6canvas.focusFirst();K6canvas.replace('Новый текст');await new Promise(r=>setTimeout(r,400));return JSON.stringify({t:K6canvas.text()})"""),
("system",W+"""await K6dash.open();await new Promise(r=>setTimeout(r,2500));return JSON.stringify({n:K6dash.count()})"""),
]
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=[])
    for w,h in((1440,900),(390,844)):
      for u,js in C:
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/'+u+'.html',wait_until='domcontentloaded',timeout=40000);await pg.wait_for_timeout(2500);r=await asyncio.wait_for(pg.evaluate("(async()=>{"+js+"})()"),30)
        except Exception as e: r='EXC '+str(e)[:240]
        print('QA',w,u,r,'errs',len(errs),errs[:2])
        try: await asyncio.wait_for(pg.close(),5)
        except Exception: pass
    await b.close()
asyncio.run(m())
QAEOF
echo "K6 f_2 done"
