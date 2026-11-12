/* NOX HELION · Owner-approved HOME cinema scene bridge.
   Art reference: exact owner-approved Drive source (not an invented redesign).
   Retains original D02 WebGL + 14 PBR selectors, service routes, original NOX backend.
   Portraits remain owner-approved stills: no fabricated autoplay video or Persona runtime. */
(()=>{'use strict';
 if(window.NOX_OWNER_HOME_V20)return;
 function init(){
 const body=document.body,stage=document.querySelector('.helion-stage');
 if(body.dataset.page!=='index'||!stage)return;
 const read=(key,allowed,def)=>{try{let v=localStorage.getItem(key);return allowed.includes(v)?v:def}catch{return def}};
 const save=(key,val)=>{try{localStorage.setItem(key,val)}catch{}};
 const el=(tag,attrs={},children=[])=>{const node=document.createElement(tag);for(const [key,value] of Object.entries(attrs)){if(key==='class')node.className=value;else if(key==='text')node.textContent=value;else node.setAttribute(key,value)}for(const c of children)node.append(c);return node};
 body.classList.add('nox-owner-cinema');
 body.dataset.noxOwnerLayout=read('nox.home.visual.owner.v20',['CINEMA','PBR'],'CINEMA');
 body.dataset.noxOwnerHud='false';body.dataset.noxOwnerControls='false';
 for(const cls of ['nox-owner-architecture','nox-owner-floor'])stage.prepend(el('div',{class:cls,'aria-hidden':'true'}));
 const coreStill=el('div',{class:'nox-owner-core-still','aria-hidden':'true'});stage.prepend(coreStill);
 const brand=el('div',{class:'nox-owner-brand'},[el('span',{class:'nox-owner-brand-mark','aria-hidden':'true'}),el('div',{},[el('strong',{text:'NOX HELION'}),el('small',{text:'СИСТЕМА ИСКУССТВЕННОГО ИНТЕЛЛЕКТА'})])]);stage.append(brand);
 const defs=[
  ['CONSCIOUSNESS','chat.html','27%','31%','#f1ad66','#d9943e','-2.3s'],
  ['PERSONA','chat.html','37%','15%','#5cb1fc','#4d8eee','-7.1s'],
  ['ATLAS','memory.html','52%','10%','#f7ab57','#ffbd7f','-1.5s'],
  ['VOICE','settings.html','64%','18%','#bc7bfa','#9875ed','-5.4s'],
  ['REFLECTION','system.html','72%','33%','#76bff8','#7fa6c9','-3.2s'],
  ['CORE','models.html','63%','50%','#e6ab6c','#c58c4e','-8.1s'],
  ['NEXUS','projects.html','48%','53%','#4d91fd','#74bdff','-1.1s'],
  ['FORGE','training.html','32%','48%','#fd8656','#f5ac6c','-6.3s']
 ];
 const rig=el('nav',{class:'nox-owner-core-rig','aria-label':'Восемь ядер NOX'});
 for(const [name,href,x,y,glow,bright,phase] of defs){
  const a=el('a',{href,class:'nox-owner-core',title:name+' · открыть существующий раздел','aria-label':name+' · открыть существующий раздел'},[el('span',{text:name})]);
  for(const [k,v] of Object.entries({'--x':x,'--y':y,'--core-glow':glow,'--core-bright':bright,'--phase':phase}))a.style.setProperty(k,v);
  rig.append(a);
 }
 stage.append(rig);
 const names=['КАЙРЕН ВОСС','АДРИАН МЕРРОУ','ЛЕОН АРДИС','ЭЛИНА ВЕЙЛ','КАССИЕН РЕЙН'];
 const personas=el('div',{class:'nox-owner-personas','aria-label':'Пять утверждённых PersonaID'});
 const info=el('div',{class:'nox-owner-portrait-status',role:'status','aria-live':'polite',hidden:''});
 const message=el('span',{text:''}),go=el('a',{href:'chat.html',text:'ОТКРЫТЬ РЕЗОНАНС'}),dismiss=el('button',{type:'button',text:'ЗАКРЫТЬ'});
 dismiss.addEventListener('click',()=>{info.hidden=true;dismiss.blur()});
 info.append(message,' · ',go,' ',dismiss);
 const labels=['KV','AM','LA','EV','KW'];
 names.forEach((name,i)=>{
  const b=el('button',{type:'button',class:'nox-owner-persona','data-idx':String(i),'aria-label':name+' · информация и переход к Резонансу'},[el('span',{text:name})]);
  b.addEventListener('click',()=>{
   message.textContent=name+' · оригинальный утверждённый портрет '+labels[i]+'; видео Persona ещё не проверено';
   info.hidden=false;go.focus();
  });
  personas.append(b);
 });
 stage.append(personas,info);
 const actions=el('div',{class:'nox-owner-actions'});
 const menu=el('button',{type:'button',text:'✦ МЕНЮ NOX','aria-label':'Открыть сервисы NOX'});
 menu.addEventListener('click',()=>{
  if(window.NOX_UNIVERSE_V19?.open)window.NOX_UNIVERSE_V19.open();
  else{const target=stage.querySelector('.home-primary-navigation a[href="projects.html"]');if(target)target.click();else location.assign('projects.html')}
 });
 const hud=el('button',{type:'button',text:'◈ МОНИТОРИНГ','aria-expanded':'false','aria-controls':'nox-owner-hud'});
 hud.addEventListener('click',()=>{const open=body.dataset.noxOwnerHud!=='true';body.dataset.noxOwnerHud=String(open);hud.setAttribute('aria-expanded',String(open));hud.textContent=open?'✕ ЗАКРЫТЬ МОНИТОРИНГ':'◈ МОНИТОРИНГ'});
 const controls=el('button',{type:'button',text:'✧ НАСТРОЙКИ СЦЕНЫ','aria-expanded':'false'});
 controls.addEventListener('click',()=>{const open=body.dataset.noxOwnerControls!=='true';body.dataset.noxOwnerControls=String(open);controls.setAttribute('aria-expanded',String(open));controls.textContent=open?'✕ ЗАКРЫТЬ НАСТРОЙКИ':'✧ НАСТРОЙКИ СЦЕНЫ'});
 const mode=el('button',{type:'button',class:'nox-owner-mode',text:'◆ PBR','aria-label':'Переключить кинематографическую композицию и исходные PBR-планеты'});
 function updateMode(){const isPbr=body.dataset.noxOwnerLayout==='PBR';mode.textContent=isPbr?'✦ КИНОСЦЕНА':'◆ PBR';mode.dataset.state=body.dataset.noxOwnerLayout;mode.setAttribute('aria-pressed',String(isPbr))}
 mode.addEventListener('click',()=>{body.dataset.noxOwnerLayout=body.dataset.noxOwnerLayout==='PBR'?'CINEMA':'PBR';save('nox.home.visual.owner.v20',body.dataset.noxOwnerLayout);updateMode()});updateMode();
 actions.append(menu,hud,controls,mode);stage.append(actions);
 // No selector is removed: old 14 source-controls and CPU/GPU widgets can be opened by actual buttons.
 const journal=stage.querySelector('details#homeJournal');
 if(journal){journal.open=true;const summary=journal.querySelector('summary');if(summary){summary.hidden=true;summary.setAttribute('aria-hidden','true');summary.tabIndex=-1;}}
 const observer=new MutationObserver(()=>{
  const owner=stage.querySelector('#noxEclipseCanvas');if(owner&&body.dataset.noxOwnerLayout==='CINEMA')owner.style.willChange='transform';
 });
 observer.observe(stage,{childList:true,subtree:false});
 window.NOX_OWNER_HOME_V20=Object.freeze({originalArtwork:'Drive SHA256 382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a',coreLinks:defs.length,personaCards:names.length,mode:()=>body.dataset.noxOwnerLayout,pbrPreserved:true,gpuAcceptance:'NOT_TESTED',actualPersonaVideo:'HOLD'});
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
