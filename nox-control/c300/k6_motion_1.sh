echo "C300: k6_motion_1"
S=/workspace/nox/web/site; V=$S/vendor; cd $S; TS=$(date +%s)
get(){ n=$1; spec=$2; d=$V/$n; mkdir -p $d /tmp/k6v/$n; cd /tmp/k6v/$n; rm -rf package
 U=$(curl -fsSL "https://registry.npmjs.org/$spec/latest" | python3 -c "import json,sys;print(json.load(sys.stdin)['dist']['tarball'])")
 curl -fsSL "$U" | tar xz; cp package/LICENSE* $d/ 2>/dev/null; cp package/package.json $d/package.json; cd $S; }
get animate.css animate.css; cp /tmp/k6v/animate.css/package/animate.min.css $V/animate.css/
get hover.css hover.css; cp /tmp/k6v/hover.css/package/css/hover-min.css $V/hover.css/
get magic.css magic.css; cp /tmp/k6v/magic.css/package/dist/magic.min.css $V/magic.css/
get auto-animate @formkit/auto-animate; cp /tmp/k6v/auto-animate/package/index.mjs /tmp/k6v/auto-animate/package/index.min.js $V/auto-animate/
ls -la $V/animate.css $V/hover.css $V/magic.css $V/auto-animate | awk '{print $5,$9}'
grep -il "mit" $V/hover.css/LICENSE* 2>/dev/null; grep -i -m2 "licen" /tmp/k6v/hover.css/package/README.md
H=$V/hover.css/hover-min.css; M=$V/magic.css/magic.min.css
for k in hvr-bob hvr-buzz hvr-hang hvr-wobble-horizontal hvr-buzz-out; do grep -q "@keyframes $k[{ ]" $H && echo "H ok $k" || echo "H NO $k"; done
for k in puffIn vanishIn; do grep -q "@keyframes $k[{ ]" $M && echo "M ok $k" || echo "M NO $k"; done
grep -o "\.magictime{[^}]*}" $M | head -2
for k in pulse swing flip bounce bounceIn tada jello heartBeat wobble rubberBand flash shakeX headShake fadeIn fadeInUp fadeInDown fadeInRight fadeInLeft zoomIn flipInY rotateIn; do grep -q "@keyframes $k[{ ]" $V/animate.css/animate.min.css || echo "A NO $k"; done
grep -o "\.animate__animated{[^}]*}" $V/animate.css/animate.min.css | head -1
cd $S
cat > nox-k6-motionlib.js <<'K6EOF'
/* K6 motionlib: пресеты ANM-001..100 играются классами настоящих библиотек (animate.css MIT, hover.css MIT, magic.css MIT, @formkit/auto-animate MIT; vendor/*), где есть аналог; остальные остаются на GSAP из K5. Подключать ДО nox-k5-motion100.js. */
(function(){ if(window.NOXMotionLib)return;
 const reduce=window.matchMedia&&matchMedia('(prefers-reduced-motion:reduce)').matches;
 const A='a',H='h',M='m';
 const MAP={};function set(a,b,t,n){for(let i=a;i<=b;i++)MAP[i]=[t,n]}
 set(1,4,H,'hvr-bob');set(5,7,A,'pulse');set(8,10,A,'swing');set(14,15,H,'hvr-wobble-horizontal');
 set(34,35,H,'hvr-buzz');set(36,36,A,'flip');set(37,38,A,'swing');set(44,46,H,'hvr-hang');set(52,53,A,'bounce');
 set(56,58,A,'bounce');set(59,61,A,'bounceIn');set(62,63,A,'tada');set(64,65,A,'jello');set(66,67,A,'heartBeat');
 set(68,69,M,'puffIn');set(70,71,A,'wobble');set(72,73,A,'rubberBand');set(74,75,A,'flash');
 set(76,78,A,'shakeX');set(79,80,A,'headShake');set(81,83,A,'flash');set(84,85,A,'pulse');set(86,87,H,'hvr-buzz');
 set(88,88,A,'bounce');set(89,90,A,'wobble');
 set(91,91,A,'fadeIn');set(92,92,A,'fadeInUp');set(93,93,A,'fadeInDown');set(94,94,A,'fadeInRight');set(95,95,A,'fadeInLeft');
 set(96,96,A,'zoomIn');set(97,97,M,'puffIn');set(98,98,A,'flipInY');set(99,99,M,'vanishIn');set(100,100,A,'rotateIn');
 function css(h){const l=document.createElement('link');l.rel='stylesheet';l.href=h;document.head.appendChild(l)}
 css('./vendor/animate.css/animate.min.css');css('./vendor/hover.css/hover-min.css');css('./vendor/magic.css/magic.min.css');
 function clean(el){if(!el)return;if(el._k6c){el._k6c.forEach(function(c){el.classList.remove(c)});el._k6c=null}el.style.animation='';el.style.removeProperty('--animate-duration');el.style.removeProperty('--animate-repeat');el.style.removeProperty('animation-duration');el.style.removeProperty('animation-iteration-count')}
 function wrap(m){ if(!m||m._k6)return;m._k6=1;const op=m.play,os=m.stop;
  m.stop=function(el){clean(el);return os.apply(this,arguments)};
  m.play=function(el,x){ if(!el||reduce)return null;const t=m.find(x);if(!t)return op.apply(this,arguments);const r=MAP[t[0]];if(!r)return op.apply(this,arguments);
   m.stop(el);const id='ANM-'+String(t[0]).padStart(3,'0');m.cur=id;el.dataset.anm=id;el.dataset.lib=r[0]+':'+r[1];
   const inf=t[5]==='infinite',dur=t[3]+'s';el.style.transformBox='fill-box';el.style.transformOrigin='center';
   if(r[0]===A){el._k6c=['animate__animated','animate__'+r[1]].concat(inf?['animate__infinite']:[]);el._k6c.forEach(function(c){el.classList.add(c)});el.style.setProperty('--animate-duration',dur);if(!inf)el.style.setProperty('--animate-repeat',String(t[5]))}
   else if(r[0]===M){el._k6c=['magictime',r[1]];el._k6c.forEach(function(c){el.classList.add(c)});el.style.animationDuration=dur;el.style.animationIterationCount=inf?'infinite':String(t[5])}
   else{el.style.animation=r[1]+' '+(inf?Math.max(t[3]/2,.4):t[3])+'s linear 0s '+(inf?'infinite alternate':t[5])}
   if(!inf){el.addEventListener('animationend',function f(){el.removeEventListener('animationend',f);clean(el)},{once:true})}
   return null};
 }
 let _m;try{Object.defineProperty(window,'NOXMotion',{configurable:true,get:function(){return _m},set:function(v){_m=v;wrap(v)}})}catch(e){}
 const L=window.NOXMotionLib={map:MAP,wrap:wrap,autoAnimate:function(el,opt){return import('./vendor/auto-animate/index.mjs').then(function(m){return(m.default||m.autoAnimate)(el,opt)}).catch(function(){})}};
 function ready(f){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',f);else f()}
 ready(function(){ if(window.NOXMotion&&!window.NOXMotion._k6)wrap(window.NOXMotion);
  const pg=document.getElementById('page');if(pg&&!reduce&&window.NOXMotion){const id=91+(location.pathname.length%10);window.NOXMotion.play(pg,id)}
  document.querySelectorAll('[data-auto-animate],#msgs,#messages,#chat-log,#log,.sl-list').forEach(function(e){L.autoAnimate(e,{duration:200})});
 });
})();
K6EOF
# K5: не трогать переход страницы, если есть lib (правка с бэкапом)
cp nox-k5-motion100.js nox-k5-motion100.js.bak_k6_$TS
python3 - <<'PY'
p='nox-k5-motion100.js';s=open(p,encoding='utf-8').read()
if 'NOXMotionLib' not in s:
    s=s.replace("if(pg&&!reduce){const t=pick","if(pg&&!reduce&&!window.NOXMotionLib){const t=pick",1);open(p,'w',encoding='utf-8').write(s);print('k5 patched')
PY
add(){ f=$1.html; [ -f $f ] || { echo "no $f"; return; }
 grep -q "nox-k6-motionlib.js" $f && { echo "have $f"; return; }
 cp $f $f.bak_k6_$TS
 python3 - "$f" <<'PY'
import sys
f=sys.argv[1];s=open(f,encoding='utf-8').read();t='<script src="./nox-k6-motionlib.js?v=k6a" defer></script>'
i=s.find('<link rel="stylesheet" href="./nox-k5-motion100.css')
if i<0: i=s.find('nox-k5-motion100.js'); i=s.rfind('<script',0,i)
open(f,'w',encoding='utf-8').write(s[:i]+t+s[i:]);print('added',f,i)
PY
}
for p in chat index voice; do add $p; echo "K6: motionlib animate.css/hover.css/magic.css/auto-animate (vendor), ANM→классы библиотек" >> qa/rework/$p.fixed; done
grep -o 'id="[a-z-]*"' chat.html | grep -i "msg\|log\|mess\|list" | head -5
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
$PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
JS="""(async()=>{await new Promise(r=>setTimeout(r,1800));const M=window.NOXMotion;if(!M||!window.NOXMotionLib)return 'NO LIB';const el=document.createElement('div');el.style.cssText='width:44px;height:44px;position:fixed;left:5px;top:5px';document.body.appendChild(el);const o={};
for(const id of [2,5,62,68,76,92,99,21]){M.play(el,id);await new Promise(r=>setTimeout(r,60));o[id]=(el.dataset.lib||'gsap')+'|'+getComputedStyle(el).animationName}
M.stop(el);const pg=document.getElementById('page');o.page=pg?(pg.className+'|'+pg.dataset.lib):'-';o.cls=el.className;return JSON.stringify(o)})()"""
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=[])
    for w,h in((1440,900),(390,844)):
      for u in('chat','index','voice'):
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:120]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/'+u+'.html',wait_until='domcontentloaded',timeout=40000);await pg.wait_for_timeout(2500);r=await pg.evaluate(JS)
        except Exception as e: r='EXC '+str(e)[:160]
        print(w,u,r,'errs',len(errs),errs[:2]);await pg.close()
    await b.close()
asyncio.run(m())
QAEOF
echo "K6 motion done"
