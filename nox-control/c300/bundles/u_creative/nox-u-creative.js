/* U: вау-слой студии дизайна: большое полотно (авто-«Вписать»), спокойный тёмный фон, стеклянные панели, перенос плавающих кнопок в шапку чата, живое пустое состояние с подсказками ИИ. API NOXucreative */
(function(){ if(window.NOXucreative)return;
 const css=`
#k8-studio{background:radial-gradient(1200px 700px at 38% 30%,rgba(60,48,40,.35),rgba(12,10,10,.0) 70%),#0c0a0a;gap:10px;padding:0 8px 8px;box-sizing:border-box}
#k8-cv{border-radius:18px}
#dz{grid-template-columns:52px minmax(0,1fr) 272px!important;gap:8px!important;padding:8px!important;font-family:inherit}
#dz .dz-g,#dzSide{background:linear-gradient(160deg,rgba(255,255,255,.08),rgba(255,255,255,.025));backdrop-filter:blur(18px) saturate(1.3);-webkit-backdrop-filter:blur(18px) saturate(1.3);border:1px solid rgba(255,255,255,.10);border-radius:16px;box-shadow:0 10px 34px rgba(0,0,0,.28)}
#dzStage{border-radius:18px;background:radial-gradient(900px 600px at 50% 40%,rgba(255,255,255,.045),rgba(0,0,0,0) 70%),#0f0d0d;box-shadow:inset 0 0 60px rgba(0,0,0,.55),0 0 36px var(--k8-glow,transparent);transition:box-shadow 1.2s}
#dz label,#dz .l,#dz sl-tab,#dz button,#dz sl-button,#dz sl-select{font-family:inherit!important;font-size:14px}
#dz sl-icon-button,#dz sl-button,#dz sl-tab{min-width:44px;min-height:44px}
#k8-chat{border-radius:18px;border:1px solid rgba(255,255,255,.10);background:linear-gradient(170deg,rgba(255,255,255,.07),rgba(255,255,255,.02));backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);box-shadow:0 10px 34px rgba(0,0,0,.28),0 0 30px var(--k8-glow,transparent)}
.k8c-h{flex-wrap:wrap}.k8c-h .u-fab{position:static!important;inset:auto!important;transform:none!important;margin:0!important;min-height:44px;border-radius:12px;font-size:14px;width:auto!important}
.u-empty{margin:auto;max-width:340px;text-align:center;display:flex;flex-direction:column;gap:10px;align-items:stretch;padding:16px;border-radius:18px;border:1px dashed rgba(255,255,255,.2);animation:uep 3.2s ease-in-out infinite}
@keyframes uep{50%{box-shadow:0 0 28px var(--k8-glow,rgba(233,180,101,.22))}}
.u-empty b{font-size:16px}.u-empty span{opacity:.8;font-size:14px}
.u-empty button{min-height:44px;border-radius:12px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.07);color:inherit;font-size:14px;padding:6px 12px;cursor:pointer;transition:transform .15s,background .2s}
.u-empty button:hover{transform:translateY(-1px);background:rgba(233,180,101,.18)}
@media(max-width:800px){#dz{grid-template-columns:44px minmax(0,1fr)!important}}
:root{--u-s1:8px;--u-s2:16px;--u-s3:24px;--u-t-sm:14px;--u-t-md:16px;--u-t-lg:20px;--u-gold:#e9b465}
#dz :is(button,sl-button,sl-icon-button,sl-tab,sl-select,input,textarea):focus-visible,#k8-chat :is(button,textarea,input,sl-select):focus-visible,.u-empty button:focus-visible{outline:2px solid var(--u-gold);outline-offset:2px;border-radius:12px}
#k8-chat button,#k8-chat .k4-btn{min-height:44px;padding:0 var(--u-s2);border-radius:12px;font-size:var(--u-t-sm);display:inline-flex;align-items:center;gap:var(--u-s1);transition:transform .15s,background .2s,box-shadow .2s;font-family:inherit}
#k8-chat .k4-btn:not(.pri){background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);color:inherit}
#k8-chat .k4-btn.pri{background:linear-gradient(180deg,#f0c27a,#d9a35a);color:#1a1208;border:0;font-weight:600;box-shadow:0 4px 18px rgba(233,180,101,.28)}
#k8c-role{min-width:150px}
#k8-chat button:hover{transform:translateY(-1px)}#k8-chat button:active{transform:translateY(0) scale(.98)}
.k8c-h,.k8c-i{padding:var(--u-s1) var(--u-s2);gap:var(--u-s1)}
.k8c-m{font-size:var(--u-t-sm);animation:ufi .28s ease-out both}
@keyframes ufi{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
#dz .dz-g,#dzSide,#k8-chat{animation:ufi .5s ease-out both}#dzSide{animation-delay:.08s}#k8-chat{animation-delay:.14s}
#dzStage.u-gen{box-shadow:inset 0 0 60px rgba(0,0,0,.55),0 0 0 1px rgba(233,180,101,.55),0 0 38px rgba(233,180,101,.35);animation:ugen 1.6s ease-in-out infinite}
@keyframes ugen{50%{box-shadow:inset 0 0 60px rgba(0,0,0,.55),0 0 0 1px rgba(233,180,101,.9),0 0 56px rgba(233,180,101,.55)}}
#u-hk,#u-pv{max-width:min(520px,92vw)}#u-hk table{width:100%;border-collapse:collapse}#u-hk td{padding:var(--u-s1);border-bottom:1px solid rgba(255,255,255,.1);font-size:var(--u-t-sm)}#u-hk kbd{padding:2px 8px;border-radius:6px;border:1px solid rgba(255,255,255,.25);background:rgba(255,255,255,.08)}
#u-pv pre{white-space:pre-wrap;font:inherit;font-size:var(--u-t-sm);background:rgba(255,255,255,.06);padding:var(--u-s1) 12px;border-radius:10px;margin:4px 0 var(--u-s1)}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}`;
 const IDEAS=['Нарисуй неоновый город под дождём, кинематографично','Портрет, 85 мм, мягкий свет, спокойный фон','Логотип для кофейни, минимализм','Улучши текущий рисунок: свет и композицию'];
 function style(){if(document.getElementById('u-creative-css'))return;const s=document.createElement('style');s.id='u-creative-css';s.textContent=css;document.head.appendChild(s)}
 function fit(){const b=document.querySelector('#dzBot [data-act=fit]');if(b)b.click();try{const cv=NOXDZ.cv,a=cv.getObjects().filter(function(o){return o.dzArt})[0];if(!a)return;if(a.fill&&typeof a.fill==='object'){a.set('fill','#f3efe9')}const z=cv.getZoom(),c=a.getCenterPoint(),v=cv.viewportTransform.slice();v[4]=cv.getWidth()/2-c.x*z;v[5]=cv.getHeight()/2-c.y*z;cv.setViewportTransform(v);cv.requestRenderAll()}catch(e){}}
 function fabs(){const h=document.querySelector('#k8-chat .k8c-h');if(!h)return false;['k8-prompt-b','k8-album-b'].forEach(function(id){const e=document.getElementById(id);if(e&&e.parentElement!==h){e.classList.add('u-fab');h.appendChild(e)}});return true}
 function empty(){const f=document.getElementById('k8c-f');if(!f)return;const has=function(){return f.querySelector('.k8c-m')};
  const upd=function(){const e=f.querySelector('.u-empty');if(has()){e&&e.remove();return}if(e)return;const d=document.createElement('div');d.className='u-empty';d.innerHTML='<b>Что нарисуем?</b><span>Опиши идею или выбери подсказку. ИИ нарисует, оценит и улучшит до трёх раз.</span>'+IDEAS.map(function(t,i){return '<button type="button" data-i="'+i+'">'+t+'</button>'}).join('');
   d.addEventListener('click',function(e){const b=e.target.closest('button');if(!b)return;const t=IDEAS[+b.dataset.i];if(window.K8studio)K8studio.send(/^Улучши/.test(t)?t:'/рисуй '+t)});f.appendChild(d)};
  upd();new MutationObserver(upd).observe(f,{childList:true})}

 const HK=[['Ctrl+0','Вписать полотно'],['+ / −','Увеличить / уменьшить'],['Ctrl+1','100%'],['Esc','STOP: остановить рисование и голос'],['/рисуй …','Нарисовать из чата'],['Alt+клик','Спросить NOX о пункте (настройки)'],['?','Эта панель']];
 function dlg(id,title,html){let d=window.K4&&K4.modal?K4.modal(id,title):null;if(!d){d=document.getElementById(id);if(!d){d=document.createElement('sl-dialog');d.id=id;document.body.appendChild(d)}d.label=title}d.innerHTML=html;return d}
 function hotkeys(){const d=dlg('u-hk','Горячие клавиши','<table>'+HK.map(function(r){return '<tr><td><kbd>'+r[0]+'</kbd></td><td>'+r[1]+'</td></tr>'}).join('')+'</table>');customElements.whenDefined('sl-dialog').then(function(){d.show()})}
 function hkBtn(){const h=document.querySelector('#k8-chat .k8c-h');if(!h||document.getElementById('u-hkb'))return;const b=document.createElement('button');b.type='button';b.id='u-hkb';b.className='k4-btn';b.textContent='Клавиши';b.setAttribute('aria-label','Горячие клавиши');b.addEventListener('click',hotkeys);h.appendChild(b);document.addEventListener('keydown',function(e){if(e.key==='?'&&!/INPUT|TEXTAREA/.test((e.target||{}).tagName||'')&&!(e.target&&e.target.isContentEditable))hotkeys()})}
 let pvOk=false;function preview(){document.addEventListener('click',function(e){const b=e.target.closest&&e.target.closest('#k8-go');if(!b||pvOk)return;const pos=document.getElementById('k8-pos'),neg=document.getElementById('k8-neg');if(!pos||!pos.value.trim())return;e.stopImmediatePropagation();e.preventDefault();const esc=function(t){return String(t).replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c]})};const nb=document.getElementById('k8-nsw');const hasNeg=neg&&nb&&nb.checked&&neg.value.trim();
   const d=dlg('u-pv','Предпросмотр запроса','<b>Позитив</b><pre>'+esc(pos.value.trim())+'</pre>'+(hasNeg?'<b>Негатив</b><pre>'+esc(neg.value.trim())+'</pre>':'<div style="opacity:.8">Негатив выключен.</div>')+'<div class="k8c-a"><button type="button" class="k4-btn" id="u-pv-no">Править</button><button type="button" class="k4-btn pri" id="u-pv-ok">Нарисовать</button></div>');customElements.whenDefined('sl-dialog').then(function(){d.show()});
   d.querySelector('#u-pv-no').onclick=function(){d.hide()};d.querySelector('#u-pv-ok').onclick=function(){d.hide();pvOk=true;b.click();pvOk=false}},true)}
 function genGlow(){const st=document.getElementById('k8c-st'),stage=document.getElementById('dzStage');if(!st||!stage)return;const upd=function(){stage.classList.toggle('u-gen',st.classList.contains('running'))};upd();new MutationObserver(upd).observe(st,{attributes:true,attributeFilter:['class']})}
 function anim(){import('./vendor/auto-animate/index.mjs').then(function(m){const f=m.default||m.autoAnimate;['k8c-f','dzLayers'].forEach(function(id){const e=document.getElementById(id);if(e)try{f(e,{duration:180})}catch(x){}})}).catch(function(){})}
 function init(){style();const t=setInterval(function(){if(document.getElementById('dzBot')&&document.getElementById('k8-chat')&&window.NOXDZ){clearInterval(t);fabs();empty();hkBtn();preview();genGlow();anim();setTimeout(fit,500);setTimeout(fit,1800);let r;addEventListener('resize',function(){clearTimeout(r);r=setTimeout(fit,250)});const st=document.getElementById('dzStage');if(window.ResizeObserver&&st)new ResizeObserver(function(){clearTimeout(r);r=setTimeout(fit,200)}).observe(st)}},300);setTimeout(function(){clearInterval(t)},20000)}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
 window.NOXucreative={fit:fit,fabs:fabs};
})();
