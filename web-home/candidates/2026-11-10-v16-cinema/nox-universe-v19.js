/* NOX HELION V19 — shared working media/info/browser suite; original D02 untouched.
 * Network requests are made only after a user action. No synthetic API health/status.
 * Built as a reversible overlay over the existing ten native web pages.
 */
(()=>{'use strict';
 if(window.NOX_UNIVERSE_V19)return;
 const modules=['Кинотеатр','Книги','Новости','Погода','Валюта','Браузер','Разделы'];
 const $=(tag,props={},children=[])=>{const el=document.createElement(tag);for(const [k,v] of Object.entries(props)){if(k==='class')el.className=v;else if(k==='text')el.textContent=v;else if(k==='html')el.innerHTML=v;else el.setAttribute(k,v)};for(const c of children)el.append(c);return el};
 const state={active:'Кинотеатр',book:null,video:null,catalog:null,objectUrls:[],player:null,map:null,search:''};
 const clean=()=>{if(state.map){try{state.map.remove()}catch{}state.map=null}for(const u of state.objectUrls)URL.revokeObjectURL(u);state.objectUrls=[];if(state.book?.destroy)try{state.book.destroy()}catch{}state.book=null;state.video?.pause?.();state.video=null;if(state.player?.destroy)try{state.player.destroy()}catch{}state.player=null};
 const root=$('div',{class:'nox-v19-root'}),openBtn=$('button',{type:'button',class:'nox-v19-launch',text:'✦ ВСЕЛЕННАЯ NOX','aria-label':'Открыть сервисы NOX'}),panel=$('section',{class:'nox-v19-panel',role:'dialog','aria-modal':'true','aria-label':'Сервисы NOX',hidden:''});
 const head=$('header',{class:'nox-v19-head'}),title=$('h2',{text:'NOX · МОДУЛИ'}),close=$('button',{type:'button',text:'✕ ЗАКРЫТЬ',class:'nox-v19-btn'});head.append(title,close);
 const tabs=$('nav',{class:'nox-v19-tabs','aria-label':'Модули'}),body=$('div',{class:'nox-v19-body'}),status=$('div',{class:'nox-v19-status',role:'status','aria-live':'polite'});panel.append(head,tabs,body,status);root.append(openBtn,panel);
 const live=(message,type='info')=>{status.textContent=message;status.dataset.type=type};
 function action(label,cb){const b=$('button',{type:'button',class:'nox-v19-btn',text:label});b.addEventListener('click',cb);return b}
 function field(placeholder,kind='text'){return $('input',{type:kind,placeholder,'aria-label':placeholder,class:'nox-v19-input'})}
 function row(...elements){return $('div',{class:'nox-v19-row'},elements)}
 function shell(label){const node=$('section',{class:'nox-v19-card'});node.append($('h3',{text:label}));body.append(node);return node}
 function notice(parent,text){parent.append($('p',{class:'nox-v19-note',text}))}
 function sectionButton(name){const b=action(name,()=>show(name));b.setAttribute('aria-pressed',String(name===state.active));tabs.append(b)}
 function show(name){clean();state.active=name;body.replaceChildren();tabs.replaceChildren();for(const key of modules)sectionButton(key);live('Источник данных и состояние указаны в каждом модуле. Действия подтверждаются вручную.');
 if(name==='Кинотеатр')cinema();else if(name==='Книги')books();else if(name==='Новости')news();else if(name==='Погода')weather();else if(name==='Валюта')currency();else if(name==='Браузер')browser();else sections();}
 function open(){panel.hidden=false;openBtn.hidden=true;show(state.active);close.focus()}
 function dismiss(){clean();panel.hidden=true;openBtn.hidden=false;openBtn.focus()}
 openBtn.addEventListener('click',open);close.addEventListener('click',dismiss);
 panel.addEventListener('keydown',e=>{if(e.key==='Escape')dismiss()});
 const openUrl=(url)=>{try{const u=new URL(url);if(!['https:','http:'].includes(u.protocol))throw Error('Только HTTP(S)');window.open(u.href,'_blank','noopener,noreferrer')}catch(e){live('Недопустимый адрес: '+e.message,'error')}};
 function objectURL(file){const u=URL.createObjectURL(file);state.objectUrls.push(u);return u}
 function cinema(){const c=shell('Кинотеатр · реальное воспроизведение');notice(c,'Разрешённые файлы и прямые HTTP(S) видеопотоки. DRM и закрытые сайты не обходятся. Каталог сторонних фильмов без лицензии не подставляется.');
 const url=field('URL прямого MP4/WebM/HLS или локальный файл'),local=field('Выбрать видеофайл','file');local.accept='video/*,.m3u8';
 const audio=field('Выбрать субтитры VTT','file');audio.accept='.vtt,text/vtt';
 const player=$('video',{controls:'',playsinline:'',preload:'metadata',class:'nox-v19-video'}),info=$('div',{class:'nox-v19-note'});
 const bookmark=()=>{if(!player.currentSrc)return;const key='nox-watch:'+encodeURIComponent(player.dataset.source||player.currentSrc);try{localStorage.setItem(key,JSON.stringify({seconds:player.currentTime,at:Date.now()}));live('Позиция сохранена: '+Math.round(player.currentTime)+' с','ok')}catch(e){live('Не удалось сохранить: '+e.message,'error')}};
 player.addEventListener('timeupdate',()=>{if(player.currentTime&&Math.floor(player.currentTime)%15===0)bookmarkSilently()});
 function bookmarkSilently(){try{const key='nox-watch:'+encodeURIComponent(player.dataset.source||player.currentSrc);localStorage.setItem(key,JSON.stringify({seconds:player.currentTime,at:Date.now()}))}catch{}}
 player.addEventListener('loadedmetadata',()=>{try{const key='nox-watch:'+encodeURIComponent(player.dataset.source||player.currentSrc);const s=JSON.parse(localStorage.getItem(key)||'null');if(Number.isFinite(s?.seconds)&&s.seconds<player.duration-3)player.currentTime=s.seconds}catch{}});
 const assign=async(value,source)=>{try{if(state.player?.destroy)await state.player.destroy();state.player=null;player.pause();player.removeAttribute('src');player.querySelectorAll('source,track').forEach(x=>x.remove());const u=new URL(value,location.href);if(u.protocol!=='https:'&&u.protocol!=='http:'&&u.protocol!=='blob:')throw Error('Недопустимый источник');player.dataset.source=source||value;
 if(/\.m3u8(?:$|\?)/i.test(u.pathname+u.search)&&!player.canPlayType('application/vnd.apple.mpegurl')){await loadScript('./vendor/nox-extra/shaka-player.compiled.js');if(!window.shaka?.Player?.isBrowserSupported())throw Error('HLS не поддерживается браузером');state.player=new window.shaka.Player();await state.player.attach(player);await state.player.load(value)}else player.src=value;
 info.textContent='Источник: '+(source||u.host)+' · Состояние: загружен источник, не подтверждено воспроизведение';if(!state.player)player.load();live('Источник установлен. Нажмите Play для начала просмотра.','ok');}catch(e){live('Плеер HOLD: '+e.message,'error')}};
 c.append(row(url,action('ОТКРЫТЬ URL',()=>assign(url.value.trim())),local),player,info,row(audio,action('СОХРАНИТЬ ПОЗИЦИЮ',bookmark),action('НА ВЕСЬ ЭКРАН',()=>player.requestFullscreen?.()),action('−10 С',()=>player.currentTime=Math.max(0,player.currentTime-10)),action('+10 С',()=>player.currentTime=Math.min(player.duration||Infinity,player.currentTime+10))));
 local.addEventListener('change',()=>{if(local.files?.[0])assign(objectURL(local.files[0]),local.files[0].name+':'+local.files[0].size)});
 audio.addEventListener('change',()=>{if(!audio.files?.[0])return;player.querySelectorAll('track').forEach(x=>x.remove());const tr=$('track',{kind:'subtitles',label:audio.files[0].name,srclang:'ru',src:objectURL(audio.files[0]),default:''});player.append(tr);live('Субтитры VTT подключены','ok')});
 const sources=shell('Медиаисточники и права');notice(sources,'Подключайте только файлы, которыми имеете право пользоваться. Доступность внешних URL зависит от CORS и политики владельца.');
 sources.append(row(action('ОТКРЫТЬ ЛЕГАЛЬНЫЕ ИСТОЧНИКИ',()=>openUrl('https://archive.org/details/movies')),action('ОТКРЫТЬ СУЩЕСТВУЮЩЕЕ КИНО NOX',()=>location.assign('cinema.html'))));
 }
 async function loadScript(src){if(document.querySelector('script[data-nox-extra="'+src+'"]')){if(document.querySelector('script[data-nox-extra="'+src+'"]').dataset.loaded==='1')return;throw Error('Модуль ещё загружается')}
 return await new Promise((resolve,reject)=>{const sc=$('script',{src,'data-nox-extra':src});sc.onload=()=>{sc.dataset.loaded='1';resolve()};sc.onerror=()=>reject(new Error('Библиотека отсутствует: '+src));document.head.append(sc)})}
 function books(){const c=shell('Библиотека · PDF / EPUB / TXT');notice(c,'Файлы остаются в браузере. Они не отправляются на сервер. Для EPUB используется epub.js; для PDF — PDF.js.');
 const file=field('Открыть PDF, EPUB или TXT','file');file.accept='.pdf,.epub,.txt,application/pdf,application/epub+zip,text/plain';const view=$('div',{class:'nox-v19-reader'});const prev=action('◀ НАЗАД',()=>nav(-1)),next=action('ВПЕРЁД ▶',()=>nav(1)),txt=$('span',{class:'nox-v19-note',text:'Не открыт файл'});let currentPage=1,pdf=null;
 async function nav(step){try{if(pdf){currentPage=Math.max(1,Math.min(pdf.numPages,currentPage+step));await showPdfPage();}else if(state.book?.rendition){await(step<0?state.book.rendition.prev():state.book.rendition.next())}}catch(e){live(String(e),'error')}}
 async function showPdfPage(){const page=await pdf.getPage(currentPage);const vp=page.getViewport({scale:Math.min(2,Math.max(1,(view.clientWidth||700)/page.getViewport({scale:1}).width))});const cv=$('canvas',{class:'nox-v19-pdfcanvas'});cv.width=Math.floor(vp.width);cv.height=Math.floor(vp.height);view.replaceChildren(cv);await page.render({canvasContext:cv.getContext('2d'),viewport:vp}).promise;txt.textContent='Страница '+currentPage+' / '+pdf.numPages;}
 file.addEventListener('change',async()=>{const f=file.files?.[0];if(!f)return;view.replaceChildren();try{if(/\.pdf$/i.test(f.name)){const module=await import('./vendor/nox-extra/pdf.mjs');module.GlobalWorkerOptions.workerSrc='./vendor/nox-extra/pdf.worker.mjs';pdf=await module.getDocument({data:new Uint8Array(await f.arrayBuffer())}).promise;currentPage=1;await showPdfPage();}
 else if(/\.epub$/i.test(f.name)){await loadScript('./vendor/nox-extra/epub.min.js');const book=window.ePub(await f.arrayBuffer());const rendition=book.renderTo(view,{width:'100%',height:580});await rendition.display();state.book={destroy:()=>book.destroy(),rendition};txt.textContent='EPUB · '+f.name;}
 else{const t=await f.text();const pre=$('article',{class:'nox-v19-text',text:t.slice(0,3e6)});view.append(pre);txt.textContent='TXT · '+f.name;}
 live('Файл открыт локально: '+f.name,'ok');}catch(e){live('Ридер HOLD: '+e.message,'error')}});
 c.append(file,row(prev,next,txt),view)}
 function news(){const c=shell('Новости · реальные источники');notice(c,'Показаны проверяемые ссылки, даты и источники. Никаких вымышленных новостей и автоматических публикаций.');
 const target=$('div',{class:'nox-v19-feed'});c.append(row(action('ЗАГРУЗИТЬ ТЕХНОЛОГИИ',async()=>{target.replaceChildren();live('Получение HN Algolia…');try{const res=await fetch('https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=16',{signal:AbortSignal.timeout(12000)});if(!res.ok)throw Error('HTTP '+res.status);const j=await res.json();for(const h of j.hits||[]){if(!h.title)continue;const u=h.url||('https://news.ycombinator.com/item?id='+encodeURIComponent(h.objectID));let link=$('a',{href:u,target:'_blank',rel:'noopener noreferrer',text:h.title});let date=$('small',{text:' '+new Date(h.created_at).toLocaleString('ru-RU')+' · '+new URL(u).host});target.append($('div',{class:'nox-v19-feed-item'},[link,date]))}live('Получены свежие записи с указанием источников','ok')}catch(e){live('Новости HOLD: '+e.message,'error')}}),action('ЯНДЕКС ДЗЕН',()=>openUrl('https://dzen.ru/')),action('GOOGLE NEWS',()=>openUrl('https://news.google.com/'))),target);
 const rss=shell('RSS / Atom: проверка источника');const url=field('Публичный URL RSS/Atom');const output=$('div',{class:'nox-v19-feed'});rss.append(row(url,action('ПРОВЕРИТЬ RSS',async()=>{output.replaceChildren();try{const u=new URL(url.value);if(u.protocol!=='https:')throw Error('Только HTTPS');const res=await fetch(u.href,{signal:AbortSignal.timeout(10000)});if(!res.ok)throw Error('HTTP '+res.status);const xml=new DOMParser().parseFromString(await res.text(),'application/xml');if(xml.querySelector('parsererror'))throw Error('Некорректный XML');let entries=[...xml.querySelectorAll('item,entry')].slice(0,15);for(const e of entries){const title=e.querySelector('title')?.textContent?.trim()||'Без заголовка';const link=e.querySelector('link')?.getAttribute('href')||e.querySelector('link')?.textContent?.trim();if(!link)continue;const a=$('a',{href:new URL(link,u.href).href,target:'_blank',rel:'noopener noreferrer',text:title});const date=e.querySelector('pubDate,published,updated')?.textContent||'дата не указана';output.append($('div',{class:'nox-v19-feed-item'},[a,$('small',{text:date})]))}live('RSS загружен: '+entries.length+' записей','ok')}catch(e){live('RSS HOLD (возможен CORS): '+e.message,'error')}}),action('ОТКРЫТЬ ИСТОЧНИК',()=>openUrl(url.value))),output)}
 function weather(){
 const c=shell('Погода · интерактивная карта');
 notice(c,'Open-Meteo — реальная погода и прогноз. Карта Leaflet / © OpenStreetMap. Для публичного коммерческого использования нужны разрешённые тарифы поставщиков.');
 const city=field('Найти город: Мадрид, Альмерия, Москва…');
 const layer=$('div',{class:'nox-v19-weather-map','aria-label':'Интерактивная карта прогноза'});
 const info=$('div',{class:'nox-v19-weather-info'});
 const modeButtons=row(),forecast=$('div',{class:'nox-v19-weather-days'});
 const statusMap=$('p',{class:'nox-v19-note',text:'Карта появляется после выбора города. Сведения не запрашиваются автоматически.'});
 let map=null,marker=null,data=null,mode='temperature',painted=false;
 const metric={temperature:{name:'Температура',key:'temperature_2m',suffix:'°C'},wind:{name:'Ветер',key:'wind_speed_10m',suffix:'км/ч'},rain:{name:'Осадки',key:'precipitation',suffix:'мм'}};
 const renderMetric=()=>{
  modeButtons.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===mode)));
  if(!data)return;
  const current=data.current||{},m=metric[mode],value=current[m.key];
  const pretty=value===null||value===undefined?'нет данных':String(value)+' '+m.suffix;
  const seen=current.time||'дата отсутствует';
  info.replaceChildren($('div',{class:'nox-v19-big',text:pretty}),$('p',{class:'nox-v19-note',text:m.name+' · '+seen+' · Open-Meteo'}));
  if(marker){const title=m.name+': '+pretty;marker.bindTooltip(title,{direction:'top',opacity:.94}).openTooltip();}
  forecast.replaceChildren();
  const days=data.daily||{};
  (days.time||[]).slice(0,7).forEach((day,i)=>{
   const hi=days.temperature_2m_max?.[i],lo=days.temperature_2m_min?.[i],rain=days.precipitation_sum?.[i],wind=days.wind_speed_10m_max?.[i];
   forecast.append($('div',{class:'nox-v19-day'},[
    $('strong',{text:day}),$('span',{text:(Number.isFinite(hi)?hi+'°':'—')+' / '+(Number.isFinite(lo)?lo+'°':'—')}),
    $('small',{text:'Осадки '+(rain??'—')+' мм · ветер '+(wind??'—')+' км/ч'})
   ]));
  });
 };
 for(const [modeId,meta] of Object.entries(metric)){const button=action(meta.name,()=>{mode=modeId;renderMetric()});button.dataset.mode=modeId;modeButtons.append(button);}
 async function ensureMap(lat,lon,label){
  if(!window.L){
   const css=document.createElement('link');css.rel='stylesheet';css.href='./vendor/nox-extra/leaflet.css';css.dataset.noxMapStyle='1';document.head.append(css);
   await loadScript('./vendor/nox-extra/leaflet.js');
  }
  if(!window.L)throw Error('Leaflet не загрузился');
  if(!map){
   map=window.L.map(layer,{scrollWheelZoom:false,zoomControl:true,attributionControl:true,preferCanvas:true}).setView([lat,lon],8);
   window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:12,minZoom:2,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>'}).addTo(map);
   state.map=map;
  }else{map.setView([lat,lon],8);}
  if(marker)marker.remove();
  marker=window.L.circleMarker([lat,lon],{radius:10,color:'#e9b978',weight:2,fillColor:'#f2b76b',fillOpacity:.8}).addTo(map).bindPopup(label);
  marker.openPopup();
  painted=true;
  requestAnimationFrame(()=>map.invalidateSize());
 }
 const result=$('div',{class:'nox-v19-weather-results'});
 async function getWeather(item){
  const lat=Number(item.latitude),lon=Number(item.longitude);
  try{
   if(!Number.isFinite(lat)||!Number.isFinite(lon))throw Error('Нет координат');
   const url='https://api.open-meteo.com/v1/forecast?latitude='+encodeURIComponent(lat)+'&longitude='+encodeURIComponent(lon)+'&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max&forecast_days=7&timezone=auto';
   const res=await fetch(url,{signal:AbortSignal.timeout(15000)});if(!res.ok)throw Error('HTTP '+res.status);
   data=await res.json();if(!data?.current)throw Error('Ответ без актуальных данных');
   await ensureMap(lat,lon,item.name+', '+(item.country||''));
   result.replaceChildren();statusMap.textContent='Выбрано: '+item.name+', '+(item.country||'')+' · данные '+(data.current.time||'без даты');
   renderMetric();live('Карта и реальный прогноз обновлены для '+item.name,'ok');
  }catch(e){live('Погодная карта HOLD: '+e.message,'error');statusMap.textContent='Ошибка источника: '+e.message}
 }
 async function search(){
  result.replaceChildren();
  if(city.value.trim().length<2){live('Введите город','error');return}
  try{
   const url='https://geocoding-api.open-meteo.com/v1/search?name='+encodeURIComponent(city.value.trim())+'&count=5&language=ru&format=json';
   const r=await fetch(url,{signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Geocoding HTTP '+r.status);
   const j=await r.json();if(!j.results?.length)throw Error('Город не найден');
   for(const item of j.results)result.append(action(item.name+', '+(item.country||'')+' · '+(item.admin1||''),()=>getWeather(item)));
   live('Выберите город — загрузится карта и прогноз');
  }catch(e){live('Поиск погоды HOLD: '+e.message,'error')}
 }
 city.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();search()}});
 c.append(row(city,action('НАЙТИ ГОРОД',search)),result,modeButtons,statusMap,layer,info,forecast);
 }
 function currency(){const c=shell('Курсы · официальные справочные значения');notice(c,'Frankfurter v2: справочные курсы центральных банков, не биржевые котировки. BYN, EUR, USD, RUB доступны по данным поставщика.');const from=field('Исходная валюта, например EUR'),to=field('Целевая валюта, например BYN'),amount=field('Сумма','number');from.value='EUR';to.value='USD';amount.value='100';const output=$('div',{class:'nox-v19-big'});c.append(row(from,to,amount,action('ПОСЧИТАТЬ',async()=>{try{const a=from.value.trim().toUpperCase(),b=to.value.trim().toUpperCase(),n=Number(amount.value);if(!/^[A-Z]{3}$/.test(a)||!/^[A-Z]{3}$/.test(b)||!Number.isFinite(n)||n<0)throw Error('Введите ISO валюты и положительную сумму');if(a===b){output.textContent=n.toLocaleString('ru-RU')+' '+a;return}const r=await fetch('https://api.frankfurter.dev/v2/rate/'+encodeURIComponent(a.toLowerCase())+'/'+encodeURIComponent(b.toLowerCase()),{signal:AbortSignal.timeout(12000)});if(!r.ok)throw Error('HTTP '+r.status);const v=await r.json();if(!Number.isFinite(v.rate))throw Error('Курс недоступен');output.textContent=new Intl.NumberFormat('ru-RU',{style:'currency',currency:b}).format(n*v.rate);live('Frankfurter · '+v.date+' · 1 '+a+' = '+v.rate+' '+b,'ok')}catch(e){live('Курсы HOLD: '+e.message,'error')}})),output)}
 function browser(){const c=shell('Браузер источников');notice(c,'Используется изолированная вкладка браузера. Ограничения CORS, CSP, DRM и входа на сайты не обходятся.');const url=field('HTTPS URL страницы или поисковый запрос');const bookmarks=$('div',{class:'nox-v19-feed'});const key='nox-browser-bookmarks';const saved=()=>{try{return JSON.parse(localStorage.getItem(key)||'[]')}catch{return []}};const paint=()=>{bookmarks.replaceChildren();for(const u of saved())bookmarks.append(row(action('ОТКРЫТЬ '+new URL(u).host,()=>openUrl(u)),action('УДАЛИТЬ',()=>{localStorage.setItem(key,JSON.stringify(saved().filter(x=>x!==u)));paint()})))};
 const normalize=()=>{const t=url.value.trim();if(!t)throw Error('Введите адрес или запрос');if(t.includes(' ')||!t.includes('.'))return 'https://www.google.com/search?q='+encodeURIComponent(t);const u=new URL(t.startsWith('http')?t:'https://'+t);if(!['https:','http:'].includes(u.protocol))throw Error('Запрещённая схема');return u.href};
 c.append(row(url,action('ОТКРЫТЬ',()=>{try{openUrl(normalize())}catch(e){live(e.message,'error')}}),action('В ИЗБРАННОЕ',()=>{try{const u=normalize(),s=saved();if(!s.includes(u))s.push(u);localStorage.setItem(key,JSON.stringify(s.slice(-80)));paint();live('Адрес сохранён локально','ok')}catch(e){live(e.message,'error')}})),bookmarks);paint()}
 async function sections(){
  const c=shell('Карта сервисов NOX · 130 утверждённых разделов');
  notice(c,'Каталог — утверждённое ТЗ, НЕ 130 работающих экранов. Действующие страницы открываются; остальные честно отмечены как проектируемые.');
  const query=field('Поиск раздела');
  const list=$('div',{class:'nox-v19-sections'});
  c.append(row(query),list);
  try{
   const response=await fetch('./nox-section-map-v19.json',{cache:'force-cache'});
   if(!response.ok)throw Error('Каталог HTTP '+response.status);
   const all=await response.json();
   if(!Array.isArray(all))throw Error('Некорректный каталог');
   const mapping={'Кинотеатр':'cinema.html','Книги / Reader':'memory.html','RU↔ES / Voice':'settings.html','GPU Training':'training.html','RAG':'memory.html','Ask NOX':'chat.html','System':'system.html','Главная':'index.html'};
   function paint(){
    list.replaceChildren();
    const q=query.value.trim().toLowerCase();
    for(const item of all.filter(x=>(x.page+' '+x.section+' '+x.id).toLowerCase().includes(q)).slice(0,130)){
     const link=mapping[item.page];
     const button=action(item.id+' · '+item.page,()=>{
      if(link)location.assign(link);
      else live(item.id+' · '+item.page+': нет принятого обработчика. ТЗ: '+item.actions,'warn');
     });
     button.classList.toggle('nox-v19-planned',!link);
     list.append(button);
    }
   }
   query.addEventListener('input',paint);
   paint();live('Каталог загружен: '+all.length+' строк по утверждённой матрице');
  }catch(e){live('Каталог HOLD: '+e.message,'error')}
 }
 function boot(){document.body.append(root);window.NOX_UNIVERSE_V19=Object.freeze({open,close:dismiss,modules:modules.slice(),source:'V19_SHARED_UI_FUNCTIONS',noFakeRuntime:true})}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
