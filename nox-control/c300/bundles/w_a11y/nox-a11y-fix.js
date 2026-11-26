/* NOX a11y-fix (WEB): точечные aria-правки общих скриптов и готовых компонентов. Откат: ?a11y=0 */
(function(){if(/[?&]a11y=0/.test(location.search))return;
var st=document.createElement('style');st.textContent='.nx-sr{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}sl-input.nx-hl::part(form-control-label),sl-textarea.nx-hl::part(form-control-label){position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}';document.head.appendChild(st);
function $$(s,f){document.querySelectorAll(s).forEach(f)}
function fix(){
$$('#nxdock[role=region]',function(e){e.removeAttribute('role')});
$$('#nxpult:not([role]),#nxnavx:not([role])',function(e){e.setAttribute('role','region')});
$$('[role=tablist]',function(e){if(!e.querySelector('[role=tab]')||e.classList.contains('nxm-side')){e.removeAttribute('role');e.querySelectorAll('[role=tab]').forEach(function(t){t.removeAttribute('role');if(t.hasAttribute('aria-selected')){t.setAttribute('aria-current',t.getAttribute('aria-selected')==='true'?'true':'false');t.removeAttribute('aria-selected')}})}});
$$('sl-input:not([label]),sl-textarea:not([label]),sl-select:not([label]),sl-range:not([label])',function(e){var t=e.getAttribute('aria-label')||e.title||e.getAttribute('placeholder')||e.getAttribute('name')||e.id||'Поле';e.setAttribute('label',t);e.classList.add('nx-hl')});
$$('sl-switch,sl-checkbox,sl-radio',function(e){if(!e.textContent.trim()){var s=document.createElement('span');s.className='nx-sr';s.textContent=e.getAttribute('aria-label')||e.title||e.getAttribute('name')||e.id||'Переключатель';e.appendChild(s)}});
$$('textarea:not([aria-label]):not([aria-labelledby])',function(e){if(e.closest('label')||(e.id&&document.querySelector('label[for="'+e.id+'"]')))return;e.setAttribute('aria-label',e.placeholder||e.title||'Редактор')});
$$('input:not([aria-label]):not([aria-labelledby]):not([type=hidden])',function(e){if(e.closest('label')||e.closest('sl-input,sl-switch,sl-checkbox')||(e.id&&document.querySelector('label[for="'+e.id+'"]')))return;e.setAttribute('aria-label',e.placeholder||e.title||e.name||'Поле')});
$$('.FIE_crop-tool[aria-selected]',function(e){e.removeAttribute('aria-selected')});
$$('[aria-selected]:not([role]),.FIE_tab[aria-selected],.FIE_crop-tool[aria-selected]',function(e){var r=e.getAttribute('role');if(r==='tab'||r==='option'||r==='treeitem')return;var v=e.getAttribute('aria-selected');e.removeAttribute('aria-selected');if(!e.hasAttribute('role'))e.setAttribute('role','button');e.setAttribute('aria-pressed',v)});
$$('button:not([aria-label])',function(e){if(e.textContent.trim()||e.getAttribute('aria-labelledby')||e.querySelector('img[alt]'))return;e.setAttribute('aria-label',e.title||e.getAttribute('data-tooltip')||'Кнопка')});
$$('.fc-scrollgrid, .fc-scrollgrid table, .fc-scrollgrid [role=rowgroup], .fc-scrollgrid [role=row], .fc-scrollgrid [role=columnheader], .fc-scrollgrid [role=gridcell]',function(e){if(e.getAttribute('role')!=='presentation')e.setAttribute('role','presentation')});
$$('.fc-icon[role=img]',function(e){e.removeAttribute('role');e.setAttribute('aria-hidden','true')});
$$('.fc-scroller:not([tabindex]),.fc-view:not([tabindex]),.fc-scroller-harness:not([tabindex])',function(e){e.setAttribute('tabindex','0')});
$$('#k4-nl > h3',function(e){e.setAttribute('aria-level','2')});
}
var t=0;function sch(){clearTimeout(t);t=setTimeout(fix,250)}
fix();new MutationObserver(sch).observe(document.documentElement,{childList:true,subtree:true});setTimeout(fix,2500);setTimeout(fix,6000)})();
