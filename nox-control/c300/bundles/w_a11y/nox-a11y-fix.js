/* NOX a11y-fix (WEB): точечные aria-правки общих скриптов и готовых компонентов. Откат: ?a11y=0 */
(function(){if(/[?&]a11y=0/.test(location.search))return;
var st=document.createElement('style');st.textContent='.tb-t,.tb-i{min-height:44px}.tb-i{min-width:44px}#u-tab{min-width:44px}.nox-worlds-open{min-height:44px}#dkToggle{min-width:44px;min-height:44px}sl-button::part(base){min-height:44px}.tb-burger,.nmc-x,.nxsun-x{min-width:44px}.FIE_root button,.FIE_root [role=button]{min-width:44px}.tb-sun{min-height:44px}.nx-sr{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}sl-input.nx-hl::part(form-control-label),sl-textarea.nx-hl::part(form-control-label),sl-select.nx-hl::part(form-control-label){position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}';document.head.appendChild(st);
function $$(s,f){document.querySelectorAll(s).forEach(f)}
function fix(){
try{document.querySelectorAll('.tb-t,.tb-sun,.nox-worlds-open').forEach(function(e){if(getComputedStyle(e).display==='inline')e.style.display='inline-flex',e.style.alignItems='center'})}catch(e){}
$$('#nxdock[role=region]',function(e){e.removeAttribute('role')});
$$('#nxpult:not([role]),#nxnavx:not([role])',function(e){e.setAttribute('role','region')});
$$('[role=tablist]',function(e){if(!e.querySelector('[role=tab]')||e.classList.contains('nxm-side')){e.removeAttribute('role');e.querySelectorAll('[role=tab]').forEach(function(t){t.removeAttribute('role');if(t.hasAttribute('aria-selected')){t.setAttribute('aria-current',t.getAttribute('aria-selected')==='true'?'true':'false');t.removeAttribute('aria-selected')}})}});
$$('sl-input:not([label]),sl-textarea:not([label]),sl-select:not([label]),sl-range:not([label])',function(e){var t=e.getAttribute('aria-label')||e.title||e.getAttribute('placeholder')||e.getAttribute('name')||e.id||'Поле';e.setAttribute('label',t);e.classList.add('nx-hl')});
$$('sl-switch,sl-checkbox,sl-radio',function(e){if(!e.textContent.trim()){var s=document.createElement('span');s.className='nx-sr';s.textContent=e.getAttribute('aria-label')||e.title||e.getAttribute('name')||e.id||'Переключатель';e.appendChild(s)}});
$$('sl-button',function(e){if(!(e.innerText||'').trim()&&!e.querySelector('.nx-sr')){var s=document.createElement('span');s.className='nx-sr';s.textContent=e.getAttribute('aria-label')||e.title||e.id||'Кнопка';e.appendChild(s)}});
$$('sl-icon-button:not([label])',function(e){e.setAttribute('label',e.getAttribute('aria-label')||e.title||e.getAttribute('name')||'Кнопка')});
$$('textarea:not([aria-label]):not([aria-labelledby])',function(e){if(e.closest('label')||(e.id&&document.querySelector('label[for="'+e.id+'"]')))return;e.setAttribute('aria-label',e.placeholder||e.title||'Редактор')});
$$('input:not([aria-label]):not([aria-labelledby]):not([type=hidden])',function(e){if(e.closest('label')||e.closest('sl-input,sl-switch,sl-checkbox')||(e.id&&document.querySelector('label[for="'+e.id+'"]')))return;e.setAttribute('aria-label',e.placeholder||e.title||e.name||'Поле')});
$$('.FIE_crop-tool[aria-selected]',function(e){e.removeAttribute('aria-selected')});
$$('[aria-selected]:not([role]),.FIE_tab[aria-selected],.FIE_crop-tool[aria-selected]',function(e){var r=e.getAttribute('role');if(r==='tab'||r==='option'||r==='treeitem')return;var v=e.getAttribute('aria-selected');e.removeAttribute('aria-selected');if(!e.hasAttribute('role'))e.setAttribute('role','button');e.setAttribute('aria-pressed',v)});
$$('button:not([aria-label])',function(e){if(e.textContent.trim()||e.getAttribute('aria-labelledby')||e.querySelector('img[alt]'))return;e.setAttribute('aria-label',e.title||e.getAttribute('data-tooltip')||'Кнопка')});
$$('.fc-icon[role=img]',function(e){e.removeAttribute('role');e.setAttribute('aria-hidden','true')});
$$('.fc-scroller:not([tabindex])',function(e){var o=getComputedStyle(e);if(/(auto|scroll)/.test(o.overflowX+o.overflowY)&&(e.scrollWidth>e.clientWidth||e.scrollHeight>e.clientHeight)){e.setAttribute('tabindex','0');if(!e.getAttribute('role')){e.setAttribute('role','region');e.setAttribute('aria-label','Прокручиваемая область календаря')}}});
$$('.fc-view-harness div:not([tabindex])',function(e){var o=getComputedStyle(e);if(/(auto|scroll)/.test(o.overflowX+o.overflowY)&&(e.scrollWidth>e.clientWidth+1||e.scrollHeight>e.clientHeight+1)){e.setAttribute('tabindex','0')}});
if(!document.querySelector('h2,h3'))$$('h4',function(e){if(!e.hasAttribute('aria-level'))e.setAttribute('aria-level','2')});
$$('body[data-page=tv] #chat:not([role])',function(e){e.setAttribute('role','region');e.setAttribute('aria-label','Экран NOX')});
$$('a[aria-label]',function(e){var t=(e.textContent||'').trim(),l=e.getAttribute('aria-label')||'';if(t&&l.toLowerCase().indexOf(t.toLowerCase())<0&&!e.dataset.nxl){e.dataset.nxl=1;e.setAttribute('aria-label',t+': '+l)}});
$$('img:not([alt])',function(e){var n=(e.getAttribute('src')||'').split('?')[0].split('/').pop().replace(/\.[a-z0-9]+$/i,'').replace(/[_-]+/g,' ');e.setAttribute('alt',n||'Изображение')});
$$('#feed:not([tabindex])',function(e){e.setAttribute('tabindex','0')});
if(!document.querySelector('h2'))$$('h3',function(e){if(!e.hasAttribute('aria-level')&&!e.getAttribute('role'))e.setAttribute('aria-level','2')});
$$('h3[role],h4[role]',function(e){e.removeAttribute('aria-level')});
if(!document.querySelector('main,[role=main]')){var mm=document.querySelector('.page,#app,.grid');if(mm)mm.setAttribute('role','main')}
if(!document.querySelector('.u-cta,sl-button[variant=primary],button.pri,.k4-btn.pri')){var cc=document.querySelector('main button:not(.tb-i):not([disabled]), main .btn, .page button:not([disabled]), .page sl-button');if(cc){if(cc.tagName==='SL-BUTTON')cc.setAttribute('variant','primary');else cc.classList.add('pri')}}
$$('#k4-nl > h3',function(e){e.setAttribute('aria-level','2')});
}
var t=0;function sch(){clearTimeout(t);t=setTimeout(fix,250)}
fix();new MutationObserver(sch).observe(document.documentElement,{childList:true,subtree:true});setTimeout(fix,2500);setTimeout(fix,6000)})();
