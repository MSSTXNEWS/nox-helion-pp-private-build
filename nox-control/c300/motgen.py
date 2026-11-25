import json
A=[]  # (state,name,dur,ease,iter,frames[(off,dict)])
def add(s,n,d,e,i,fr): A.append((s,n,d,e,i,fr))
def sym(k,v): return [(0,{}),(.5,{k:v}),(1,{})]
# ожидание 1-20
for a in (3,5,8,12): add('wait','float-%d'%a,3.2,'ease-in-out','infinite',sym('y',-a))
for s in (1.02,1.04,1.07): add('wait','breathe-%s'%s,3.6,'ease-in-out','infinite',sym('scale',s))
for r in (2,4,7): add('wait','sway-%d'%r,4,'ease-in-out','infinite',[(0,{'rot':-r}),(.5,{'rot':r}),(1,{'rot':-r})])
for b in (1.1,1.25,1.4): add('wait','glow-%s'%b,2.8,'ease-in-out','infinite',sym('filter','brightness(%s)'%b))
for x in (4,8): add('wait','drift-%d'%x,5,'ease-in-out','infinite',[(0,{'x':-x}),(.5,{'x':x}),(1,{'x':-x})])
for h in (10,25): add('wait','hue-%d'%h,6,'linear','infinite',sym('filter','hue-rotate(%ddeg)'%h))
for r in (6,12): add('wait','tilt-%d'%r,4.5,'ease-in-out','infinite',[(0,{'rotY':-r}),(.5,{'rotY':r}),(1,{'rotY':-r})])
add('wait','blink-soft',3,'ease-in-out','infinite',sym('op',.6))
# думает 21-40
for t in (1.6,2.4,3.2): add('think','spin-%s'%t,t,'linear','infinite',[(0,{'rot':0}),(1,{'rot':360})])
for r in (4,8): add('think','orbit-%d'%r,2.2,'linear','infinite',[(0,{'x':r,'y':0}),(.25,{'x':0,'y':r}),(.5,{'x':-r,'y':0}),(.75,{'x':0,'y':-r}),(1,{'x':r,'y':0})])
for s in (3,6): add('think','skew-%d'%s,1.4,'ease-in-out','infinite',[(0,{'skew':-s}),(.5,{'skew':s}),(1,{'skew':-s})])
for o in (.35,.6): add('think','dots-%s'%o,1.1,'ease-in-out','infinite',sym('op',o))
for b in (1.3,1.6): add('think','scan-%s'%b,1.8,'ease-in-out','infinite',[(0,{'filter':'brightness(1)'}),(.5,{'filter':'brightness(%s)'%b}),(1,{'filter':'brightness(1)'})])
for s in (.9,.82): add('think','squash-%s'%s,1.2,'ease-in-out','infinite',sym('scaleY',s))
for x in (2,4): add('think','twitch-%d'%x,.5,'linear','infinite',[(0,{}),(.25,{'x':-x}),(.75,{'x':x}),(1,{})])
for d in (2.4,): add('think','flip-%s'%d,d,'ease-in-out','infinite',[(0,{'rotY':0}),(1,{'rotY':360})])
for r in (10,18): add('think','pendulum-%d'%r,1.6,'ease-in-out','infinite',[(0,{'rot':-r}),(.5,{'rot':r}),(1,{'rot':-r})])
for b in (1,2): add('think','blur-%d'%b,1.6,'ease-in-out','infinite',sym('filter','blur(%dpx)'%b))
# говорит 41-55
for d in (.2,.3,.45): add('speak','talk-%s'%d,d,'ease-in-out','infinite',[(0,{'scaleY':1}),(.5,{'scaleY':.94}),(1,{'scaleY':1.04})])
for y in (2,4,6): add('speak','nod-%d'%y,.6,'ease-in-out','infinite',sym('y',y))
for s in (8,14,22): add('speak','ripple-%d'%s,.9,'ease-out','infinite',[(0,{'filter':'drop-shadow(0 0 0 rgba(233,180,101,.7))'}),(1,{'filter':'drop-shadow(0 0 %dpx rgba(233,180,101,0))'%s})])
for s in (.96,.9): add('speak','jaw-%s'%s,.25,'ease-in-out','infinite',sym('scaleX',s))
for y in (3,6): add('speak','hop-%d'%y,.5,'ease-out','infinite',[(0,{'y':0}),(.4,{'y':-y}),(1,{'y':0})])
add('speak','eq-a',.35,'steps(3)','infinite',[(0,{'scaleY':.9}),(.33,{'scaleY':1.1}),(.66,{'scaleY':.95}),(1,{'scaleY':1.05})])
add('speak','eq-b',.5,'steps(4)','infinite',[(0,{'scaleY':1}),(.25,{'scaleY':1.12}),(.5,{'scaleY':.9}),(.75,{'scaleY':1.06}),(1,{'scaleY':1})])
# радость 56-75
for h in (10,16,24): add('joy','bounce-%d'%h,.9,'cubic-bezier(.3,.9,.4,1)',3,[(0,{'y':0}),(.4,{'y':-h}),(.6,{'y':-h}),(1,{'y':0})])
for h in (12,20,30): add('joy','jump-squash-%d'%h,.8,'ease-out',3,[(0,{'y':0,'scaleY':1}),(.2,{'y':0,'scaleY':.85}),(.5,{'y':-h,'scaleY':1.1}),(1,{'y':0,'scaleY':1})])
for s in (1.15,1.3): add('joy','tada-%s'%s,1,'ease-in-out',1,[(0,{'scale':1}),(.2,{'scale':.9,'rot':-4}),(.4,{'scale':s,'rot':4}),(.6,{'scale':s,'rot':-4}),(.8,{'scale':s,'rot':4}),(1,{'scale':1,'rot':0})])
for s in (8,14): add('joy','jello-%d'%s,.9,'ease-in-out',1,[(0,{}),(.22,{'skew':-s}),(.44,{'skew':s*.7}),(.66,{'skew':-s*.4}),(.88,{'skew':s*.2}),(1,{})])
for s in (1.1,1.2): add('joy','heartbeat-%s'%s,1.1,'ease-in-out',2,[(0,{'scale':1}),(.14,{'scale':s}),(.28,{'scale':1}),(.42,{'scale':s}),(.7,{'scale':1}),(1,{'scale':1})])
for s in (.6,.8): add('joy','spin-pop-%s'%s,.9,'ease-out',1,[(0,{'rot':0,'scale':s}),(.6,{'rot':360,'scale':1.2}),(1,{'rot':360,'scale':1})])
for r in (8,14): add('joy','wiggle-%d'%r,.7,'ease-in-out',3,[(0,{'rot':0}),(.25,{'rot':-r}),(.75,{'rot':r}),(1,{'rot':0})])
for s in (1.25,1.4): add('joy','rubber-%s'%s,.9,'ease-out',1,[(0,{'scaleX':1,'scaleY':1}),(.3,{'scaleX':s,'scaleY':.75}),(.5,{'scaleX':.8,'scaleY':1.2}),(.7,{'scaleX':1.1,'scaleY':.9}),(1,{'scaleX':1,'scaleY':1})])
for b in (1.5,2): add('joy','flash-gold-%s'%b,.8,'ease-out',2,[(0,{'filter':'brightness(1)'}),(.3,{'filter':'brightness(%s) saturate(1.5)'%b}),(1,{'filter':'brightness(1)'})])
# тревога 76-90
for x in (6,10,14): add('alarm','shake-%d'%x,.5,'linear',3,[(0,{'x':0}),(.2,{'x':-x}),(.4,{'x':x}),(.6,{'x':-x*.6}),(.8,{'x':x*.6}),(1,{'x':0})])
for r in (6,12): add('alarm','headshake-%d'%r,.7,'ease-in-out',2,[(0,{'rotY':0}),(.25,{'rotY':-r}),(.75,{'rotY':r}),(1,{'rotY':0})])
for o in (.2,.4,.6): add('alarm','flash-%s'%o,.6,'steps(2)','infinite',[(0,{'op':1}),(.5,{'op':o}),(1,{'op':1})])
for s in (10,20): add('alarm','pulse-red-%d'%s,.8,'ease-out','infinite',[(0,{'filter':'drop-shadow(0 0 0 rgba(255,90,80,.9))'}),(1,{'filter':'drop-shadow(0 0 %dpx rgba(255,90,80,0))'%s})])
for x in (1,2): add('alarm','vibrate-%d'%x,.12,'linear','infinite',[(0,{'x':-x,'y':x}),(.5,{'x':x,'y':-x}),(1,{'x':-x,'y':x})])
add('alarm','heavy-bounce',.8,'cubic-bezier(.5,0,.8,.5)',2,[(0,{'y':0}),(.5,{'y':14}),(1,{'y':0})])
for r in (10,16): add('alarm','wobble-hard-%d'%r,.8,'ease-in-out',2,[(0,{'rot':0,'x':0}),(.15,{'rot':-r,'x':-8}),(.45,{'rot':r*.6,'x':6}),(.75,{'rot':-r*.3,'x':-3}),(1,{'rot':0,'x':0})])
# переходы 91-100 (вход)
T=[('fade-in',[(0,{'op':0}),(1,{})]),('fade-up',[(0,{'op':0,'y':24}),(1,{})]),('fade-down',[(0,{'op':0,'y':-24}),(1,{})]),('slide-left',[(0,{'op':0,'x':40}),(1,{})]),('slide-right',[(0,{'op':0,'x':-40}),(1,{})]),('zoom-in',[(0,{'op':0,'scale':.92}),(1,{})]),('zoom-out',[(0,{'op':0,'scale':1.08}),(1,{})]),('flip-in',[(0,{'op':0,'rotY':-35}),(1,{})]),('blur-in',[(0,{'op':0,'filter':'blur(8px)'}),(1,{})]),('rotate-in',[(0,{'op':0,'rot':-6,'scale':.96}),(1,{})])]
for n,f in T: add('trans',n,.45,'cubic-bezier(.2,.7,.2,1)',1,f)
assert len(A)==100,len(A)
def tr(p):
    t=[]
    if 'x' in p or 'y' in p: t.append('translate(%gpx,%gpx)'%(p.get('x',0),p.get('y',0)))
    if 'scale' in p: t.append('scale(%g)'%p['scale'])
    if 'scaleX' in p or 'scaleY' in p: t.append('scale(%g,%g)'%(p.get('scaleX',1),p.get('scaleY',1)))
    if 'rot' in p: t.append('rotate(%gdeg)'%p['rot'])
    if 'rotY' in p: t.append('perspective(600px) rotateY(%gdeg)'%p['rotY'])
    if 'skew' in p: t.append('skewX(%gdeg)'%p['skew'])
    return t
css=['/* K5 motion100: 100 анимаций ANM-001..100. Собственные пресеты в духе Animate.css / Hover.css / Magic.css (MIT-стиль), без внешнего кода. Генерировано. */']
js=[]
for i,(s,n,d,e,it,fr) in enumerate(A,1):
    k='anm-%03d'%i;body=[]
    for off,p in fr:
        t=tr(p);o='%g%%{'%(off*100)
        if t:o+='transform:'+' '.join(t)+';'
        if 'op' in p:o+='opacity:%g;'%p['op']
        if 'filter' in p:o+='filter:'+p['filter']+';'
        body.append(o+'}')
    css.append('@keyframes %s{%s}.%s{animation:%s %gs %s %s %s;transform-origin:50%% 50%%}'%(k,''.join(body),k,k,d,e,'infinite' if it=='infinite' else it,'backwards' if s=='trans' else 'both'))
    js.append([i,s,n,d,e,it,[[off,p] for off,p in fr]])
css.append('@media(prefers-reduced-motion:reduce){[class*="anm-"]{animation:none!important}}')
open('/home/claude/k5src/nox-k5-motion100.css','w').write('\n'.join(css)+'\n')
data=json.dumps(js,ensure_ascii=False,separators=(',',':'))
src='''/* K5 motion100: ANM-001..100, пресеты GSAP (vendor/gsap) + CSS-классы .anm-NNN. Состояния: wait/think/speak/joy/alarm, переходы trans (ANM-091..100).
   API: NOXMotion.play(el,id|state), .stop(el), .state(name), .list. Привязка: талисман #k5-mc (data-state), событие 'nox:state', вход страницы (случайный ANM-091..100 по адресу). */
(function(){ if(window.NOXMotion)return;
 const T=%s;
 const S={wait:'ожидание',think:'думает',speak:'говорит',joy:'радость',alarm:'тревога',trans:'переход'};
 const MAP={idle:'wait',listen:'wait',think:'think',speak:'speak',joy:'joy',alarm:'alarm',wait:'wait'};
 const reduce=matchMedia('(prefers-reduced-motion:reduce)').matches;
 function gprops(p){const o={};if('x' in p)o.x=p.x;if('y' in p)o.y=p.y;if('scale' in p)o.scale=p.scale;if('scaleX' in p)o.scaleX=p.scaleX;if('scaleY' in p)o.scaleY=p.scaleY;if('rot' in p)o.rotation=p.rot;if('rotY' in p)o.rotationY=p.rotY;if('skew' in p)o.skewX=p.skew;if('op' in p)o.opacity=p.op;if('filter' in p)o.filter=p.filter;return o}
 function pick(s,seed){const a=T.filter(function(t){return t[1]===s});return a[(seed||0)%%a.length]}
 const M=window.NOXMotion={list:T.map(function(t){return{id:'ANM-'+String(t[0]).padStart(3,'0'),state:t[1],name:t[2]}}),states:S,cur:null,
  find:function(x){return typeof x==='number'?T[x-1]:(typeof x==='string'&&/^ANM-/.test(x)?T[+x.slice(4)-1]:pick(MAP[x]||x,Date.now()%%7))},
  stop:function(el){if(!el)return;if(el._anm){try{el._anm.kill()}catch(e){}el._anm=null}el.className=(el.className&&el.className.baseVal!==undefined?el.className.baseVal:String(el.className)).replace(/\\banm-\\d+\\b/g,'').trim()},
  play:function(el,x){ if(!el||reduce)return null;const t=M.find(x);if(!t)return null;M.stop(el);M.cur='ANM-'+String(t[0]).padStart(3,'0');el.dataset.anm=M.cur;
   const g=window.gsap;
   if(g&&t[1]!=='trans'){const fr=t[6].map(function(f){return Object.assign({},gprops(f[1]),{duration:t[3]/Math.max(1,t[6].length-1)})}).slice(1);
    const base=gprops(t[6][0][1]);g.set(el,Object.assign({x:0,y:0,scale:1,rotation:0,opacity:1},base));
    el._anm=g.to(el,{keyframes:fr,ease:'none',repeat:t[5]==='infinite'?-1:t[5]-1,transformPerspective:600,onComplete:function(){g.set(el,{clearProps:'all'})}});return el._anm}
   el.classList.add('anm-'+String(t[0]).padStart(3,'0'));return null},
  state:function(name,el){const tg=el||document.querySelector('#k5-mc svg')||document.querySelector('#k5-pulse')||document.querySelector('#k4-fab');document.documentElement.dataset.noxState=name;M.play(tg,MAP[name]||name);window.dispatchEvent(new CustomEvent('nox:state',{detail:name}))}};
 function ready(f){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',f);else f()}
 ready(function(){
  const L=document.createElement('script');L.src='./vendor/gsap/gsap.min.js';L.onload=function(){const m=document.getElementById('k5-mc');if(m)M.state(m.dataset.state)};document.head.appendChild(L);
  const pg=document.getElementById('page');if(pg&&!reduce){const t=pick('trans',location.pathname.length);try{pg.animate(gAnim(t),{duration:t[3]*1000,easing:t[4],fill:'none'})}catch(e){}}
  const tick=setInterval(function(){const m=document.getElementById('k5-mc');if(!m)return;clearInterval(tick);new MutationObserver(function(){M.state(m.dataset.state)}).observe(m,{attributes:true,attributeFilter:['data-state']});M.state(m.dataset.state)},400);
  setTimeout(function(){clearInterval(tick)},12000);
 });
 function gAnim(t){return t[6].map(function(f){const p=f[1],o={offset:f[0]},tt=[];if('x' in p||'y' in p)tt.push('translate('+(p.x||0)+'px,'+(p.y||0)+'px)');if('scale' in p)tt.push('scale('+p.scale+')');if('rot' in p)tt.push('rotate('+p.rot+'deg)');if('rotY' in p)tt.push('perspective(600px) rotateY('+p.rotY+'deg)');if(tt.length)o.transform=tt.join(' ');if('op' in p)o.opacity=p.op;if('filter' in p)o.filter=p.filter;return o})}
})();
'''%data
open('/home/claude/k5src/nox-k5-motion100.js','w').write(src)
# MOTION100.md
L=['# MOTION100: 100 анимаций NOX (K5)','','Источник: собственные пресеты (CSS @keyframes + GSAP keyframes), написанные в духе перечисленных открытых библиотек. Код сторонних библиотек НЕ копировался и не скачивался (Animate.css, Hover.css, Magic.css, AutoAnimate в vendor отсутствуют; GSAP, Motion, Lottie-web есть в vendor).','Лицензия кода пресетов: проект NOX (свой код). Вдохновение/названия приёмов: Animate.css (MIT, bounce/tada/jello/rubberBand/shakeX/headShake/flash/fadeIn*), Hover.css (MIT, float/bob/pulse/wobble), Magic.css (MIT, puffIn/swap-перспектива), GSAP (Standard no-charge, vendor/gsap, исполнитель keyframes), AutoAnimate (MIT, идея мягких входов).','Файлы: site/nox-k5-motion100.css (классы .anm-001…100), site/nox-k5-motion100.js (NOXMotion.play(el,id|состояние), пресеты GSAP, привязка к состояниям).','Применено: chat.html (талисман #k5-mc, состояния idle/listen->ожидание, think->думает, speak->говорит; переход страницы), index.html и voice.html (переход страницы, NOXMotion.state(name) для радости/тревоги).','','| ID | Состояние | Название | Длит., с | Повторы | Где применено |','|---|---|---|---|---|---|']
for i,(s,n,d,e,it,fr) in enumerate(A,1):
    L.append('| ANM-%03d | %s | %s | %g | %s | %s |'%(i,{'wait':'ожидание','think':'думает','speak':'говорит','joy':'радость','alarm':'тревога','trans':'переход (вход страницы)'}[s],n,d,it,'талисман/#page' if s in('wait','think','speak','trans') else 'NOXMotion.state("%s")'%('joy' if s=='joy' else 'alarm')))
open('/home/claude/k5src/MOTION100.md','w').write('\n'.join(L)+'\n')
