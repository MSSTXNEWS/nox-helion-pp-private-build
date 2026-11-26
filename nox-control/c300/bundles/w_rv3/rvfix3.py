import sys,os,re
S=sys.argv[1].rstrip('/')+'/'
def rd(f):
    return open(S+f).read()
def wr(f,t,bak='.bak_rv3'):
    if not os.path.exists(S+f+bak): open(S+f+bak,'w').write(rd(f))
    open(S+f,'w').write(t)
JS=r"""
/*rvfix3*/(function(){
function nm(s){return (s||'').replace(/\s+/g,' ').trim()}
var PAR={listitem:'[role=list],ul,ol,menu',option:'[role=listbox],select,datalist,[role=group]',menuitem:'[role=menu],[role=menubar],[role=group]',row:'[role=grid],[role=table],[role=treegrid],table',cell:'[role=row],tr',gridcell:'[role=row],tr',treeitem:'[role=tree],[role=group]'};
function fixBtnEl(e){var t=nm(e.textContent),l=nm(e.getAttribute('aria-label'));if(!t||!l||!/[0-9A-Za-zЀ-ӿ]/.test(t)||e.getAttribute('aria-hidden')==='true')return;if(l.toLowerCase().indexOf(t.toLowerCase())>=0)return;if(t.length<=40)e.setAttribute('aria-label',t+': '+l);else e.removeAttribute('aria-label')}
function fixIn(root){
 if(root.nodeType!==1)return;
 var L=root.matches&&root.matches('button[aria-label],[role=button][aria-label]')?[root]:[];
 if(root.querySelectorAll)L=L.concat([].slice.call(root.querySelectorAll('button[aria-label],[role=button][aria-label]')));
 L.forEach(fixBtnEl);
}
function fixAll(){
 document.querySelectorAll('button[aria-label],[role=button][aria-label]').forEach(fixBtnEl);
 document.querySelectorAll('.tabulator').forEach(function(g){g.removeAttribute('aria-owns');if(g.getAttribute('role')==='grid')g.removeAttribute('role');if(g.getAttribute('role'))return;g.removeAttribute('aria-rowcount');g.removeAttribute('aria-colcount');g.querySelectorAll('[aria-sort],[aria-rowindex],[aria-colindex],[role=rowgroup],[role=row],[role=columnheader],[role=gridcell],[role=cell]').forEach(function(x){['aria-sort','aria-rowindex','aria-colindex','role'].forEach(function(k){x.removeAttribute(k)})})});
 // grid без строк (Tabulator до загрузки данных)
 document.querySelectorAll('[role=grid],[role=table],[role=treegrid]').forEach(function(g){if(g.querySelector('[role=row],tr'))return;var o=g.getAttribute('aria-owns');if(o&&o.split(' ').some(function(id){var x=document.getElementById(id);return x&&(x.querySelector('[role=row],tr')||x.getAttribute('role')==='row')}))return;g.removeAttribute('role');g.removeAttribute('aria-owns')});
 // div/span с aria-label без роли
 document.querySelectorAll('div[aria-label]:not([role]),span[aria-label]:not([role])').forEach(function(e){if(e.getAttribute('aria-hidden')==='true')return;e.setAttribute('role','group')});
 // роль без обязательного родителя
 Object.keys(PAR).forEach(function(r){document.querySelectorAll('[role='+r+']').forEach(function(e){if(/^SL-/.test(e.tagName)||e.closest('[aria-owns]'))return;if(!e.parentElement||!e.parentElement.closest(PAR[r]))e.removeAttribute('role')})});
 // поля без имени
 document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]),select,textarea').forEach(function(e){if(e.getAttribute('aria-label')||e.getAttribute('aria-labelledby')||e.closest('label')||(e.id&&document.querySelector('label[for="'+e.id+'"]'))||e.closest('sl-input,sl-select,sl-textarea,sl-checkbox,sl-switch,sl-range'))return;e.setAttribute('aria-label',nm(e.placeholder||e.title||e.name||e.id)||'Поле')});
}
function run(){try{fixAll()}catch(x){}}
var tm=0;function sched(){clearTimeout(tm);tm=setTimeout(run,120)}
function init(){run();var n=0,iv=setInterval(function(){run();if(++n>25)clearInterval(iv)},800);
 if(window.MutationObserver&&document.body)new MutationObserver(function(ms){try{ms.forEach(function(m){m.addedNodes&&m.addedNodes.forEach(fixIn)})}catch(x){}sched()}).observe(document.body,{childList:true,subtree:true})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
"""
f='nox-a11y-fix.js'; t=rd(f)
if 'rvfix3' not in t: wr(f,t+JS); print('a11y3 ok')
# tablist -> group в копиях assistant/editor
for f in ('assistant-s1.main.html','editor-s1.main.html'):
    if os.path.exists(S+f):
        t=rd(f); old='<div class="ed-tabs" role="tablist" aria-label="Раздел">'
        if old in t: wr(f,t.replace(old,'<div class="ed-tabs" role="group" aria-label="Раздел">',1)); print(f,'tablist ok')
# *-s1.main.html: фрагменты без html/title/lang -> полноценный документ
TT={'assistant-s1.main.html':'NOX · ПОМОЩНИК (копия)','atlas-s1.main.html':'NOX · ATLAS (копия)','editor-s1.main.html':'NOX · РЕДАКТОР (копия)'}
for f,ti in TT.items():
    if not os.path.exists(S+f): continue
    t=rd(f)
    if 'rvfix3' in t or '<html' in t.lower(): continue
    t=re.sub(r'(<div id="atGlobe" class="at-view") (aria-label)',r'\1 role="group" \2',t)
    t=re.sub(r'(<div id="atMap" class="at-view"[^>]*?) (aria-label)',r'\1 role="group" \2',t)
    t=t.replace('<div class="ed-thumbs" id="pdfThumbs" aria-label','<div class="ed-thumbs" id="pdfThumbs" role="group" aria-label')
    if '<h1' not in t: t='<h1 class="nx-sr" style="position:absolute;left:-9999px">'+ti+'</h1>'+t
    wr(f,'<!DOCTYPE html><!--rvfix3--><html lang="ru"><head><meta charset="utf-8"><title>'+ti+'</title></head><body>'+t+'</body></html>'); print(f,'doc ok')
# статические role=group для известных div с aria-label
for f,pairs in (('pdf.html',[('<div class="ed-thumbs" id="pdfThumbs" aria-label','<div class="ed-thumbs" id="pdfThumbs" role="group" aria-label')]),('atlas.html',[('<div id="atGlobe" class="at-view" aria-label','<div id="atGlobe" class="at-view" role="group" aria-label')])):
    if os.path.exists(S+f):
        t=rd(f); n=t
        for a,b in pairs: n=n.replace(a,b,1)
        if n!=t: wr(f,n); print(f,'group ok')
