echo "C300: k2_b2"
S=/workspace/nox/web/site; cd $S
TS=$(date +%s)
cat > nox-k2-heat.css <<'EOF'
#k2-heat{margin:16px 0;padding:16px;border-radius:18px;background:rgba(20,15,15,.95);border:1px solid rgba(255,255,255,.12)}
#k2-heat h3{margin:0 0 8px;font-size:16px;font-weight:400;color:#efe6df}
#k2-heat .k2-chart{width:100%;height:190px}
#k2-heat sl-button::part(base),#k2-heat button{min-height:44px;font-size:14px}
EOF
cat > nox-k2-heat.js <<'EOF'
/* K2 №9: тепловой календарь активности организма (GitHub contributions) на ECharts. Данные: data/organs_hist.jsonl. Связь: «Объяснить» -> NOXcmd chat.send */
(function(){
 function load(src){return new Promise(function(ok,no){if(window.echarts)return ok();const s=document.createElement('script');s.src=src;s.onload=ok;s.onerror=no;document.head.appendChild(s)})}
 async function go(){
  const host=document.getElementById('page');if(!host||document.getElementById('k2-heat'))return;
  let txt;try{txt=await (await fetch('./data/organs_hist.jsonl',{cache:'no-cache'})).text()}catch(e){return}
  const day={};txt.split('\n').forEach(function(l){if(!l)return;try{const o=JSON.parse(l);const d=new Date(o.ts*1000);const k=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');day[k]=(day[k]||0)+1}catch(e){}});
  const keys=Object.keys(day).sort();if(!keys.length)return;
  await load('./vendor/echarts/echarts.min.js');
  const box=document.createElement('section');box.id='k2-heat';box.className='card';
  box.innerHTML='<h3>Активность организма по дням</h3><div class="k2-chart" role="img" aria-label="Тепловой календарь активности"></div><sl-button size="large" pill>Объяснить</sl-button>';
  host.appendChild(box);
  const end=keys[keys.length-1],d0=new Date(end);d0.setDate(d0.getDate()-100);
  const start=d0.toISOString().slice(0,10);
  const c=echarts.init(box.querySelector('.k2-chart'),'nox');
  c.setOption({tooltip:{formatter:function(p){return p.value[0]+': '+p.value[1]+' замеров'}},visualMap:{show:false,min:0,max:Math.max.apply(null,Object.values(day)),inRange:{color:['#2a1f1a','#7a4b2a','#e9b465']}},
   calendar:{range:[start,end],cellSize:['auto',16],left:30,right:10,top:24,itemStyle:{borderWidth:2,borderColor:'#140f0f'},splitLine:{show:false},yearLabel:{show:false},dayLabel:{color:'#cbbfb6',fontSize:12},monthLabel:{color:'#cbbfb6',fontSize:12}},
   series:[{type:'heatmap',coordinateSystem:'calendar',data:Object.entries(day)}]});
  addEventListener('resize',function(){c.resize()});
  const b=box.querySelector('sl-button');b.addEventListener('click',function(){if(window.NOXcmd)window.NOXcmd('chat.send',{message:'Объясни мою активность по дням: '+JSON.stringify(day).slice(0,1500)})});
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);else setTimeout(go,300);
})();
EOF
cat > nox-k2-lyrics.css <<'EOF'
#k2-lyr{margin-top:12px;padding:14px;border-radius:14px;background:rgba(20,15,15,.9);border:1px solid rgba(255,255,255,.1);max-height:220px;overflow:auto;font-size:16px;line-height:1.7;color:#a89c93}
#k2-lyr p{margin:0;transition:all .25s}
#k2-lyr p.on{color:#efe6df;font-size:20px}
EOF
cat > nox-k2-lyrics.js <<'EOF'
/* K2 №20: текст песни с подсветкой строки. Только локальный .lrc рядом с треком (то же имя файла), ничего не качается с сайтов. lrc-kit из vendor. */
(function(){
 const a=document.getElementById('mAud');if(!a)return;let box,lines=[],cur=-1,last='';
 function parse(t){return import('./vendor/lrc-kit/lrc-kit.esm.js').then(function(m){const L=(m.Lrc||(m.default&&m.default.Lrc));const r=L.parse(t);return r.lyrics.map(function(x){return{t:x.timestamp,s:x.content}}).filter(function(x){return x.s})}).catch(function(){const o=[];t.split('\n').forEach(function(l){const m=l.match(/^\[(\d+):(\d+(?:\.\d+)?)\](.*)/);if(m&&m[3].trim())o.push({t:+m[1]*60+ +m[2],s:m[3].trim()})});return o})}
 async function load(){const src=a.currentSrc||a.src;if(!src||src===last)return;last=src;lines=[];cur=-1;if(box)box.remove();box=null;
  const u=src.replace(/\.[a-z0-9]{2,4}(\?.*)?$/i,'.lrc');if(u===src)return;
  try{const r=await fetch(u);if(!r.ok)return;const t=await r.text();if(t.indexOf('[')<0)return;lines=await parse(t);if(!lines.length)return;
   box=document.createElement('div');box.id='k2-lyr';box.setAttribute('aria-live','off');box.innerHTML=lines.map(function(l){return'<p>'+l.s.replace(/[<>&]/g,'')+'</p>'}).join('');a.insertAdjacentElement('afterend',box)}catch(e){}}
 a.addEventListener('loadedmetadata',load);a.addEventListener('play',load);
 a.addEventListener('timeupdate',function(){if(!box)return;let i=-1;for(let k=0;k<lines.length;k++){if(lines[k].t<=a.currentTime)i=k;else break}
  if(i!==cur){cur=i;const ps=box.children;for(let k=0;k<ps.length;k++)ps[k].classList.toggle('on',k===i);if(ps[i])box.scrollTo({top:ps[i].offsetTop-80,behavior:'smooth'})}});
})();
EOF
cat > nox-k2-recent.css <<'EOF'
#k2-recent sl-button::part(base){min-height:44px;font-size:14px;justify-content:flex-start}
#k2-recent::part(panel){background:rgba(24,18,18,.92);backdrop-filter:blur(18px);border:1px solid rgba(255,255,255,.14)}
EOF
cat > nox-k2-recent.js <<'EOF'
/* K2: недавние разделы стопкой (Stage Manager). Alt+R открывает окно, клик переходит. Хранение: localStorage k2_recent */
(function(){
 const K='k2_recent';let L=[];try{L=JSON.parse(localStorage.getItem(K)||'[]')}catch(e){}
 const p=location.pathname.split('/').pop()||'index.html';const t=(document.title||p).slice(0,40);
 L=L.filter(function(x){return x.p!==p});L.unshift({p:p,t:t});L=L.slice(0,8);try{localStorage.setItem(K,JSON.stringify(L))}catch(e){}
 function open(){if(!window.customElements||!customElements.get('sl-dialog'))return;
  let d=document.getElementById('k2-recent');if(d)d.remove();
  d=document.createElement('sl-dialog');d.id='k2-recent';d.label='Недавние разделы';
  d.innerHTML=L.map(function(x){return'<sl-button size="large" variant="text" style="display:block;width:100%" href="./'+x.p.replace(/[^\w.\-]/g,'')+'">'+x.t.replace(/[<>&"]/g,'')+'</sl-button>'}).join('');
  document.body.appendChild(d);d.show();d.addEventListener('sl-after-hide',function(){d.remove()})}
 document.addEventListener('keydown',function(e){if(e.altKey&&!e.ctrlKey&&!e.metaKey&&(e.code==='KeyR')){e.preventDefault();open()}});
})();
EOF
cat > nox-k2-stickyth.css <<'EOF'
/* K2: липкие шапки таблиц в ответах чата (Raycast 2.10) */
#msgs table thead th,.msgs table thead th{position:sticky;top:0;background:rgba(24,18,18,.96);z-index:1}
EOF
add(){ f=$1.html; [ -f $f ] || { echo "no $f"; return; }
 grep -q "nox-k2-$2" $f && { echo "have $f $2"; return; }
 cp $f $f.bak_k2_$TS; tag=""
 [ -f nox-k2-$2.css ] && tag="$tag<link rel=\"stylesheet\" href=\"./nox-k2-$2.css?v=k2b\">"
 [ -f nox-k2-$2.js ] && tag="$tag<script src=\"./nox-k2-$2.js?v=k2b\" defer></script>"
 python3 - "$f" "$tag" <<'PY'
import sys
f,t=sys.argv[1],sys.argv[2]
s=open(f,encoding='utf-8').read();i=s.rfind('</body>')
open(f,'w',encoding='utf-8').write(s[:i]+t+s[i:] if i>=0 else s+t)
PY
 echo "added $2 -> $f"; }
add growth heat; add music lyrics; add chat stickyth
for p in index chat music growth news cinema photo settings system calendar; do add $p recent; done
echo "K2: добавлены фишки: тепловой календарь активности (heat)" >> qa/rework/growth.fixed
echo "K2: добавлены фишки: текст песни из локального .lrc (lyrics)" >> qa/rework/music.fixed
echo "K2: добавлены фишки: липкие шапки таблиц (stickyth)" >> qa/rework/chat.fixed
for p in index music news cinema photo settings system calendar; do echo "K2: недавние разделы Alt+R (recent)" >> qa/rework/$p.fixed; done
sed -i 's#127.0.0.1:8090/web/#127.0.0.1:8091/web/#' /tmp/k2_qa.py 2>/dev/null
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
sed -i "s#if pg=='index' and w==1440#if pg=='growth' and w==1440#; s#errs.append(str(e)\[:120\])#errs.append(str(e)[:120])#" /tmp/k2_qa.py
timeout 200 $PY /tmp/k2_qa.py growth music chat index news cinema photo settings system calendar 2>&1 | tail -22
$PY - <<'PY'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch();pg=await b.new_page(viewport={'width':1440,'height':900})
    await pg.goto('http://127.0.0.1:8091/web/growth.html');await pg.wait_for_timeout(3000)
    print('heat',await pg.evaluate("!!document.getElementById('k2-heat')"), await pg.evaluate("document.querySelector('#k2-heat canvas')?1:0"))
    await pg.keyboard.press('Alt+R');await pg.wait_for_timeout(800)
    print('recent',await pg.evaluate("!!document.getElementById('k2-recent')"))
    await b.close()
asyncio.run(m())
PY
exit 0
