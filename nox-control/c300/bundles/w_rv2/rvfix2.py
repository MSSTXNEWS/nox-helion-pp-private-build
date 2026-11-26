import sys,os
S=sys.argv[1].rstrip('/')+'/'
def rd(f):
    return open(S+f).read()
def wr(f,t,bak='.bak_rv2'):
    if not os.path.exists(S+f+bak): open(S+f+bak,'w').write(rd(f))
    open(S+f,'w').write(t)
# 1. a11y-fix: label-content-name-mismatch (кнопки), label-title-only (sl-select внутри shadow)
JS=r"""
/*rvfix2*/(function(){
function nm(s){return (s||'').replace(/\s+/g,' ').trim()}
function fixBtn(){document.querySelectorAll('button[aria-label],[role=button][aria-label]').forEach(function(e){var t=nm(e.textContent),l=nm(e.getAttribute('aria-label'));if(!t||!l||!/[0-9A-Za-z\u0400-\u04FF]/.test(t)||e.getAttribute('aria-hidden')==='true')return;if(l.toLowerCase().indexOf(t.toLowerCase())>=0)return;if(t.length<=40)e.setAttribute('aria-label',t+': '+l);else e.removeAttribute('aria-label')})}
function fixSel(){document.querySelectorAll('sl-select').forEach(function(h){var r=h.shadowRoot;if(!r)return;var i=r.querySelector('input.select__display-input');if(!i||i.getAttribute('aria-label'))return;var l=nm(h.getAttribute('label')||h.getAttribute('aria-label')||h.title)||'Выбор';i.setAttribute('aria-label',l);i.removeAttribute('title')})}
function run(){try{fixBtn();fixSel()}catch(e){}}
var tm=0;function sched(){clearTimeout(tm);tm=setTimeout(run,120)}
function init(){run();var n=0,iv=setInterval(function(){run();if(++n>25)clearInterval(iv)},800);if(window.MutationObserver&&document.body)new MutationObserver(sched).observe(document.body,{childList:true,subtree:true})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
"""
f='nox-a11y-fix.js'; t=rd(f)
if 'rvfix2' not in t:
    wr(f,t+JS); print('a11y2 ok')
# 2. assistant: role=tablist на контейнере sl-tab-group (нет прямых role=tab) -> group
f='assistant.html'; t=rd(f)
old='<div class="ed-tabs" role="tablist" aria-label="Раздел">'
if old in t:
    wr(f,t.replace(old,'<div class="ed-tabs" role="group" aria-label="Раздел">',1)); print('assistant tablist ok')
