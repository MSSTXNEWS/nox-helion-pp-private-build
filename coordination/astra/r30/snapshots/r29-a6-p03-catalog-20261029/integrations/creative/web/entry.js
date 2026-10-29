// NOX HELION R13 · additive creative launcher in existing routes. Never replaces D02 HOME.
(()=>{'use strict';
 const main=document.querySelector('#main-content');if(!main)return;
 const screen=document.createElement('section');screen.id='creative';screen.className='screen';screen.setAttribute('aria-label','NOX HELION · Творческая студия');
 const frame=document.createElement('iframe');frame.id='nox-creative-frame';frame.title='NOX HELION Creative Studio';frame.src='creative/studio.html';frame.allow='fullscreen';
 frame.style.cssText='border:0;width:100%;min-height:75vh;height:calc(100vh - 110px);display:block;background:#040608';
 screen.append(frame);main.append(screen);
 const button=(label,where)=>{const b=document.createElement('button');b.type='button';b.className='cta nox-creative-launch';b.textContent=label;b.addEventListener('click',()=>launch());where?.append(b);return b;};
 button('🎬 NOX AI STUDIO · Фильмы / Аниме / 3D',document.querySelector('#menu-detail'));
 button('🎬 СОЗДАТЬ ФИЛЬМ / ВИДЕО',document.querySelector('#chat .chat-actions'));
 button('🎬 ТВОРЧЕСКАЯ СТУДИЯ',document.querySelector('#functions .nox-pack-head'));
 function launch(text='',execute=false){
   if(typeof showScreen==='function')showScreen('creative');else screen.classList.add('active');
   if(text){window.__noxCreativePrefill={text,execute};if(frame.dataset.loaded==='yes'){frame.contentWindow.postMessage({type:'nox.creative.prefill.v1',text,execute},location.origin);window.__noxCreativePrefill=null}}
 }
 frame.addEventListener('load',()=>{frame.dataset.loaded='yes';const t=window.__noxCreativePrefill;if(t){frame.contentWindow?.postMessage({type:'nox.creative.prefill.v1',...t},location.origin);window.__noxCreativePrefill=null}});
 window.addEventListener('message',event=>{
   if(event.origin!==location.origin || event.source!==frame.contentWindow || !event.data)return;
   // The first 50 WOW route cards must lead to the REAL approved P01 route,
   // not only show a decorative preview. Native owner still enforces permission.
   if(event.data.type==='nox.creative.navigate.v1'){
     const route=event.data.routeId;
     if(typeof route!=='string'||!/^[-a-z0-9_.]{2,80}$/i.test(route))return;
     if(typeof showScreen==='function')showScreen('functions');
     const search=document.getElementById('nox-pack-search');
     if(search){search.value=route;search.dispatchEvent(new Event('input',{bubbles:true}));search.focus();}
     return;
   }
   if(event.data.type==='nox.creative.projector.v1'){
     const project=event.data.project_id;
     if(typeof project!=='string'||(project!==''&&!/^[a-z0-9_-]{1,48}$/i.test(project)))return;
     window.chrome?.webview?.postMessage?.({action:'creativeProjector',projectId:project});return;
   }
   if(event.data.type==='nox.creative.request.v1'){
     if(!/^[0-9a-f-]{36}$/i.test(event.data.request_id||''))return;
     window.chrome?.webview?.postMessage?.({action:'creativeInvoke',requestId:event.data.request_id,payload:event.data.payload});
   }
 });
 window.chrome?.webview?.addEventListener?.('message',event=>{
   if(event.data?.kind==='creativeResult')frame.contentWindow?.postMessage(event.data,location.origin);
 });
 // Native chat commands continue to regular chat for other messages.
 const chatInput=document.querySelector('#chat-input'),send=document.querySelector('#chat-send');
 function studioIntent(raw){
   const t=(raw||'').toLocaleLowerCase('ru').trim();
   if(!/^(создай|сделай|сгенерируй|нарисуй|сними|смонтируй|подготовь|create|generate|make)\b|^(создай|сделай|сгенерируй|нарисуй|сними|смонтируй|подготовь)/i.test(t))return false;
   return /(фильм|кино|сериал|видео|мульт|аниме|хентай|3d|3д|фото|картин|изображен|озвуч|музык|сайт|презентац|код|анимац|movie|anime|video|image)/i.test(t);
 }
 function sendToStudio(event){
   const value=chatInput?.value||'';if(!studioIntent(value))return;
   event.preventDefault();event.stopImmediatePropagation();
   chatInput.value='';window.__noxCreativePrefill={text:value,execute:true};launch(value,true);
 }
 send?.addEventListener('click',sendToStudio,true);
 chatInput?.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&!event.repeat&&studioIntent(chatInput.value))sendToStudio(event)},true);
})();
