/* NOX HELION WEB V4, extension of original routes. Additive, no duplicate backend. */
(()=>{'use strict';if(window.NOX_WEB_SHELL_V4)return;
 const D=document,H=D.documentElement,B=D.body;
 const safeKey='nox.master.v4.skin';
 const clean=x=>typeof x==='string'?x:'';
 function apply(){let data=null;try{data=JSON.parse(localStorage.getItem(safeKey)||'null')}catch{}
   if(!data||typeof data!=='object')return;
   const buttons=['metal','liquid','gear','glass','plasma','mineral'];
   const fonts=['tektur','orbitron','russo','serif','mono'];
   if(buttons.includes(data.button))H.dataset.noxUiButton=data.button;
   if(fonts.includes(data.font))H.dataset.noxUiFont=data.font;
   if(['max','balanced','eco'].includes(data.quality))H.dataset.noxDemoMode=data.quality.toUpperCase();
   if(['none','embers','lensing','steam','prism','signals'].includes(data.layer))H.dataset.noxUiLayer=data.layer;
 }
 function nav(){if(D.querySelector('link[data-nox-shared-v10]')||D.querySelector('[data-nox-master-nav="v4"]'))return;
  const here=location.pathname.toLowerCase();
  const entries=[['studio.html','✦ КОНСТРУКТОР'],['dispatcher.html','◫ ДИСПЕТЧЕР'],['downloads.html','⇣ ЗАГРУЗКИ']];
  const src=D.querySelector('nav[aria-label="Разделы NOX"]:not([hidden]),nav[aria-label="Основные разделы NOX"]:not([hidden]),nav.nav:not([hidden])');
  const nav=src||D.createElement('nav');
  if(!src){nav.className='nox-master-bar nox-master-floating-dock';nav.setAttribute('aria-label','NOX · быстрые переходы');B.appendChild(nav)}
  nav.dataset.noxMasterNav='v4';
  const up=location.pathname.includes('/pc/pages/')?'../../':'';
  const currentEntries=(src?entries:[['index.html','HOME'],...entries]).map(([href,label])=>[up+href,label]);
  for(const [href,label] of currentEntries){
    if(nav.querySelector('a[href="'+href+'"]'))continue;
    const a=D.createElement('a');a.href=href;a.textContent=label;a.classList.add('nox-master-nav-link');
    if(here.endsWith('/'+href))a.setAttribute('aria-current','page');nav.appendChild(a)
  }
 }
 function boot(){apply();nav();}
 window.addEventListener('storage',e=>{if(e.key===safeKey)apply()});
 window.NOX_WEB_SHELL_V4=Object.freeze({version:'4.0.0',dataSource:'original NOX theme localStorage',nav:true});
 if(D.readyState==='loading')D.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
