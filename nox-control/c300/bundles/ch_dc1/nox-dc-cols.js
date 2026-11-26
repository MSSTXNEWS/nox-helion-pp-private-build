/* NOX · боковые колонки на Shoelace (sl-card, sl-tree, sl-badge): диалоги | быстрые команды | заготовки | система. Только >=1440. */
(function(){
'use strict';
if(/[?&]mini=1/.test(location.search))return;
var D=function(){return window.NOXdc},$=function(s){return document.querySelector(s)};
var LS={g:function(k,d){try{var v=localStorage.getItem(k);return v==null?d:v}catch(e){return d}},s:function(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function card(h,gl){var c=document.createElement('sl-card');c.appendChild(el('h2','',h));if(gl){var w=el('div','dc-gl');w.appendChild(c);c.__w=w;setTimeout(function(){window.NOXdcGlass&&NOXdcGlass(w,{radius:12})},0)}return c}
function put(box,c){box.appendChild(c.__w||c)}
function proj(t){return t.project||'Общие'}
/* 1 диалоги: sl-tree по проектам */
function left(){var box=$('#dcL');if(!box||!D())return;box.textContent='';var c=card('Диалоги',1);var tr=document.createElement('sl-tree');tr.selection='leaf';
 var g={};D().threads().forEach(function(t){if(!t.msgs.length&&t!==D().cur())return;(g[proj(t)]=g[proj(t)]||[]).push(t)});
 Object.keys(g).forEach(function(p){var n=document.createElement('sl-tree-item');n.textContent=p;n.expanded=true;g[p].forEach(function(t){var i=document.createElement('sl-tree-item');i.textContent=(t.title||'Диалог').slice(0,40);i.dataset.id=t.id;if(t===D().cur())i.selected=true;n.appendChild(i)});tr.appendChild(n)});
 tr.addEventListener('sl-selection-change',function(e){var it=e.detail.selection[0];if(it&&it.dataset.id&&it.dataset.id!==D().cur().id){LS.s('nox.wow.cur',it.dataset.id);location.reload()}});
 c.appendChild(tr);put(box,c)}
/* 2 быстрые команды: выполняются сразу, в ленту не пишутся */
function quick(){var box=$('#dcQ');if(!box)return;var c=card('Быстрые команды');
 var C=[['Новый диалог',function(){$('#dcNew').click()}],['Блокнот',function(){window.NOXNote&&NOXNote.toggle()}],['Копировать ответ',function(){try{navigator.clipboard.writeText(D().lastAi());window.NOXdcToast&&NOXdcToast('Скопировано',1500)}catch(e){}}],['В блокнот',function(){var t=D().lastAi();if(t&&window.NOXNote)NOXNote.add(t)}],['Озвучить ответ',function(){try{speechSynthesis.cancel();var u=new SpeechSynthesisUtterance(D().lastAi());u.lang='ru-RU';speechSynthesis.speak(u)}catch(e){}}],['Тишина',function(){try{speechSynthesis.cancel()}catch(e){}}],['Классический чат',function(){location.search='?legacy=1'}]];
 C.forEach(function(x){var b=el('button','dc-cmd',x[0]);b.type='button';b.onclick=x[1];c.appendChild(b)});box.appendChild(c)}
/* 4 заготовки: по проекту, закрепляемые */
var PK='nox.dc.prompts';function pall(){try{return JSON.parse(LS.g(PK,'{}'))||{}}catch(e){return {}}}
function prompts(){var box=$('#dcP');if(!box||!D())return;box.textContent='';var p=proj(D().cur()),all=pall();var list=all[p]||[{t:'Кратко перескажи этот диалог'},{t:'Составь план из трёх шагов'},{t:'Найди слабые места в моём тексте'}];
 var c=card('Заготовки · '+p,1);list.sort(function(a,b){return (b.pin?1:0)-(a.pin?1:0)});
 list.forEach(function(it,i){var b=el('div','dc-pr'+(it.pin?' pin':''));b.setAttribute('role','button');b.tabIndex=0;var s=el('span','',it.t);var pin=el('i','',it.pin?'★':'☆');pin.title='Закрепить';b.appendChild(s);b.appendChild(pin);
  b.onclick=function(e){if(e.target===pin){it.pin=!it.pin;all[p]=list;LS.s(PK,JSON.stringify(all));prompts();return}D().setInput(it.t)};b.onkeydown=function(e){if(e.key==='Enter')b.click()};c.appendChild(b)});
 var add=el('button','dc-cmd','+ Заготовка');add.type='button';add.onclick=function(){var t=prompt('Текст заготовки');if(t){list.push({t:t.slice(0,300)});all[p]=list;LS.s(PK,JSON.stringify(all));prompts()}};c.appendChild(add);
 var pj=el('button','dc-cmd','Проект: '+p);pj.type='button';pj.onclick=function(){var n=prompt('Проект для этого диалога',p);if(n){D().cur().project=n.slice(0,30);D().save();left();prompts()}};c.appendChild(pj);put(box,c)}
/* 5 система: реальные числа из /api/nox-live */
function flat(o,p,out){out=out||[];Object.keys(o||{}).forEach(function(k){var v=o[k];if(typeof v==='number'&&isFinite(v))out.push([(p?p+'.':'')+k,v]);else if(v&&typeof v==='object'&&!Array.isArray(v)&&(p||'').split('.').length<3)flat(v,(p?p+'.':'')+k,out)});return out}
function widgets(){var box=$('#dcW');if(!box)return;var c=card('Система');var h=el('div','dc-w','загрузка…');c.appendChild(h);box.textContent='';box.appendChild(c);
 function upd(){fetch('/api/nox-live',{cache:'no-store'}).then(function(r){return r.json()}).then(function(j){var f=flat(j);h.parentNode&&(function(){c.querySelectorAll('.dc-w').forEach(function(x){x.remove()});if(!f.length){c.appendChild(el('div','dc-w','нет числовых данных'));return}f.slice(0,10).forEach(function(x){var r=el('div','dc-w');r.appendChild(el('span','',x[0].split('.').slice(-2).join(' ')));r.appendChild(el('b','',Math.abs(x[1])>=100?String(Math.round(x[1])):String(Math.round(x[1]*100)/100)));c.appendChild(r)})})()}).catch(function(){})}
 upd();setInterval(upd,15000)}
function build(){var g=$('#dcGrid');if(!g||g.querySelector('sl-split-panel'))return;var L=$('#dcL'),Q=$('#dcQ'),P=$('#dcP'),W=$('#dcW'),M=g.querySelector('.dc-main');
 var sa=document.createElement('sl-split-panel'),sb=document.createElement('sl-split-panel');sa.setAttribute('primary','start');sb.setAttribute('primary','end');
 var pa=+LS.g('nox.dc.spA',460),pb=+LS.g('nox.dc.spB',520);sa.positionInPixels=pa;sb.positionInPixels=pb;
 sa.addEventListener('sl-reposition',function(){LS.s('nox.dc.spA',String(Math.round(sa.positionInPixels)))});sb.addEventListener('sl-reposition',function(){LS.s('nox.dc.spB',String(Math.round(sb.positionInPixels)))});
 var l=el('div','dc-grp');l.slot='start';l.appendChild(L);l.appendChild(Q);var r=el('div','dc-grp');r.slot='end';r.appendChild(P);r.appendChild(W);
 var mid=el('div','');mid.slot='end';mid.style.cssText='height:100%;min-width:0';sb.style.setProperty('--min','400px');M.slot='start';M.style.height='100%';sb.appendChild(M);sb.appendChild(r);mid.appendChild(sb);sa.appendChild(l);sa.appendChild(mid);g.appendChild(sa)}
function init(){if(!D()){return setTimeout(init,300)}build();left();quick();prompts();widgets()}
if(matchMedia('(min-width:1440px)').matches)init();
matchMedia('(min-width:1440px)').addEventListener('change',function(e){if(e.matches)init()});
})();
