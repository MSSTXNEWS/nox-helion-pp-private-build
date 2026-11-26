/* NOX Writer Pro (WEB): «Книга» слева от полотна: главы, персонажи, сюжетные линии, память роли. Готовое: Shoelace (tab-group, card, input, textarea, button), SortableJS, CodeMirror/студия ролей. Данные только в браузере (localStorage nox.wr.v1) + экспорт. Откат: ?wr=0 */
(function(){
if(/[?&]wr=0/.test(location.search))return;
var KEY='nox.wr.v1',root=null,S,API,cm;
function uid(){return Math.random().toString(36).slice(2,9)}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function load(){try{S=JSON.parse(localStorage.getItem(KEY)||'null')}catch(e){S=null}if(!S||!S.chapters)S={title:'Моя книга',cur:null,chapters:[],chars:[],plots:[],mem:[]};}
function save(){try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}sys()}
function chap(id){return S.chapters.filter(function(c){return c.id===id})[0]}
function sys(){if(!API||!API.role)return;if(!API.role._base)API.role._base=API.role.system||'';var t=API.role._base+'\n\nКонтекст книги «'+S.title+'» (учитывай, не пересказывай):';
 if(S.chars.length)t+='\nПерсонажи: '+S.chars.map(function(c){return c.name+(c.desc?' — '+c.desc.slice(0,200):'')}).join('; ');
 if(S.plots.length)t+='\nСюжетные линии: '+S.plots.map(function(p){return p.title+(p.beats.length?' ['+p.beats.join(' > ').slice(0,200)+']':'')}).join('; ');
 if(S.mem.length)t+='\nПамять роли: '+S.mem.map(function(m){return m.text.slice(0,200)}).join(' | ');
 API.role.system=t.slice(0,3500)}
function flush(){if(S.cur&&cm){var c=chap(S.cur);if(c){c.text=cm.getValue();c.upd=Date.now()}}}
function open(id){flush();S.cur=id;var c=chap(id);if(c&&cm)cm.setValue(c.text||'');save();render()}
function addChapter(){var c={id:uid(),title:'Глава '+(S.chapters.length+1),text:''};S.chapters.push(c);open(c.id)}
function wc(t){return(String(t||'').trim().match(/\S+/g)||[]).length}
var css='#rsRoot.wr{grid-template-columns:300px minmax(0,1fr) 340px}#rsRoot.wr #wr-book{grid-column:1;grid-row:1/3}#rsRoot.wr #rs-cv,#rsRoot.wr #rs-tools{grid-column:2}#rsRoot.wr #rs-chat{grid-column:3}#wr-book{display:flex;flex-direction:column;min-height:0;overflow:hidden}#wr-book sl-tab-group{flex:1;min-height:0;--indicator-color:var(--gx-acc,#c8b6a2)}#wr-book sl-tab-group::part(base){height:100%}#wr-book sl-tab-group::part(body){overflow:auto}#wr-book sl-tab::part(base){padding:10px 10px;font-size:13px;min-height:44px}.wr-p{padding:12px;display:flex;flex-direction:column;gap:10px}.wr-i{display:flex;align-items:center;gap:8px;min-height:44px;padding:8px 12px;border-radius:12px;border:1px solid var(--gx-5,#2a2c30);background:var(--gx-3,#18191b);color:var(--gx-12,#edeef0);cursor:pointer;font:inherit;font-size:14px;text-align:left;width:100%}.wr-i[aria-pressed=true]{border-color:var(--gx-acc,#c8b6a2);background:color-mix(in srgb,var(--gx-acc,#c8b6a2) 14%,var(--gx-3,#18191b))}.wr-i span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.wr-i small{color:var(--gx-11,#b0b4ba);font-size:12px}.wr-h{color:var(--gx-11,#b0b4ba);font-size:13px;line-height:1.5;margin:0}.wr-r{display:flex;gap:8px;flex-wrap:wrap}.wr-bt{margin:0;padding:8px 10px;border-left:2px solid var(--gx-acc,#c8b6a2);font-size:14px;display:flex;gap:8px;align-items:center;background:var(--gx-2,#111113);border-radius:0 8px 8px 0;list-style:none}.wr-bt span{flex:1}.wr-t{font-weight:600;font-size:15px}@media(max-width:1100px){#rsRoot.wr{grid-template-columns:1fr}#rsRoot.wr #wr-book,#rsRoot.wr #rs-cv,#rsRoot.wr #rs-tools,#rsRoot.wr #rs-chat{grid-column:1;grid-row:auto}#wr-book{max-height:560px;order:9}}';
function btn(label,fn,v,icon){var b=document.createElement('sl-button');b.setAttribute('size','medium');if(v)b.setAttribute('variant',v);b.textContent=label;b.addEventListener('click',fn);return b}
function field(tag,label,val,ph){var f=document.createElement(tag);f.setAttribute('label',label);f.value=val||'';if(ph)f.setAttribute('placeholder',ph);if(tag==='sl-textarea')f.setAttribute('rows','3');return f}
function panelChapters(p){
 var tot=S.chapters.reduce(function(a,c){return a+wc(c.id===S.cur&&cm?cm.getValue():c.text)},0);
 p.appendChild(Object.assign(document.createElement('p'),{className:'wr-h',textContent:'Глав: '+S.chapters.length+' · слов: '+tot}));
 var list=document.createElement('div');list.className='wr-p';list.style.padding='0';list.id='wr-ch';
 S.chapters.forEach(function(c){var b=document.createElement('button');b.type='button';b.className='wr-i';b.dataset.id=c.id;b.setAttribute('aria-pressed',c.id===S.cur?'true':'false');b.innerHTML='<span>'+esc(c.title)+'</span><small>'+wc(c.id===S.cur&&cm?cm.getValue():c.text)+' сл.</small>';b.addEventListener('click',function(){open(c.id)});list.appendChild(b)});
 p.appendChild(list);
 if(window.Sortable&&S.chapters.length>1)window.Sortable.create(list,{animation:150,onEnd:function(){var ids=[].map.call(list.children,function(x){return x.dataset.id});S.chapters.sort(function(a,b){return ids.indexOf(a.id)-ids.indexOf(b.id)});save()}});
 var r=document.createElement('div');r.className='wr-r';r.appendChild(btn('Новая глава',addChapter,'primary'));
 if(S.cur){r.appendChild(btn('Переименовать',function(){var c=chap(S.cur),n=prompt('Название главы',c.title);if(n){c.title=n.slice(0,80);save();render()}}));
  r.appendChild(btn('Удалить',function(){if(S.chapters.length<2||!confirm('Удалить главу «'+chap(S.cur).title+'»?'))return;S.chapters=S.chapters.filter(function(c){return c.id!==S.cur});S.cur=null;open(S.chapters[0].id)}));
  r.appendChild(btn('Сжать главу в синопсис',function(){var c=chap(S.cur);flush();if(!(c.text||'').trim())return;API.ask('Сделай синопсис этой главы в 3-4 предложениях, назови ключевые события и кто участвует.\n\n'+c.text.slice(0,6000),'Синопсис',false)}))}
 p.appendChild(r);
 var e=document.createElement('div');e.className='wr-r';e.appendChild(btn('Экспорт книги .md',function(){flush();var t='# '+S.title+'\n\n'+S.chapters.map(function(c){return '## '+c.title+'\n\n'+(c.text||'')}).join('\n\n');dl(S.title+'.md',t,'text/markdown')}));e.appendChild(btn('Резерв .json',function(){flush();dl('nox-writer.json',JSON.stringify(S,null,1),'application/json')}));p.appendChild(e)}
function dl(n,t,m){var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([t],{type:m}));a.download=n;a.click();setTimeout(function(){URL.revokeObjectURL(a.href)},2000)}
function panelChars(p){
 p.appendChild(Object.assign(document.createElement('p'),{className:'wr-h',textContent:'Библия персонажей. NOX учитывает её во всех запросах из этой студии.'}));
 S.chars.forEach(function(c){var d=document.createElement('sl-card');d.innerHTML='<div class="wr-t">'+esc(c.name)+'</div><div class="wr-h">'+esc(c.desc)+'</div>';var r=document.createElement('div');r.className='wr-r';r.style.marginTop='8px';
  r.appendChild(btn('Править',function(){var n=prompt('Имя',c.name);if(n==null)return;var t=prompt('Описание: внешность, цель, страх, манера речи',c.desc);c.name=n.slice(0,60);if(t!=null)c.desc=t.slice(0,800);save();render('chars')}));
  r.appendChild(btn('Дополнить через NOX',function(){API.ask('Дополни профиль персонажа: цель, страх, тайна, манера речи, арка. Коротко, списком.\nИмя: '+c.name+'\nСейчас: '+c.desc,'Профиль: '+c.name,false)}));
  r.appendChild(btn('Удалить',function(){S.chars=S.chars.filter(function(x){return x!==c});save();render('chars')}));d.appendChild(r);p.appendChild(d)});
 var n=field('sl-input','Имя',''),t=field('sl-textarea','Описание','','Внешность, цель, страх, манера речи');p.appendChild(n);p.appendChild(t);
 p.appendChild(btn('Добавить персонажа',function(){if(!n.value.trim())return;S.chars.push({id:uid(),name:n.value.trim().slice(0,60),desc:(t.value||'').slice(0,800)});save();render('chars')},'primary'))}
function panelPlots(p){
 p.appendChild(Object.assign(document.createElement('p'),{className:'wr-h',textContent:'Сюжетные линии и их ключевые события. Порядок событий меняется перетаскиванием.'}));
 S.plots.forEach(function(pl){var d=document.createElement('sl-card');d.innerHTML='<div class="wr-t">'+esc(pl.title)+'</div>';var ul=document.createElement('ul');ul.style.cssText='margin:8px 0;padding:0;display:flex;flex-direction:column;gap:6px';
  pl.beats.forEach(function(b,i){var li=document.createElement('li');li.className='wr-bt';li.innerHTML='<span>'+esc(b)+'</span>';var x=document.createElement('sl-icon-button');x.setAttribute('name','x');x.setAttribute('library','tabler');x.setAttribute('label','Убрать событие');x.addEventListener('click',function(){pl.beats.splice(i,1);save();render('plots')});li.appendChild(x);ul.appendChild(li)});d.appendChild(ul);
  if(window.Sortable&&pl.beats.length>1)window.Sortable.create(ul,{animation:150,onEnd:function(){var o=[].map.call(ul.children,function(l){return l.firstChild.textContent});pl.beats=o;save()}});
  var bi=field('sl-input','Новое событие','');d.appendChild(bi);var r=document.createElement('div');r.className='wr-r';r.style.marginTop='8px';
  r.appendChild(btn('Добавить событие',function(){if(!bi.value.trim())return;pl.beats.push(bi.value.trim().slice(0,160));save();render('plots')},'primary'));
  r.appendChild(btn('Предложить развитие',function(){API.ask('Предложи 3 варианта развития сюжетной линии и риски для каждой.\nЛиния: '+pl.title+'\nСобытия: '+pl.beats.join(' > '),'Линия: '+pl.title,false)}));
  r.appendChild(btn('Удалить линию',function(){S.plots=S.plots.filter(function(x){return x!==pl});save();render('plots')}));d.appendChild(r);p.appendChild(d)});
 var n=field('sl-input','Название линии','');p.appendChild(n);p.appendChild(btn('Добавить линию',function(){if(!n.value.trim())return;S.plots.push({id:uid(),title:n.value.trim().slice(0,80),beats:[]});save();render('plots')},'primary'))}
function panelMem(p){
 p.appendChild(Object.assign(document.createElement('p'),{className:'wr-h',textContent:'Память роли: факты мира, стиль, запреты. Подмешивается в каждый запрос к NOX из студии.'}));
 S.mem.forEach(function(m){var d=document.createElement('div');d.className='wr-bt';d.innerHTML='<span>'+esc(m.text)+'</span>';var x=document.createElement('sl-icon-button');x.setAttribute('name','x');x.setAttribute('library','tabler');x.setAttribute('label','Забыть');x.addEventListener('click',function(){S.mem=S.mem.filter(function(y){return y!==m});save();render('mem')});d.appendChild(x);p.appendChild(d)});
 var t=field('sl-textarea','Новый факт или правило','','Например: действие в 1923 году, без магии');p.appendChild(t);var r=document.createElement('div');r.className='wr-r';
 r.appendChild(btn('Запомнить',function(){if(!t.value.trim())return;S.mem.push({id:uid(),text:t.value.trim().slice(0,300)});save();render('mem')},'primary'));
 r.appendChild(btn('Из выделенного',function(){var s=cm&&cm.getSelection();if(!s||!s.trim())return;S.mem.push({id:uid(),text:s.trim().slice(0,300)});save();render('mem')}));p.appendChild(r)}
var curTab='ch';
function render(tab){if(tab)curTab={chars:'ch2',plots:'pl',mem:'mm'}[tab]||tab;var box=root.querySelector('#wr-body');if(!box)return;box.innerHTML='';
 var g=document.createElement('sl-tab-group');
 [['ch','Главы',panelChapters],['ch2','Персонажи',panelChars],['pl','Линии',panelPlots],['mm','Память',panelMem]].forEach(function(x){var t=document.createElement('sl-tab');t.slot='nav';t.panel=x[0];t.textContent=x[1];if(x[0]===curTab)t.setAttribute('active','');g.appendChild(t);var pn=document.createElement('sl-tab-panel');pn.name=x[0];if(x[0]===curTab)pn.setAttribute('active','');var inner=document.createElement('div');inner.className='wr-p';x[2](inner);pn.appendChild(inner);g.appendChild(pn)});
 g.addEventListener('sl-tab-show',function(e){curTab=e.detail.name});box.appendChild(g)}
function init(){
 API=window.NOXroleStudio;var r=document.getElementById('rsRoot');if(!API||!API.cm||!r||r.classList.contains('wr'))return false;
 if(new URLSearchParams(location.search).get('role')&&new URLSearchParams(location.search).get('role')!=='writer')return true;
 cm=API.cm;root=r;load();
 var st=document.createElement('style');st.textContent=css+'#rs-ch-h>*:not(sl-icon):not(b){display:none!important}';document.head.appendChild(st);
 var a=document.createElement('aside');a.id='wr-book';a.className='rs-card';a.setAttribute('aria-label','Книга');a.innerHTML='<div id="rs-ch-h"><sl-icon library="tabler" name="books" aria-hidden="true"></sl-icon><b>Книга</b><span class="wr-h" style="margin-left:auto">хранится в браузере</span></div><div id="wr-body" style="flex:1;min-height:0;display:flex;flex-direction:column"></div>';
 r.insertBefore(a,r.firstChild);r.classList.add('wr');
 if(!S.chapters.length){S.chapters.push({id:uid(),title:'Глава 1',text:cm.getValue()||''});S.cur=S.chapters[0].id}
 else if(!chap(S.cur))S.cur=S.chapters[0].id;
 cm.setValue(chap(S.cur).text||'');
 var t=0;cm.on('change',function(){clearTimeout(t);t=setTimeout(function(){flush();try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}},700)});
 function go(){render();sys()}
 if(window.Sortable)go();else{var s=document.createElement('script');s.src='./vendor/sortablejs/Sortable.min.js';s.onload=go;s.onerror=go;document.head.appendChild(s)}
 var bs=document.createElement('script');bs.type='module';var b=new URL('./vendor/shoelace/cdn/',location.href).href;
 return true}
var n=0,iv=setInterval(function(){if(init()||++n>60)clearInterval(iv)},300);
})();
