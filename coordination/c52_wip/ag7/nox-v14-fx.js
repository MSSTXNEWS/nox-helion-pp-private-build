/* NOX v14 FX — C14 след курсора, C15 параллакс фона, C16 звуки WebAudio */
(function(){'use strict';if(window.NOX_V14_FX)return;window.NOX_V14_FX=true;
var D=document,R=D.documentElement,W=window,LS='nox.v14.fx.';
var mq=function(q){try{return W.matchMedia(q).matches}catch(e){return false}};
var fine=function(){return mq('(pointer:fine)')},reduced=function(){return mq('(prefers-reduced-motion: reduce)')},lite=function(){return R.hasAttribute('data-nox-lite')};
function get(k,def){try{var v=localStorage.getItem(LS+k);return v==null?def:v==='1'}catch(e){return def}}
function put(k,v){try{localStorage.setItem(LS+k,v?'1':'0')}catch(e){}}
var st={trail:get('trail',fine()),parallax:get('parallax',fine()),sound:get('sound',false)};
var raf=W.requestAnimationFrame.bind(W),now=function(){return performance.now()};

/* ---------- accent colour from shell palette ---------- */
var acc='234,186,119',accAt=0;
function accent(){var t=now();if(t-accAt<1500)return acc;accAt=t;var cs=getComputedStyle(R),g=cs.getPropertyValue('--glass-accent-rgb').trim();
 if(/^\d+\s*,\s*\d+\s*,\s*\d+$/.test(g)){acc=g.replace(/\s/g,'');return acc}
 var c=cs.getPropertyValue('--nv-acc').trim()||cs.getPropertyValue('--accent').trim();
 if(c){var s=D.createElement('i');s.style.color=c;s.style.display='none';D.body.appendChild(s);var m=getComputedStyle(s).color.match(/\d+(\.\d+)?/g);s.remove();if(m&&m.length>=3)acc=m.slice(0,3).map(function(x){return Math.round(+x)}).join(',')}
 return acc}

/* ---------- C14 trail ---------- */
var T={cv:null,ctx:null,pts:[],run:false,last:0,dpr:1};
function trailOK(){return st.trail&&fine()&&!reduced()&&!lite()}
function trailSize(){if(!T.cv)return;T.dpr=Math.min(W.devicePixelRatio||1,1.5);T.cv.width=Math.round(innerWidth*T.dpr);T.cv.height=Math.round(innerHeight*T.dpr)}
function trailMount(){if(T.cv)return;T.cv=D.createElement('canvas');T.cv.className='nxfx-trail';T.cv.setAttribute('aria-hidden','true');T.ctx=T.cv.getContext('2d');trailSize();D.body.appendChild(T.cv)}
function trailUnmount(){T.run=false;T.pts=[];if(T.cv){T.cv.remove();T.cv=null;T.ctx=null}}
var LIFE=420;
function trailFrame(){if(!T.run||!T.ctx)return;var t=now(),c=T.ctx,p=T.pts,d=T.dpr;
 while(p.length&&t-p[0].t>LIFE)p.shift();
 c.clearRect(0,0,T.cv.width,T.cv.height);
 if(p.length>1){var a=accent();c.lineCap='round';c.lineJoin='round';
  for(var pass=0;pass<2;pass++){for(var i=1;i<p.length;i++){var k=1-(t-p[i].t)/LIFE;if(k<=0)continue;
   c.beginPath();c.moveTo(p[i-1].x*d,p[i-1].y*d);c.lineTo(p[i].x*d,p[i].y*d);
   if(pass===0){c.strokeStyle='rgba('+a+','+(k*.16).toFixed(3)+')';c.lineWidth=(2+6*k)*d}
   else{c.strokeStyle='rgba('+a+','+(k*.85).toFixed(3)+')';c.lineWidth=(.6+1.4*k)*d}c.stroke()}}
  var h=p[p.length-1],kh=1-(t-h.t)/LIFE;if(kh>0){c.fillStyle='rgba(255,255,255,'+(kh*.7).toFixed(3)+')';c.beginPath();c.arc(h.x*d,h.y*d,1.6*d,0,6.283);c.fill()}}
 if(!p.length&&t-T.last>1000||D.hidden){T.run=false;c.clearRect(0,0,T.cv.width,T.cv.height);return}
 raf(trailFrame)}
function trailMove(e){if(!trailOK()||e.pointerType&&e.pointerType!=='mouse')return;trailMount();var t=now();T.last=t;
 var p=T.pts,l=p[p.length-1];if(!l||Math.abs(l.x-e.clientX)+Math.abs(l.y-e.clientY)>1.5){p.push({x:e.clientX,y:e.clientY,t:t});if(p.length>40)p.shift()}
 if(!T.run&&!D.hidden){T.run=true;raf(trailFrame)}}
function trailApply(){if(!trailOK())trailUnmount()}

/* ---------- C15 parallax ---------- */
var P={els:[],scanAt:0,tx:0,ty:0,cx:0,cy:0,run:false,AMP:8};
function pxOK(){return st.parallax&&fine()&&!reduced()&&!lite()}
function pxScan(force){var t=now();if(!force&&t-P.scanAt<3000&&P.els.length)return;P.scanAt=t;
 var vw=innerWidth,vh=innerHeight,found=[];
 D.querySelectorAll('canvas,video,.nox-page-scene,[data-nox-bg]').forEach(function(e){if(e===T.cv||e.closest('.nv-pal,.nox-v14-bar,.nv-side,.nv-assist,#messages,dialog'))return;
  var cs=getComputedStyle(e);if(cs.pointerEvents!=='none'&&e.tagName!=='VIDEO'&&!e.classList.contains('nox-page-scene'))return;
  if(cs.position!=='fixed'&&cs.position!=='absolute')return;var r=e.getBoundingClientRect();if(r.width<vw*.8||r.height<vh*.8)return;
  found.push({e:e,z:parseInt(cs.zIndex,10)||0,fixed:cs.position==='fixed',scale:cs.scale})});
 found.sort(function(a,b){return a.z-b.z});
 P.els.forEach(function(o){if(found.every(function(f){return f.e!==o.e}))pxClear(o)});
 found.forEach(function(f,i){f.depth=found.length>1?1-.55*i/(found.length-1):1;var old=P.els.filter(function(o){return o.e===f.e})[0];if(old)f.scale=old.scale;f.e.classList.add('nxfx-px');
  if(f.fixed&&(f.scale==='none'||!f.scale)&&!f.e.style.scale){f.e.style.scale='1.02';f.ownScale=true}else if(old)f.ownScale=old.ownScale});
 P.els=found}
function pxClear(o){o.e.style.translate='';if(o.ownScale)o.e.style.scale='';o.e.classList.remove('nxfx-px')}
function pxFrame(){if(!P.run)return;P.cx+=(P.tx-P.cx)*.08;P.cy+=(P.ty-P.cy)*.08;
 P.els.forEach(function(o){o.e.style.translate=(P.cx*o.depth).toFixed(2)+'px '+(P.cy*o.depth).toFixed(2)+'px'});
 if(Math.abs(P.tx-P.cx)<.02&&Math.abs(P.ty-P.cy)<.02||D.hidden){P.run=false;return}raf(pxFrame)}
function pxMove(e){if(!pxOK()||e.pointerType&&e.pointerType!=='mouse')return;pxScan(false);
 P.tx=-(e.clientX/innerWidth-.5)*2*P.AMP;P.ty=-(e.clientY/innerHeight-.5)*2*P.AMP;
 if(!P.run&&!D.hidden){P.run=true;raf(pxFrame)}}
function pxApply(){if(!pxOK()){P.run=false;P.tx=P.ty=P.cx=P.cy=0;P.els.forEach(pxClear);P.els=[]}}

/* ---------- C16 sound ---------- */
var A={ctx:null,gest:false,master:null,lastClick:0,VOL:.06};
function audio(){if(!st.sound||!A.gest)return null;
 if(!A.ctx){var AC=W.AudioContext||W.webkitAudioContext;if(!AC)return null;try{A.ctx=new AC();A.master=A.ctx.createGain();A.master.gain.value=A.VOL;A.master.connect(A.ctx.destination)}catch(e){A.ctx=null;return null}}
 if(A.ctx.state==='suspended')A.ctx.resume().catch(function(){});return A.ctx}
function env(c,g,t,a,peak,dec){g.gain.setValueAtTime(0.0001,t);g.gain.exponentialRampToValueAtTime(peak,t+a);g.gain.exponentialRampToValueAtTime(0.0001,t+a+dec)}
function click(){var c=audio();if(!c)return;var t=c.currentTime;if(t-A.lastClick<.04)return;A.lastClick=t;
 var o=c.createOscillator(),g=c.createGain();o.type='sine';o.frequency.setValueAtTime(1500,t);o.frequency.exponentialRampToValueAtTime(700,t+.05);env(c,g,t,.004,.5,.06);o.connect(g).connect(A.master);o.start(t);o.stop(t+.09)}
var noiseBuf=null;
function whoosh(){var c=audio();if(!c)return;var t=c.currentTime;
 if(!noiseBuf){noiseBuf=c.createBuffer(1,Math.round(c.sampleRate*.4),c.sampleRate);var d=noiseBuf.getChannelData(0);for(var i=0;i<d.length;i++)d[i]=Math.random()*2-1}
 var s=c.createBufferSource(),f=c.createBiquadFilter(),g=c.createGain();s.buffer=noiseBuf;f.type='bandpass';f.Q.value=1.4;f.frequency.setValueAtTime(400,t);f.frequency.exponentialRampToValueAtTime(2600,t+.22);
 env(c,g,t,.08,.55,.24);s.connect(f).connect(g).connect(A.master);s.start(t);s.stop(t+.36)}
function chime(){var c=audio();if(!c)return;var t=c.currentTime;[[660,0],[990,.07]].forEach(function(n){var o=c.createOscillator(),g=c.createGain();o.type='triangle';o.frequency.value=n[0];env(c,g,t+n[1],.01,.32,.5);o.connect(g).connect(A.master);o.start(t+n[1]);o.stop(t+n[1]+.55)})}
function gesture(){A.gest=true}
function onDown(e){gesture();if(!st.sound)return;var b=e.target&&e.target.closest&&e.target.closest('button,a[href],[role=button],.nv-btn,.nv-row,input[type=checkbox],select');if(b)click()}
var palObs=null,msgObs=null;
function hookPal(){var p=D.querySelector('.nv-pal');if(!p||p.dataset.nxfx)return!!p;p.dataset.nxfx='1';var was=p.hidden;
 palObs=new MutationObserver(function(){if(was&&!p.hidden)whoosh();was=p.hidden;if(!p.hidden)palGroup(p)});palObs.observe(p,{attributes:true,attributeFilter:['hidden'],childList:true,subtree:true});return true}
function hookMsgs(){var m=D.getElementById('messages');if(!m||m.dataset.nxfx)return;m.dataset.nxfx='1';var tq=0;
 msgObs=new MutationObserver(function(rs){for(var i=0;i<rs.length;i++)for(var j=0;j<rs[i].addedNodes.length;j++){var n=rs[i].addedNodes[j];if(n.nodeType===1&&n.classList.contains('msg')&&n.classList.contains('nox')){var t=now();if(t-tq>600){tq=t;chime()}return}}});
 msgObs.observe(m,{childList:true})}

/* ---------- Ctrl+K group ---------- */
var LABELS={trail:['След курсора','светящийся шлейф'],parallax:['Параллакс фона','фон следует за мышью ±8px'],sound:['Звуки интерфейса','тихий синтез WebAudio']};
function palGroup(p){var list=p.querySelector('#nvList'),q=p.querySelector('#nvQ');if(!list||list.querySelector('.nxfx-grp')||(q&&q.value))return;
 var h=D.createElement('div');h.className='nv-grp nxfx-grp';h.textContent='Эффекты';list.appendChild(h);
 Object.keys(LABELS).forEach(function(k){var b=D.createElement('button');b.type='button';b.className='nv-row nxfx-row';b.dataset.fx=k;
  b.innerHTML='<span>'+LABELS[k][0]+'<small style="display:block">'+LABELS[k][1]+'</small></span><span class="nxfx-st"></span>';paint(b);
  b.onclick=function(ev){ev.stopPropagation();set(k,!st[k]);paint(b);toast(LABELS[k][0]+': '+(st[k]?'вкл':'выкл'))};list.appendChild(b)})}
function paint(b){var on=st[b.dataset.fx],s=b.querySelector('.nxfx-st');s.textContent=on?'ВКЛ':'ВЫКЛ';s.classList.toggle('on',on);b.setAttribute('aria-pressed',on?'true':'false')}
function toast(m){try{if(W.NoxToast){typeof W.NoxToast==='function'?W.NoxToast(m):W.NoxToast.show&&W.NoxToast.show(m)}}catch(e){}}

/* ---------- API ---------- */
function set(k,v){if(!(k in st))return;st[k]=!!v;put(k,st[k]);if(k==='trail')trailApply();if(k==='parallax')pxApply();if(k==='sound'&&st.sound){gesture();click()}}
W.NoxFX={get state(){return {trail:st.trail,parallax:st.parallax,sound:st.sound}},set:set,toggle:function(k){set(k,!st[k]);return st[k]},
 play:function(n){({click:click,whoosh:whoosh,chime:chime}[n]||function(){})()},rescan:function(){pxScan(true);return P.els.map(function(o){return o.e})},
 get audioContext(){return A.ctx},get trailRunning(){return T.run}};

function onMove(e){trailMove(e);pxMove(e)}
function start(){W.addEventListener('pointermove',onMove,{passive:true});W.addEventListener('pointerdown',onDown,{passive:true,capture:true});
 W.addEventListener('keydown',gesture,{capture:true});W.addEventListener('resize',function(){trailSize();P.scanAt=0},{passive:true});
 D.addEventListener('visibilitychange',function(){if(D.hidden){T.run=false;P.run=false}});
 new MutationObserver(function(){trailApply();pxApply()}).observe(R,{attributes:true,attributeFilter:['data-nox-lite']});
 hookMsgs();var n=0,iv=setInterval(function(){var ok=hookPal();hookMsgs();if(ok&&++n>3||n>20)clearInterval(iv);if(!ok)n++},800)}
if(D.readyState==='loading')D.addEventListener('DOMContentLoaded',start);else start();
})();
