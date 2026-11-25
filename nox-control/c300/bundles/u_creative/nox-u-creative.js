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
@media(max-width:800px){#dz{grid-template-columns:44px minmax(0,1fr)!important}}`;
 const IDEAS=['Нарисуй неоновый город под дождём, кинематографично','Портрет, 85 мм, мягкий свет, спокойный фон','Логотип для кофейни, минимализм','Улучши текущий рисунок: свет и композицию'];
 function style(){if(document.getElementById('u-creative-css'))return;const s=document.createElement('style');s.id='u-creative-css';s.textContent=css;document.head.appendChild(s)}
 function fit(){const b=document.querySelector('#dzBot [data-act=fit]');if(b)b.click();try{const cv=NOXDZ.cv,a=cv.getObjects().filter(function(o){return o.dzArt})[0];if(!a)return;const z=cv.getZoom(),c=a.getCenterPoint(),v=cv.viewportTransform.slice();v[4]=cv.getWidth()/2-c.x*z;v[5]=cv.getHeight()/2-c.y*z;cv.setViewportTransform(v);cv.requestRenderAll()}catch(e){}}
 function fabs(){const h=document.querySelector('#k8-chat .k8c-h');if(!h)return false;['k8-prompt-b','k8-album-b'].forEach(function(id){const e=document.getElementById(id);if(e&&e.parentElement!==h){e.classList.add('u-fab');h.appendChild(e)}});return true}
 function empty(){const f=document.getElementById('k8c-f');if(!f)return;const has=function(){return f.querySelector('.k8c-m')};
  const upd=function(){const e=f.querySelector('.u-empty');if(has()){e&&e.remove();return}if(e)return;const d=document.createElement('div');d.className='u-empty';d.innerHTML='<b>Что нарисуем?</b><span>Опиши идею или выбери подсказку. ИИ нарисует, оценит и улучшит до трёх раз.</span>'+IDEAS.map(function(t,i){return '<button type="button" data-i="'+i+'">'+t+'</button>'}).join('');
   d.addEventListener('click',function(e){const b=e.target.closest('button');if(!b)return;const t=IDEAS[+b.dataset.i];if(window.K8studio)K8studio.send(/^Улучши/.test(t)?t:'/рисуй '+t)});f.appendChild(d)};
  upd();new MutationObserver(upd).observe(f,{childList:true})}
 function init(){style();const t=setInterval(function(){if(document.getElementById('dzBot')&&document.getElementById('k8-chat')&&window.NOXDZ){clearInterval(t);fabs();empty();setTimeout(fit,500);setTimeout(fit,1800);let r;addEventListener('resize',function(){clearTimeout(r);r=setTimeout(fit,250)});const st=document.getElementById('dzStage');if(window.ResizeObserver&&st)new ResizeObserver(function(){clearTimeout(r);r=setTimeout(fit,200)}).observe(st)}},300);setTimeout(function(){clearInterval(t)},20000)}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
 window.NOXucreative={fit:fit,fabs:fabs};
})();
