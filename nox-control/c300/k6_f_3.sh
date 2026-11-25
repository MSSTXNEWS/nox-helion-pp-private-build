echo "C300: k6_f_3"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
cat > nox-k6-askphoto.js <<'K6EOF'
/* K6 №95: вопрос к своей галерее (orama-orama; transformers-js по кнопке «Разметить ИИ» добавляет теги к фото). Источники: data/studio_gallery.json и картинки #gTh. API: K6ask.index(список), K6ask.search(запрос), K6ask.count() */
(function(){ if(window.K6ask||!window.K4)return; let d,db,items=[];
 async function build(list){ await K4.load('./vendor/orama-orama/orama-orama.iife.js');const O=K4.glob(window.NOX_orama_orama)||window.NOX_orama_orama;const C=O.create||(O.default&&O.default.create);
  items=list.map(function(x,i){return{id:String(i),title:String(x.title||''),tags:String(x.tags||''),thumb:x.thumb||''}});db=await C({schema:{title:'string',tags:'string'}});await O.insertMultiple(db,items.map(function(x){return{id:x.id,title:x.title,tags:x.tags}}));return items.length}
 async function sources(){ let a=[];try{const j=await fetch('./data/studio_gallery.json',{cache:'no-store'}).then(function(r){return r.json()});a=(j.items||[]).map(function(x){return{title:x.title,thumb:x.thumb}})}catch(e){}
  document.querySelectorAll('#gTh img').forEach(function(im){a.push({title:im.alt||im.title||im.src.split('/').pop(),thumb:im.src})});return a}
 async function search(q){ if(!db)await build(await sources());const O=K4.glob(window.NOX_orama_orama)||window.NOX_orama_orama;let h=[];
  try{const r=await O.search(db,{term:q,tolerance:1,limit:12});h=r.hits.map(function(x){return items[+x.id]})}catch(e){}
  if(!h.length){const l=q.toLowerCase().split(/\s+/).filter(Boolean);h=items.filter(function(x){return l.some(function(w){return(x.title+' '+x.tags).toLowerCase().indexOf(w)>=0})}).slice(0,12)}return h}
 function show(h){ const o=d.querySelector('#k6-ao');o.innerHTML=h.length?'':'<div class="k6-st">Ничего не найдено</div>';h.forEach(function(x){const b=document.createElement('a');b.href=x.thumb||'#';b.target='_blank';b.rel='noopener';b.className='k4-btn';b.style.cssText='display:flex;gap:10px;margin:6px 0;text-decoration:none;justify-content:flex-start;height:auto;padding:6px';b.innerHTML=(x.thumb?'<img alt="" src="'+K4.esc(x.thumb)+'" style="width:72px;height:56px;object-fit:cover;border-radius:6px">':'')+'<span style="font-size:14px">'+K4.esc(x.title.slice(0,120))+'</span>';o.appendChild(b)})}
 async function tag(){ const st=d.querySelector('#k6-as');st.textContent='Загрузка модели…';try{const T=await import('./vendor/transformers-js/dist/transformers.web.min.js');const p=await T.pipeline('image-classification','Xenova/mobilenet_v2');let n=0;
  for(const x of items.slice(0,12)){if(!x.thumb)continue;try{const r=await p(x.thumb,{topk:3});x.tags=r.map(function(y){return y.label}).join(', ');n++}catch(e){}}await build(items);st.textContent='Размечено фото: '+n}catch(e){st.textContent='Модель недоступна, поиск идёт по названиям'}}
 async function open(){ if(!d){d=K4.modal('k6-as-d','Спросить свои фото');d.classList.add('k6-wide');d.innerHTML='<div class="k6-row"><input id="k6-aq" class="k4-in k6-in" aria-label="Запрос" placeholder="Найди фото: закат, скульптура…" style="flex:1;min-width:200px"><button type="button" class="k4-btn pri" id="k6-ag">Найти</button><button type="button" class="k4-btn" id="k6-at">Разметить ИИ</button></div><div class="k6-st" id="k6-as"></div><div id="k6-ao"></div>';
   const go=async function(){const q=d.querySelector('#k6-aq').value.trim();if(q)show(await search(q))};d.querySelector('#k6-ag').addEventListener('click',go);d.querySelector('#k6-aq').addEventListener('keydown',function(e){if(e.key==='Enter')go()});d.querySelector('#k6-at').addEventListener('click',tag)}d.show();return d}
 K4.fab('k6-ask','Спросить фото','search',function(){open()});window.K6ask={open:open,index:build,search:search,count:function(){return items.length}};
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
add photo askphoto
echo "K6: №95 вопрос к галерее (orama, transformers-js по кнопке)" >> qa/rework/photo.fixed
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 200 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
JS="""(async()=>{await K6ask.index([{title:'Закат над морем'},{title:'Скульптура в лесу'},{title:'Кот на окне'}]);const a=await K6ask.search('закат');const b=await K6ask.search('скульптура');await K6ask.open();const bt=[...document.querySelectorAll('#k6-as-d button')].map(x=>x.getBoundingClientRect().height).filter(x=>x>0);return JSON.stringify({n:K6ask.count(),a:a.map(x=>x.title),b:b.length,minbtn:bt.length?Math.min(...bt):-1})})()"""
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=[])
    for w,h in((1440,900),(390,844)):
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/photo.html',wait_until='domcontentloaded',timeout=40000);await pg.wait_for_function('window.K6ask',timeout=15000);r=await asyncio.wait_for(pg.evaluate(JS),40)
        except Exception as e: r='EXC '+str(e)[:240]
        print('QA',w,'photo',r,'errs',len(errs),errs[:2])
        try: await asyncio.wait_for(pg.close(),5)
        except Exception: pass
    await b.close()
asyncio.run(m())
QAEOF
echo "K6 f_3 done"
