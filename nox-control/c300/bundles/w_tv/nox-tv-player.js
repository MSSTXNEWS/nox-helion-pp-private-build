/* NOX tv-player (WEB): готовый vidstack + hls.js для экрана ТВ. Принимает те же сообщения 'video' (BroadcastChannel nox-tv / storage) и ручной ввод адреса. Нет адреса: HOLD. Откат: ?tvp=0 */
(function(){
if(/[?&]tvp=0/.test(location.search))return;
function css(h){var l=document.createElement('link');l.rel='stylesheet';l.href=h;document.head.appendChild(l)}
['base.css','default/theme.css','default/layouts/video.css'].forEach(function(f){css('./vendor/vidstack/player/styles/'+f)});
var st=document.createElement('style');st.textContent='#nxtv{position:fixed;inset:0;z-index:80;display:none;background:#000;flex-direction:column}#nxtv.on{display:flex}#nxtv media-player{flex:1;min-height:0;width:100%}#nxtv-bar{display:flex;gap:8px;padding:10px;background:#0b0c0e;align-items:center}#nxtv-bar input{flex:1;min-height:44px;border-radius:12px;border:1px solid #2a2c30;background:#111214;color:#edeef0;padding:0 12px;font:16px system-ui}#nxtv-bar button,#nxtv-open{min-height:44px;padding:0 16px;border-radius:12px;border:1px solid #43484e;background:#18191b;color:#edeef0;font:600 14px system-ui;cursor:pointer}#nxtv-hold{color:#b0b4ba;font:14px system-ui;padding:0 12px}';document.head.appendChild(st);
var box=document.createElement('div');box.id='nxtv';box.setAttribute('role','dialog');box.setAttribute('aria-label','Плеер эфира');
box.innerHTML='<div id="nxtv-bar"><input id="nxtv-url" placeholder="Адрес потока .m3u8, .mp4 или .mpd" aria-label="Адрес потока"><button id="nxtv-go" type="button">Смотреть</button><button id="nxtv-x" type="button">Закрыть</button></div><div id="nxtv-hold">Эфир: HOLD, источник не задан. Вставьте адрес потока или отправьте видео с телефона.</div>';
document.body.appendChild(box);
var op=document.createElement('button');op.id='nxtv-open';op.type='button';op.className='b';op.textContent='Эфир';var tries=0,iv=setInterval(function(){var p=document.querySelector('#s2tv .top #s2p');if(p){p.insertAdjacentElement('afterend',op);clearInterval(iv)}else if(++tries>40){document.body.appendChild(op);op.style.cssText='position:fixed;right:16px;top:16px;z-index:70';clearInterval(iv)}},250);
var pl=null;
function play(u){if(!u)return;if(!window.__nxHls&&/\.m3u8/i.test(u)){import('./vendor/hls.js/hls.js.esm.js').then(function(m){window.__nxHls=m.default;play(u)}).catch(function(){window.__nxHls=null;play2(u)});return}play2(u)}
function play2(u){box.classList.add('on');document.getElementById('nxtv-hold').style.display='none';var old=document.getElementById('vid');if(old){try{old.pause()}catch(e){}old.style.display='none'}
 if(!pl){customElements.whenDefined('media-player').then(function(){})}
 if(pl)pl.remove();pl=document.createElement('media-player');pl.setAttribute('playsinline','');pl.setAttribute('autoplay','');pl.setAttribute('title','Эфир NOX');pl.innerHTML='<media-provider></media-provider><media-video-layout></media-video-layout>';box.insertBefore(pl,box.firstChild.nextSibling);
 pl.addEventListener('provider-change',function(e){var p=e.detail;if(p&&p.type==='hls')if(window.__nxHls)p.library=window.__nxHls});
 pl.src=/\.m3u8(\?|$)/i.test(u)?{src:u,type:'application/x-mpegurl'}:u}
function load(){if(window.customElements&&customElements.get('media-player'))return Promise.resolve();return new Promise(function(ok){var s=document.createElement('script');s.src='./vendor/vidstack/vidstack.iife.js';s.onload=function(){var V=window.NOX_vidstack;try{if(V&&V.defineCustomElement&&!customElements.get('media-player')){['MediaPlayerElement','MediaProviderElement','MediaVideoLayoutElement'].forEach(function(k){if(V[k]&&!customElements.get(V[k].tagName||'x'))V.defineCustomElement(V[k])})}}catch(e){}ok()};s.onerror=ok;document.head.appendChild(s)})}
op.onclick=function(){box.classList.add('on')};document.getElementById('nxtv-x').onclick=function(){box.classList.remove('on');if(pl){try{pl.pause()}catch(e){}}};
document.getElementById('nxtv-go').onclick=function(){var u=document.getElementById('nxtv-url').value.trim();if(u)load().then(function(){play(u)})};
document.getElementById('nxtv-url').addEventListener('keydown',function(e){if(e.key==='Enter')document.getElementById('nxtv-go').click()});
function msg(m){if(m&&m.type==='video'&&m.url)load().then(function(){play(m.url)})}
if('BroadcastChannel' in window)new BroadcastChannel('nox-tv').addEventListener('message',function(e){msg(e.data)});
addEventListener('storage',function(e){if(e.key==='nox-tv:last')try{msg(JSON.parse(e.newValue))}catch(x){}});
addEventListener('keydown',function(e){if(e.key==='Escape')box.classList.remove('on')});
window.NOXtvPlayer={play:function(u){load().then(function(){play(u)})}};
})();
