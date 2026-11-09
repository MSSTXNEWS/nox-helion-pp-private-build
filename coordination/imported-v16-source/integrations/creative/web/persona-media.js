/* NOX HELION R15 · Canonical identity-preserving secondary Persona video loops.
 * These are optical camera-motion loops over exact approved photo sources;
 * NO lip-sync, NO alleged facial micro-expression, NO simulated backend state.
 * The fifth EV source is a source candidate and deliberately remains unmounted.
 */
(() => {
 'use strict';
 const roster = Object.freeze([
  {id:'KV',status:'OWNER_APPROVED_SOURCE',title:'KV · Persona',ready:true},
  {id:'AM',status:'OWNER_APPROVED_SOURCE',title:'AM · Persona',ready:true},
  {id:'LA',status:'OWNER_FACE_REFERENCE · BODY_PENDING',title:'LA · Persona (портрет)',ready:true},
  {id:'KW',status:'OWNER_APPROVED_SOURCE',title:'KW · Persona',ready:true},
  {id:'EV',status:'IDENTITY_CONFLICT_HOLD',title:'EV · Идентичность не утверждена',ready:false}
 ]);
 const nav=document.querySelector('nav.nav'), main=document.querySelector('.layout main.content');
 if(!nav||!main||document.getElementById('screen-personas'))return;
 const button=document.createElement('button');button.type='button';button.dataset.nav='personas';
 button.textContent='◈ Persona · Видео';button.setAttribute('aria-current','false');nav.append(button);
 const section=document.createElement('section');section.id='screen-personas';section.className='screen';
 const panel=document.createElement('div');panel.className='panel';
 const heading=document.createElement('h2');heading.textContent='NOX PERSONA CINEMA · оригинальные лица';
 const expl=document.createElement('p');expl.className='muted';
 expl.textContent='Только на вторичном экране. Это реальные бесшумные MP4-кинопетли с плавным движением камеры по исходным фотографиям. Мимика и lip-sync не имитируются.';
 const grid=document.createElement('div');grid.className='nox-persona-grid';
 for(const person of roster){
  const card=document.createElement('article');card.className='nox-persona-card';card.dataset.personaId=person.id;
  const h=document.createElement('h3');h.textContent=person.title;card.append(h);
  if(person.ready){
   const video=document.createElement('video');video.className='nox-persona-loop';
   video.muted=true;video.loop=true;video.autoplay=false;video.playsInline=true;
   video.preload='metadata';video.setAttribute('aria-label',person.id+' · кинопетля без звука');
   video.poster='personas/NOX_PERSONA_'+person.id+'_POSTER.jpg';
   video.src='personas/NOX_PERSONA_'+person.id+'_CAMERA_LOOP.mp4';
   video.addEventListener('error',()=>{card.dataset.media='unavailable';state.textContent='Локальный видеоассет пока не установлен';});
   card.append(video);
   const state=document.createElement('p');state.className='nox-persona-status';state.textContent=person.status+' · камера, без lip-sync';card.append(state);
  }else{
   const held=document.createElement('p');held.className='nox-persona-identity-hold';
   held.textContent='HOLD_IDENTITY · Требуется утверждённый паспорт лица; исходник EV не показывается как готовый персонаж';card.append(held);
  }
  grid.append(card);
 }
 panel.append(heading,expl,grid);section.append(panel);main.append(section);
 const media=window.matchMedia?.('(prefers-reduced-motion: reduce)');
 function update(){
  const visible=section.classList.contains('active')&&!document.hidden;
  for(const video of section.querySelectorAll('video')){
   const canPlay=visible && !media?.matches;
   if(canPlay){const p=video.play();p?.catch?.(()=>{video.parentElement.dataset.media='blocked';});}
   else video.pause();
  }
 }
 button.addEventListener('click',()=>{
  document.querySelectorAll('.screen').forEach(el=>el.classList.toggle('active',el===section));
  document.querySelectorAll('[data-nav]').forEach(el=>el.setAttribute('aria-current',el===button?'true':'false'));
  update();
 });
 // Existing Studio nav doesn't own this late-added page: listen for other tab clicks.
 nav.addEventListener('click',e=>{if(e.target!==button){section.classList.remove('active');queueMicrotask(update)}});
 document.addEventListener('visibilitychange',update);
 media?.addEventListener?.('change',update);
 window.addEventListener('pagehide',()=>{for(const v of section.querySelectorAll('video'))v.pause();});
 window.NoxPersonaCinema=Object.freeze({sourceOnly:true,assetsOptional:true,liveSpeech:false,
  approvedPortraits:4,candidateIdentityPending:1,refresh:update});
})();