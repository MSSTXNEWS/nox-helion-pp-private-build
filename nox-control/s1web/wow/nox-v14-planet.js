/* NOX · фон-планета (выбор в «Настройки → Фон»). WebGL2-сфера: терминатор, атмосферное свечение, без жёстких контуров.
   Земля/Луна — текстуры Solar System Scope (CC BY 4.0, NASA); остальные тела — процедурные шейдеры. Выбор хранится в localStorage. */
(function(){'use strict';if(window.NOXPlanet)return;
var D=document,H=D.documentElement,KEY='nox:planet',SRC=(D.currentScript&&D.currentScript.src)||'';var BASE=SRC?SRC.replace(/[^\/]*$/,''):'./';
var PL=[{id:'none',name:'Только космос',kind:-1,note:'Без планеты: туманность и звёзды'},
{id:'mercury',name:'Меркурий',kind:1,tx:['vendor/nox-planets/2k_mercury.jpg'],note:'Фото-текстура SSS, запасная процедурная',atm:[.5,.5,.55]},
{id:'venus',name:'Венера',kind:2,tx:['vendor/nox-planets/2k_venus_surface.jpg'],note:'Фото-текстура SSS, запасная процедурная',atm:[1,.75,.4]},
{id:'earth',name:'Земля',kind:0,tx:['vendor/nox-planets/2k_earth_daymap.jpg','vendor/nox-planets/earth_daymap.jpg'],note:'Текстура Solar System Scope, CC BY 4.0 (NASA)',atm:[.3,.55,1]},
{id:'moon',name:'Луна',kind:0,tx:['vendor/nox-planets/2k_moon.jpg','vendor/nox-planets/moon.jpg'],note:'Текстура Solar System Scope, CC BY 4.0 (NASA)',atm:[.6,.6,.62],atmK:.15},
{id:'mars',name:'Марс',kind:3,tx:['vendor/nox-planets/2k_mars.jpg'],note:'Фото-текстура SSS, запасная процедурная',atm:[1,.5,.3]},
{id:'jupiter',name:'Юпитер',kind:4,tx:['vendor/nox-planets/2k_jupiter.jpg'],note:'Фото-текстура SSS, запасная процедурная',atm:[1,.8,.6]},
{id:'saturn',name:'Сатурн',kind:5,tx:['vendor/nox-planets/2k_saturn.jpg'],note:'Фото-текстура SSS, кольца процедурные',atm:[1,.85,.55],rings:1},
{id:'uranus',name:'Уран',kind:6,tx:['vendor/nox-planets/2k_uranus.jpg'],note:'Фото-текстура SSS, запасная процедурная',atm:[.5,.9,.95]},
{id:'neptune',name:'Нептун',kind:7,tx:['vendor/nox-planets/2k_neptune.jpg'],note:'Фото-текстура SSS, запасная процедурная',atm:[.3,.5,1]}];
function by(id){for(var i=0;i<PL.length;i++)if(PL[i].id===id)return PL[i];return PL[0]}
function load(){try{var v=localStorage.getItem(KEY);if(v)return by(v).id}catch(e){}return 'earth'}
var cur=load(),subs=[];var MF=null,mfP=null;function mfLoad(){if(mfP)return mfP;mfP=fetch(BASE+'vendor/nox-planets/manifest.json',{cache:'no-store'}).then(function(r){return r.ok?r.json():{files:['*']}}).then(function(j){MF=new Set(j.files||[])}).catch(function(){MF=new Set(['*'])});return mfP}
function cands(pl){var a=pl.tx||(pl.tex?[pl.tex]:[]);if(!MF||MF.has('*'))return a;return a.filter(function(p){return MF.has(p.split('/').pop())})}
var TXST={};/* id -> 'photo:<файл>' | 'procedural' (честный статус для настроек) */
function save(id){try{localStorage.setItem(KEY,id)}catch(e){}}
var VS='#version 300 es\nin vec2 p;out vec2 v;void main(){v=p;gl_Position=vec4(p,0.,1.);}';
var FS='#version 300 es\nprecision highp float;in vec2 v;out vec4 o;uniform sampler2D uT;uniform int uK;uniform float uRot,uAK,uTilt;uniform vec3 uAtm;uniform float uRing;\n'+
'float h3(vec3 p){p=fract(p*.3183099+.1);p*=17.;return fract(p.x*p.y*p.z*(p.x+p.y+p.z));}\n'+
'float n3(vec3 x){vec3 i=floor(x),f=fract(x);f=f*f*(3.-2.*f);return mix(mix(mix(h3(i),h3(i+vec3(1,0,0)),f.x),mix(h3(i+vec3(0,1,0)),h3(i+vec3(1,1,0)),f.x),f.y),mix(mix(h3(i+vec3(0,0,1)),h3(i+vec3(1,0,1)),f.x),mix(h3(i+vec3(0,1,1)),h3(i+vec3(1,1,1)),f.x),f.y),f.z);}\n'+
'float fb(vec3 p){float a=.5,s=0.;for(int i=0;i<5;i++){s+=a*n3(p);p=p*2.07+3.1;a*=.5;}return s;}\n'+
'vec3 surf(vec3 q,float lat,float lon){\n'+
' if(uK==0){vec2 uv=vec2(lon/6.28318+.5,lat/3.14159+.5);return texture(uT,uv).rgb;}\n'+
' if(uK==1){float c=fb(q*5.);float cr=smoothstep(.45,.5,fb(q*14.))*.18;return mix(vec3(.32,.30,.29),vec3(.62,.59,.55),c)-cr;}\n'+
' if(uK==2){vec3 w=q*2.2;w+=1.2*vec3(fb(q*3.+7.),fb(q*3.+13.),fb(q*3.+2.));float c=fb(w*1.6+vec3(0.,lon*.0,0.));return mix(vec3(.80,.62,.30),vec3(.97,.90,.72),smoothstep(.3,.75,c));}\n'+
' if(uK==3){float c=fb(q*3.2);float d=fb(q*9.+4.);vec3 col=mix(vec3(.45,.20,.10),vec3(.80,.42,.22),c);col=mix(col,vec3(.25,.12,.08),smoothstep(.55,.8,d)*.6);float cap=smoothstep(1.25,1.4,abs(lat));return mix(col,vec3(.93,.93,.95),cap);}\n'+
' if(uK==4){float w=fb(vec3(q.x*2.,q.y*.3,q.z*2.)*2.);float b=sin(lat*13.+w*3.2)*.5+.5;float b2=sin(lat*29.+w*5.)*.5+.5;vec3 col=mix(vec3(.55,.36,.22),vec3(.93,.84,.70),b);col=mix(col,vec3(.72,.50,.34),b2*.35);vec2 d=vec2((lon-1.2)*cos(lat+.45),(lat+.45)*1.6);float spot=smoothstep(.5,.15,length(d*vec2(1.,1.6)));return mix(col,vec3(.72,.28,.16),spot*.8);}\n'+
' if(uK==5){float w=fb(vec3(q.x*2.,q.y*.2,q.z*2.)*1.6);float b=sin(lat*18.+w*2.)*.5+.5;return mix(vec3(.62,.52,.36),vec3(.90,.80,.60),b);}\n'+
' if(uK==6){float b=sin(lat*9.+fb(q*2.)*1.5)*.5+.5;return mix(vec3(.55,.80,.84),vec3(.66,.88,.90),b);}\n'+
' float b=sin(lat*12.+fb(q*3.)*2.)*.5+.5;vec3 col=mix(vec3(.12,.25,.65),vec3(.22,.42,.85),b);float s=smoothstep(.3,.1,length(vec2((lon-2.)*cos(lat+.3),(lat+.3)*1.5)));col=mix(col,vec3(.05,.10,.30),s*.7);float st=smoothstep(.02,0.,abs(lat-.6+.1*fb(q*6.)))*.4;return col+st;}\n'+
'void main(){vec2 P=v;float R=uRing>.5?.40:.86;vec3 L=normalize(vec3(-.65,.45,.62));vec4 acc=vec4(0.);\n'+
' float ct=cos(uTilt),st2=sin(uTilt);\n'+
' /* кольца Сатурна: плоскость, наклонённая к лучу */\n'+
' float ringA=0.;vec3 ringC=vec3(0.);float ringZ=-9.;\n'+
' if(uRing>.5){vec2 q=P/R;float rz=-q.y*ct/st2;vec3 rp=vec3(q.x,q.y,rz);float rr=length(rp);if(rr>1.35&&rr<2.3){float band=.55+.45*sin(rr*48.)*sin(rr*17.+1.);float gap=smoothstep(.015,0.,abs(rr-1.88))*.9;ringA=clamp(band*(1.-gap)*smoothstep(1.35,1.45,rr)*smoothstep(2.3,2.2,rr),0.,1.)*.85;ringC=mix(vec3(.62,.52,.38),vec3(.88,.80,.64),band);ringZ=rz;float shade=1.;vec3 rl=rp;/* тень планеты на кольце */float t=dot(rl,L);vec3 cp=rl-L*t;if(t<0.&&length(cp)<1.)shade=.25;ringC*=shade;}}\n'+
' vec2 q=P/R;float r2=dot(q,q);vec3 col=vec3(0.);float a=0.;\n'+
' if(r2<1.){float z=sqrt(1.-r2);vec3 n=vec3(q,z);\n'+
'  float cy=cos(uTilt*.6),sy=sin(uTilt*.6);vec3 m=vec3(n.x,n.y*cy-n.z*sy,n.y*sy+n.z*cy);float lon=atan(m.x,m.z)+uRot;float lat=asin(clamp(m.y,-1.,1.));vec3 q3=vec3(sin(lon)*cos(lat),sin(lat),cos(lon)*cos(lat));\n'+
'  vec3 s=surf(q3,lat,lon);float nl=dot(n,L);float diff=smoothstep(-.12,.55,nl);float amb=.035;float limb=pow(z,.35);\n'+
'  col=s*(amb+diff*1.05)*(.65+.35*limb);\n'+
'  float fres=pow(1.-z,3.);float lit=smoothstep(-.35,.5,nl);col+=uAtm*fres*lit*uAK*1.3;\n'+
'  a=smoothstep(1.,.992,sqrt(r2));\n'+
'  if(ringA>0.&&ringZ>z){col=mix(col,ringC,ringA);}\n'+
' } else {\n'+
'  float rr=sqrt(r2);float lit=smoothstep(-.6,.6,dot(normalize(vec3(q,.2)),L));float gl=exp(-(rr-1.)*14.)*uAK*.55*lit;col=uAtm*gl;a=gl;\n'+
'  if(ringA>0.){col=mix(col,ringC,ringA);a=max(a,ringA);}\n'+
' }\n'+
' if(r2<1.&&ringA>0.&&ringZ<=sqrt(1.-r2)){} \n'+
' float alpha=clamp(a,0.,1.);o=vec4(col*alpha+((r2<1.)?vec3(0.):vec3(0.)),alpha);}';
function sh(g,t,s){var o=g.createShader(t);g.shaderSource(o,s);g.compileShader(o);if(!g.getShaderParameter(o,g.COMPILE_STATUS))throw new Error(g.getShaderInfoLog(o));return o}
var R=null;
function renderer(cv,opts){var g=cv.getContext('webgl2',{alpha:true,premultipliedAlpha:true,antialias:false,preserveDrawingBuffer:!!(opts&&opts.keep)});if(!g)return null;
 var p=g.createProgram();g.attachShader(p,sh(g,g.VERTEX_SHADER,VS));g.attachShader(p,sh(g,g.FRAGMENT_SHADER,FS));g.bindAttribLocation(p,0,'p');g.linkProgram(p);if(!g.getProgramParameter(p,g.LINK_STATUS))throw new Error(g.getProgramInfoLog(p));
 var b=g.createBuffer();g.bindBuffer(g.ARRAY_BUFFER,b);g.bufferData(g.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),g.STATIC_DRAW);var vao=g.createVertexArray();g.bindVertexArray(vao);g.enableVertexAttribArray(0);g.vertexAttribPointer(0,2,g.FLOAT,false,0,0);
 var U={};['uT','uK','uRot','uAK','uTilt','uAtm','uRing'].forEach(function(n){U[n]=g.getUniformLocation(p,n)});var texs={};
 function tex(pl,cb){if(!(pl.tx||pl.tex))return null;if(texs[pl.id])return texs[pl.id].t;if(!MF){mfLoad().then(function(){cb&&cb()});return null}var list=cands(pl),e={t:null,ok:false};texs[pl.id]=e;var t=g.createTexture();g.bindTexture(g.TEXTURE_2D,t);g.texImage2D(g.TEXTURE_2D,0,g.RGBA,1,1,0,g.RGBA,g.UNSIGNED_BYTE,new Uint8Array([20,20,30,255]));e.t=t;var i=0;
  (function next(){if(i>=list.length){TXST[pl.id]='procedural';cb&&cb();return}var im=new Image(),src=list[i++];im.onload=function(){g.bindTexture(g.TEXTURE_2D,t);g.pixelStorei(g.UNPACK_FLIP_Y_WEBGL,true);g.texImage2D(g.TEXTURE_2D,0,g.RGBA,g.RGBA,g.UNSIGNED_BYTE,im);g.generateMipmap(g.TEXTURE_2D);g.texParameteri(g.TEXTURE_2D,g.TEXTURE_MIN_FILTER,g.LINEAR_MIPMAP_LINEAR);g.texParameteri(g.TEXTURE_2D,g.TEXTURE_WRAP_S,g.REPEAT);g.texParameteri(g.TEXTURE_2D,g.TEXTURE_WRAP_T,g.CLAMP_TO_EDGE);e.ok=true;TXST[pl.id]='photo:'+src.split('/').pop();cb&&cb()};im.onerror=next;im.src=BASE+src})();return t}
 return{g:g,draw:function(pl,rot,w,h,cb){if(pl.kind<0){g.viewport(0,0,w,h);g.clearColor(0,0,0,0);g.clear(g.COLOR_BUFFER_BIT);return}
  g.viewport(0,0,w,h);g.clearColor(0,0,0,0);g.clear(g.COLOR_BUFFER_BIT);g.useProgram(p);g.bindVertexArray(vao);g.activeTexture(g.TEXTURE0);var t=tex(pl,cb),ent=texs[pl.id],useTex=!!(ent&&ent.ok);if(t)g.bindTexture(g.TEXTURE_2D,t);g.uniform1i(U.uT,0);g.uniform1i(U.uK,(pl.kind===0||useTex)?0:pl.kind);g.uniform1f(U.uRot,rot);g.uniform1f(U.uAK,pl.atmK==null?1:pl.atmK);g.uniform1f(U.uTilt,pl.rings?.42:.3);g.uniform3fv(U.uAtm,pl.atm||[.5,.6,.8]);g.uniform1f(U.uRing,pl.rings?1:0);g.drawArrays(g.TRIANGLES,0,3)}}}
/* ---------- фон ---------- */
var cv=null,rd=null,t0=performance.now(),run=false,last=0,reduce=false;
function small(){return innerWidth<=820||matchMedia('(pointer:coarse)').matches}
function layout(){if(!cv)return;var m=small(),vw=innerWidth,vh=innerHeight,idx=!!D.getElementById('stage');var s=m?Math.min(vw*1.05,vh*.6):Math.min(vh*.95,vw*.62);if(idx)s*=.62;var pl=by(cur);if(pl.rings)s*=1.25;
 cv.style.width=s+'px';cv.style.height=s+'px';
 if(m){cv.style.left=(vw-s)/2+'px';cv.style.right='auto';cv.style.bottom=(-s*.42)+'px'}else{cv.style.right=(-s*.18)+'px';cv.style.left='auto';cv.style.bottom=(-s*.2)+'px'}
 var px=Math.round(Math.min(s,m?420:640)*(m?.8:1)*Math.min(devicePixelRatio||1,m?1.5:1.5));px=Math.max(160,px);if(cv.width!==px){cv.width=px;cv.height=px}}
function frame(now,force){var pl=by(cur);if(!rd||pl.kind<0)return;var T=reduce?30:(now-t0)/1000;rd.draw(pl,T*.012+1.1,cv.width,cv.height,function(){frame(performance.now(),true)})}
function loop(now){if(!run)return;requestAnimationFrame(loop);if(now-last<100)return;last=now;frame(now)}
function applyBg(){var pl=by(cur);H.classList.toggle('nx-planet',pl.kind>=0);H.setAttribute('data-nox-planet',pl.id);
 if(pl.kind<0){if(cv)cv.style.display='none';return}
 if(!cv){cv=D.createElement('canvas');cv.id='nxPlanet';cv.setAttribute('aria-hidden','true');cv.style.cssText='position:fixed;z-index:-2;pointer-events:none;opacity:.92;display:block';D.body.insertBefore(cv,D.body.firstChild);try{rd=renderer(cv)}catch(e){rd=null}}
 if(!rd){cv.style.display='none';return}
 cv.style.display='block';layout();frame(performance.now(),true);if(!reduce&&!run){run=true;requestAnimationFrame(loop)}}
function set(id){cur=by(id).id;save(cur);applyBg();subs.forEach(function(f){try{f(cur)}catch(e){}});syncUI()}
/* ---------- превью и раздел в «Настройки» ---------- */
var ui=null;
function syncUI(){if(!ui)return;ui.querySelectorAll('[data-pl]').forEach(function(b){var on=b.getAttribute('data-pl')===cur;b.setAttribute('aria-checked',String(on));b.classList.toggle('on',on)})}
function buildUI(){var anchor=D.getElementById('workspacePanel');if(!anchor||D.getElementById('nxPlanets'))return;
 var sec=D.createElement('section');sec.id='nxPlanets';sec.className='nxp';sec.setAttribute('aria-label','Фон: планета');
 sec.innerHTML='<div class="nxp-h"><h2>Фон</h2><p>Планета за интерфейсом. Применяется сразу, запоминается на этом устройстве.</p></div><div class="nxp-g" role="radiogroup" aria-label="Планета"></div><p class="nxp-f">Земля и Луна — текстуры Solar System Scope (CC BY 4.0, данные NASA). Остальные тела нарисованы процедурно в шейдере — это не фотографии.</p>';
 var grid=sec.querySelector('.nxp-g');
 var th=D.createElement('canvas');th.width=th.height=160;var tr=null;try{tr=renderer(th,{keep:true})}catch(e){}
 PL.forEach(function(pl){var b=D.createElement('button');b.type='button';b.setAttribute('role','radio');b.setAttribute('data-pl',pl.id);b.setAttribute('aria-checked','false');
  var c=D.createElement('canvas');c.width=c.height=96;c.className='nxp-t';var x=c.getContext('2d');
  b.appendChild(c);var n=D.createElement('b');n.textContent=pl.name;b.appendChild(n);var s=D.createElement('span');s.textContent=pl.note;b.appendChild(s);
  b.addEventListener('click',function(){set(pl.id)});grid.appendChild(b);
  var paint=function(){if(!tr||pl.kind<0){x.fillStyle='#02030a';x.fillRect(0,0,96,96);x.fillStyle='rgba(255,255,255,.7)';for(var i=0;i<18;i++){x.fillRect((i*37)%96,(i*53)%96,1.4,1.4)}return}tr.draw(pl,1.6,160,160,function(){paint()});x.clearRect(0,0,96,96);x.fillStyle='#02030a';x.fillRect(0,0,96,96);x.drawImage(th,0,0,96,96)};paint()});
 anchor.parentNode.insertBefore(sec,anchor);ui=sec;syncUI()}
var css=D.createElement('style');css.textContent='.nxp{margin:0 0 20px;padding:16px;border-radius:12px;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.035);backdrop-filter:blur(14px);box-shadow:inset 0 1px 0 rgba(255,255,255,.10)}.nxp-h h2{margin:0 0 4px;font:700 14px/1.2 Inter,system-ui,sans-serif;letter-spacing:.14em;text-transform:uppercase}.nxp-h p{margin:0 0 14px;color:#cfd2d6;font-size:13px}'+
'.nxp-g{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:0;border:1px solid rgba(255,255,255,.08);border-radius:12px;overflow:hidden}.nxp-g button{all:unset;box-sizing:border-box;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:6px;padding:14px 8px;min-height:44px;border-right:1px solid rgba(255,255,255,.08);border-bottom:1px solid rgba(255,255,255,.08);text-align:center;color:#e9e3d8;transition:background .15s}.nxp-g button:hover{background:rgba(255,255,255,.05)}.nxp-g button.on{box-shadow:inset 0 -2px 0 var(--nxc-ac,#e0602a);background:rgba(255,255,255,.05)}.nxp-g button:focus-visible{outline:2px solid #fff;outline-offset:-2px}'+
'.nxp-g b{font:700 12px/1.2 Inter,system-ui,sans-serif;letter-spacing:.12em;text-transform:uppercase}.nxp-g span{font-size:11px;line-height:1.3;color:#cfd2d6}.nxp-t{width:72px;height:72px;border-radius:50%;background:#02030a}.nxp-f{margin:12px 0 0;font-size:12px;color:#cfd2d6}'+
'@media (max-width:600px){.nxp-g{grid-template-columns:repeat(2,minmax(0,1fr))}.nxp-t{width:64px;height:64px}}'+
'html.nx-planet .nox-page-scene{display:none!important}.nxc-theme,#nxrTheme{display:none!important}';
D.head.appendChild(css);
function init(){applyBg();buildUI();addEventListener('resize',function(){layout()});addEventListener('storage',function(e){if(e.key===KEY){cur=load();applyBg();syncUI()}});D.addEventListener('visibilitychange',function(){if(D.hidden)run=false;else if(!reduce&&by(cur).kind>=0&&!run){run=true;requestAnimationFrame(loop)}})}
window.NOXPlanet={status:function(id){return TXST[id||cur]||''},list:function(){return PL.slice()},get:function(){return cur},set:set,onchange:function(f){subs.push(f)}};
if(D.body)init();else D.addEventListener('DOMContentLoaded',init)})();
(function(){var s=document.createElement('style');s.textContent='html body .nxp-g button{height:auto!important;min-height:92px;padding:12px 8px!important;display:flex!important}html body .nxp-g .nxp-t{flex:none}';document.head.appendChild(s)})();
