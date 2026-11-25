/* U: контекстные подсказки в настройках: при наведении/фокусе — название пункта и «Alt+клик: спросить NOX»; Alt+клик открывает мини-чат с готовым вопросом. API NOXuhints */
(function(){ if(window.NOXuhints)return;
 const SEL='button,sl-switch,sl-range,sl-select,sl-input,sl-checkbox,sl-radio,sl-tab,[role=tab],[role=switch],label';
 let tip,tm,cur;
 const clean=s=>String(s||'').replace(/\s+/g,' ').trim().slice(0,60);
 function name(e){return clean(e.getAttribute('aria-label')||e.getAttribute('label')||e.getAttribute('title')||e.textContent)}
 function mk(){tip=document.createElement('div');tip.id='u-hint';tip.setAttribute('role','tooltip');tip.style.cssText='position:fixed;z-index:9600;max-width:280px;padding:8px 12px;border-radius:12px;background:color-mix(in srgb,var(--ds-glass,#140f0f) 94%,transparent);color:var(--ds-ink,#efe6df);border:1px solid color-mix(in srgb,var(--ds-acc,var(--ds-acc,#e9b465)) 50%,transparent);font-size:14px;line-height:1.35;pointer-events:none;opacity:0;transition:opacity .15s;backdrop-filter:blur(12px)';document.body.appendChild(tip)}
 function show(e){const n=name(e);if(!n||n.length<2)return;if(!tip)mk();tip.innerHTML='<b></b><div style="opacity:.8">Alt+клик: спросить NOX об этом пункте</div>';tip.firstChild.textContent=n;const r=e.getBoundingClientRect();tip.style.left=Math.max(8,Math.min(innerWidth-296,r.left))+'px';tip.style.top=(r.bottom+8>innerHeight-60?r.top-64:r.bottom+8)+'px';tip.style.opacity='1';cur=e}
 function hide(){clearTimeout(tm);if(tip)tip.style.opacity='0';cur=null}
 function target(ev){const t=ev.target&&ev.target.closest&&ev.target.closest(SEL);return t&&t.closest('main,#page,.page,body')&&!t.closest('#nxdock,#nox-m-tab,.nmc,#u-hint')?t:null}
 function ask(e){const n=name(e);const q='Объясни настройку «'+n+'»: что она делает и когда её менять?';const fab=document.querySelector('.nmc-fab');if(fab&&!fab.classList.contains('on'))fab.click();let k=0;const t=setInterval(function(){const i=document.querySelector('.nmc textarea,.nmc input[type=text],.nmc input:not([type])');if(i){clearInterval(t);i.value=q;i.dispatchEvent(new Event('input',{bubbles:true}));i.focus()}else if(++k>20)clearInterval(t)},150)}
 document.addEventListener('pointerover',function(ev){if(ev.pointerType==='touch')return;const t=target(ev);if(!t||t===cur)return;clearTimeout(tm);tm=setTimeout(function(){show(t)},450)});
 document.addEventListener('pointerout',function(ev){if(target(ev))hide()});
 document.addEventListener('focusin',function(ev){const t=target(ev);if(t)show(t)});document.addEventListener('focusout',hide);
 document.addEventListener('click',function(ev){if(!ev.altKey)return;const t=target(ev);if(!t)return;ev.preventDefault();ev.stopPropagation();hide();ask(t)},true);
 window.NOXuhints={show:show,hide:hide,ask:ask};
})();
