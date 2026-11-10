/* NOX HELION V19 — shared working media/info/browser suite; original D02 untouched.
 * Network requests are made only after a user action. No synthetic API health/status.
 * Built as a reversible overlay over the existing ten native web pages.
 */
(()=>{'use strict';
 if(window.NOX_UNIVERSE_V19)return;
 const modules=['Кинотеатр','Книги','Календарь','Галерея','Эффекты','Новости','Уведомления','Погода','Валюта','Браузер','Разделы'];
 const $=(tag,props={},children=[])=>{const el=document.createElement(tag);for(const [k,v] of Object.entries(props)){if(k==='class')el.className=v;else if(k==='text')el.textContent=v;else if(k==='html')el.innerHTML=v;else el.setAttribute(k,v)};for(const c of children)el.append(c);return el};
 const state={active:'Кинотеатр',book:null,video:null,catalog:null,objectUrls:[],player:null,map:null,search:''};
 const pendingScripts=new Map();
 const clean=()=>{if(state.fx){try{state.fx.destroy()}catch{}state.fx=null}if(state.calendar){try{state.calendar.destroy()}catch{}state.calendar=null}if(state.galleryLightbox){try{state.galleryLightbox.destroy()}catch{}state.galleryLightbox=null}if(state.map){try{state.map.remove()}catch{}state.map=null}for(const u of state.objectUrls)URL.revokeObjectURL(u);state.objectUrls=[];if(state.book?.destroy)try{state.book.destroy()}catch{}state.book=null;state.video?.pause?.();state.video=null;if(state.player?.destroy)try{state.player.destroy()}catch{}state.player=null};
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
 if(name==='Кинотеатр')cinema();else if(name==='Книги')books();else if(name==='Календарь')calendar();else if(name==='Галерея')gallery();else if(name==='Эффекты')effects();else if(name==='Новости')news();else if(name==='Уведомления')notifications();else if(name==='Погода')weather();else if(name==='Валюта')currency();else if(name==='Браузер')browser();else sections();}
 function open(){panel.hidden=false;openBtn.hidden=true;show(state.active);close.focus()}
 function dismiss(){clean();panel.hidden=true;openBtn.hidden=false;openBtn.focus()}
 openBtn.addEventListener('click',open);close.addEventListener('click',dismiss);
 panel.addEventListener('keydown',e=>{if(e.key==='Escape')dismiss()});
 const openUrl=(url)=>{try{const u=new URL(url);if(!['https:','http:'].includes(u.protocol))throw Error('Только HTTP(S)');window.open(u.href,'_blank','noopener,noreferrer')}catch(e){live('Недопустимый адрес: '+e.message,'error')}};
 function objectURL(file){const u=URL.createObjectURL(file);state.objectUrls.push(u);return u}
 function cinema(){const c=shell('Кинотеатр · реальное воспроизведение');notice(c,'Разрешённые файлы и прямые HTTP(S) видеопотоки. DRM и закрытые сайты не обходятся. Каталог сторонних фильмов без лицензии не подставляется.');
 const url=field('URL прямого MP4/WebM/HLS или локальный файл'),local=field('Выбрать видеофайл','file');local.accept='video/*,.m3u8';
 const audio=field('Выбрать субтитры VTT','file');audio.accept='.vtt,text/vtt';
 const player=$('video',{controls:'',playsinline:'',preload:'metadata',class:'nox-v19-video'}),info=$('div',{class:'nox-v19-note'});state.video=player;
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
 async function loadScript(src){
  if(!src.startsWith('./vendor/nox-extra/'))throw Error('Разрешены только локальные проверенные библиотеки');
  if(pendingScripts.has(src))return pendingScripts.get(src);
  const script=document.querySelector('script[data-nox-extra="'+src+'"]');
  if(script?.dataset.loaded==='1')return;
  const promise=new Promise((resolve,reject)=>{
   const sc=script||$('script',{src,'data-nox-extra':src});
   sc.onload=()=>{sc.dataset.loaded='1';resolve()};
   sc.onerror=()=>{sc.remove();reject(new Error('Библиотека недоступна: '+src))};
   if(!script)document.head.append(sc);
  });
  pendingScripts.set(src,promise);
  try{return await promise}finally{pendingScripts.delete(src)}
 }
 function books(){const c=shell('Библиотека · PDF / EPUB / TXT');notice(c,'Файлы остаются в браузере. Они не отправляются на сервер. Для EPUB используется epub.js; для PDF — PDF.js.');
 const file=field('Открыть PDF, EPUB или TXT','file');file.accept='.pdf,.epub,.txt,application/pdf,application/epub+zip,text/plain';const view=$('div',{class:'nox-v19-reader'});const prev=action('◀ НАЗАД',()=>nav(-1)),next=action('ВПЕРЁД ▶',()=>nav(1)),txt=$('span',{class:'nox-v19-note',text:'Не открыт файл'});let currentPage=1,pdf=null;
 async function nav(step){try{if(pdf){currentPage=Math.max(1,Math.min(pdf.numPages,currentPage+step));await showPdfPage();}else if(state.book?.rendition){await(step<0?state.book.rendition.prev():state.book.rendition.next())}}catch(e){live(String(e),'error')}}
 async function showPdfPage(){const page=await pdf.getPage(currentPage);const vp=page.getViewport({scale:Math.min(2,Math.max(1,(view.clientWidth||700)/page.getViewport({scale:1}).width))});const cv=$('canvas',{class:'nox-v19-pdfcanvas'});cv.width=Math.floor(vp.width);cv.height=Math.floor(vp.height);view.replaceChildren(cv);await page.render({canvasContext:cv.getContext('2d'),viewport:vp}).promise;txt.textContent='Страница '+currentPage+' / '+pdf.numPages;}
 file.addEventListener('change',async()=>{const f=file.files?.[0];if(!f)return;view.replaceChildren();try{if(/\.pdf$/i.test(f.name)){const module=await import('./vendor/nox-extra/pdf.mjs');module.GlobalWorkerOptions.workerSrc='./vendor/nox-extra/pdf.worker.mjs';pdf=await module.getDocument({data:new Uint8Array(await f.arrayBuffer())}).promise;currentPage=1;await showPdfPage();}
 else if(/\.epub$/i.test(f.name)){await loadScript('./vendor/nox-extra/epub.min.js');const book=window.ePub(await f.arrayBuffer());const rendition=book.renderTo(view,{width:'100%',height:580});await rendition.display();state.book={destroy:()=>book.destroy(),rendition};txt.textContent='EPUB · '+f.name;}
 else{const t=await f.text();const pre=$('article',{class:'nox-v19-text',text:t.slice(0,3e6)});view.append(pre);txt.textContent='TXT · '+f.name;}
 live('Файл открыт локально: '+f.name,'ok');}catch(e){live('Ридер HOLD: '+e.message,'error')}});
 c.append(file,row(prev,next,txt),view)}
 function calendar(){
  const c=shell('Календарь NOX · реальные локальные события');
  notice(c,'FullCalendar 6.1.19. События сохраняются только в этом браузере. Интеграция Google/Microsoft Calendar требует отдельного OAuth и разрешений.');
  const name=field('Название события'),date=field('Дата события','date');
  const mount=$('div',{class:'nox-v19-calendar',role:'application','aria-label':'Календарь NOX'});
  const key='nox-v19-calendar-events';
  const read=()=>{try{const v=JSON.parse(localStorage.getItem(key)||'[]');return Array.isArray(v)?v.slice(-1000):[]}catch{return []}};
  const store=a=>localStorage.setItem(key,JSON.stringify(a.slice(-1000)));
  const button=action('ДОБАВИТЬ СОБЫТИЕ',()=>{
   if(!name.value.trim()||!date.value){live('Введите название и дату','warn');return}
   try{const records=read(),event={id:String(Date.now())+'-'+Math.round(Math.random()*1e6),title:name.value.trim().slice(0,140),start:date.value,allDay:true};records.push(event);store(records);state.calendar?.addEvent(event);name.value='';live('Событие сохранено в браузере, не отправлено в календарный API','ok')}catch(e){live('Сохранение HOLD: '+e.message,'error')}
  });
  const clear=action('УДАЛИТЬ ВЫБРАННОЕ',()=>live('Нажмите событие в календаре и подтвердите удаление','warn'));
  c.append(row(name,date,button,clear),mount);
  loadScript('./vendor/nox-extra/fullcalendar.global.min.js').then(()=>{
   if(state.active!=='Календарь'||!mount.isConnected)return;
   const Calendar=window.FullCalendar?.Calendar;
   if(!Calendar)throw Error('FullCalendar не инициализирован');
   const instance=new Calendar(mount,{
    initialView:'dayGridMonth',height:'auto',locale:'ru',firstDay:1,editable:false,selectable:false,
    headerToolbar:{left:'prev,next today',center:'title',right:'dayGridMonth,dayGridWeek'},
    buttonText:{today:'Сегодня',month:'Месяц',week:'Неделя'},
    events:read(),eventClick:arg=>{
     if(!confirm('Удалить событие «'+arg.event.title+'»?'))return;
     try{store(read().filter(e=>e.id!==arg.event.id));arg.event.remove();live('Событие удалено локально','ok')}catch(e){live('Удаление HOLD: '+e.message,'error')}
    }
   });
   instance.render();state.calendar=instance;live('FullCalendar загружен локально. События работают без серверного API.','ok');
  }).catch(e=>live('Календарь HOLD: '+e.message,'error'));
 }
 function gallery(){
  const c=shell('Галерея NOX · кинематографическое просмотр фото');
  notice(c,'PhotoSwipe 5.4.4. Локальные изображения не отправляются в сеть. Масштаб, жесты и полноэкранное погружение доступны после загрузки файлов.');
  const input=field('Выбрать изображения','file');input.accept='image/png,image/jpeg,image/webp,image/avif,image/gif';input.multiple=true;
  const grid=$('div',{class:'nox-v19-gallery',id:'nox-v19-gallery-source'});
  const info=$('div',{class:'nox-v19-note',role:'status',text:'Изображения пока не выбраны'});
  const reset=action('ОЧИСТИТЬ ГАЛЕРЕЮ',()=>{state.galleryLightbox?.destroy?.();state.galleryLightbox=null;for(const u of state.objectUrls)URL.revokeObjectURL(u);state.objectUrls=[];grid.replaceChildren();info.textContent='Галерея очищена';});
  async function render(){
   state.galleryLightbox?.destroy?.();state.galleryLightbox=null;
   for(const u of state.objectUrls)URL.revokeObjectURL(u);state.objectUrls=[];grid.replaceChildren();
   const files=[...input.files||[]].slice(0,80);let added=0;
   for(const file of files){
    if(!file.type.startsWith('image/'))continue;
    const url=objectURL(file);
    const img=new Image();img.src=url;
    try{await img.decode()}catch{continue}
    const a=$('a',{href:url,target:'_blank',class:'nox-v19-gallery-item','data-pswp-width':String(img.naturalWidth),'data-pswp-height':String(img.naturalHeight),'aria-label':'Открыть '+file.name});
    a.append($('img',{src:url,alt:file.name,loading:'lazy'}));grid.append(a);added++;
   }
   info.textContent='Реальные изображения: '+added+' · локальные файлы';
   if(!added)return;
   try{
    const tag=document.querySelector('link[data-nox-photoswipe]');
    if(!tag){const link=$('link',{rel:'stylesheet',href:'./vendor/nox-extra/photoswipe.css','data-nox-photoswipe':'true'});document.head.append(link)}
    const mod=await import('./vendor/nox-extra/photoswipe-lightbox.esm.js');
    if(state.active!=='Галерея'||!grid.isConnected)return;
    const Lightbox=mod.default;
    const lightbox=new Lightbox({gallery:'#nox-v19-gallery-source',children:'a',pswpModule:()=>import('./vendor/nox-extra/photoswipe.esm.js')});
    lightbox.init();state.galleryLightbox=lightbox;live('PhotoSwipe загружен локально, изображений: '+added,'ok');
   }catch(e){live('Галерея: обычные ссылки доступны, PhotoSwipe HOLD: '+e.message,'warn')}
  }
  input.addEventListener('change',()=>{render().catch(e=>live('Галерея HOLD: '+e.message,'error'))});
  c.append(row(input,reset),info,grid);
 }
 function effects(){
  const c=shell('Атмосфера NOX · реальные частицы');
  notice(c,'Локальный tsParticles Slim 4.5.3. Эффект работает только внутри панели сервисов, не создаёт второй рендерер D02. Во время чтения и Reduced Motion он не запускается.');
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const container=$('div',{id:'nox-v19-particles',class:'nox-v19-particles','aria-label':'Живая атмосферная сцена'}),details=$('p',{class:'nox-v19-note',text:'FX не запущен'});
  const stop=async()=>{if(state.fx){try{await state.fx.destroy()}catch{}state.fx=null}container.replaceChildren();details.textContent='Эффект остановлен';live('FX STOP · без фоновых циклов','ok')};
  async function run(level){
   await stop();
   if(reduced.matches){live('Reduced Motion: частицы отключены','warn');return}
   try{
    await loadScript('./vendor/nox-extra/tsparticles.slim.bundle.min.js');
    const engine=window.tsParticles||window.__tsParticlesInternals?.engine?.tsParticles;
    if(!engine?.load)throw Error('tsParticles bundle API unavailable');
    const count=level==='MAX'?100:level==='BALANCED'?42:15;
    const cfg={
     background:{color:{value:'#04080e'}},fullScreen:{enable:false},
     fpsLimit:level==='ECO'?24:level==='BALANCED'?36:48,
     detectRetina:true,pauseOnBlur:true,pauseOnOutsideViewport:true,
     particles:{
      number:{value:count,density:{enable:true,area:1000}},
      color:{value:['#b5b8c3','#e4b474','#7da0bb']},
      opacity:{value:{min:.15,max:.53},animation:{enable:false}},
      size:{value:{min:.5,max:1.7}},
      links:{enable:false},collisions:{enable:false},
      move:{enable:true,speed:level==='MAX'?.28:.12,random:true,straight:false,outModes:{default:'out'}},
      shape:{type:'circle'}
     },interactivity:{events:{onHover:{enable:false},onClick:{enable:false},resize:{enable:true}}}
    };
    const instance=await engine.load({id:'nox-v19-particles',options:cfg});
    if(state.active!=='Эффекты'||!container.isConnected){instance?.destroy?.();return}
    state.fx=instance;details.textContent='tsParticles Slim · '+level+' · '+count+' частиц (пресет, не метрика NOX)';
    live('GPU-эффекты: '+level+' · источник локальный tsParticles','ok');
   }catch(e){live('WOW FX HOLD: '+e.message,'error')}
  }
  c.append(row(action('MAX · 100 ЧАСТИЦ',()=>run('MAX')),action('BALANCED · 42',()=>run('BALANCED')),action('ECO · 15',()=>run('ECO')),action('STOP FX',stop)),details,container);
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&state.fx)state.fx.pause?.()},{once:true});
 }
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

 function notifications(){
  const c=shell('Уведомления · Центр событий NOX');
  notice(c,'Локальное уведомление — это не серверный Web Push. Отправка на другое устройство требует подписки, VAPID, backend и подтверждённой доставки.');
  const output=$('div',{class:'nox-v19-feed','aria-label':'Локальная история уведомлений'}),detail=$('p',{class:'nox-v19-note'});
  const key='nox-v19-notifications';
  const get=()=>{try{const value=JSON.parse(localStorage.getItem(key)||'[]');return Array.isArray(value)?value.slice(-50):[]}catch{return []}};
  const save=x=>{try{localStorage.setItem(key,JSON.stringify(x.slice(-50)))}catch(e){live('История уведомлений не сохранена: '+e.message,'error')}};
  const status=$('div',{class:'nox-v19-notification-state'});
  async function inspect(){
   const hasAPI=('Notification' in window),hasWorker=('serviceWorker' in navigator),secure=window.isSecureContext;
   const permission=hasAPI?Notification.permission:'UNSUPPORTED';
   let sub='HOLD';try{const registration=await navigator.serviceWorker?.getRegistration?.();const current=registration?.pushManager?await registration.pushManager.getSubscription():null;sub=current?'PUSH_SUBSCRIPTION_PRESENT_NOT_DELIVERY_VERIFIED':'NO_ACTIVE_PUSH_SUBSCRIPTION'}catch(e){sub='PUSH_CHECK_FAILED: '+e.message}
   status.textContent='HTTPS: '+(secure?'OK':'HOLD')+' · Разрешение: '+permission+' · Service Worker: '+(hasWorker?'SUPPORTED':'UNAVAILABLE')+' · '+sub;
   status.dataset.type=hasAPI&&secure?'info':'warn';
  }
  function paint(){output.replaceChildren();const rows=get().slice().reverse();if(!rows.length)output.append($('p',{class:'nox-v19-note',text:'Пока нет локальных уведомлений.'}));
   for(const row of rows){const card=$('div',{class:'nox-v19-feed-item'});
    card.append($('strong',{text:String(row.title||'NOX').slice(0,100)}),$('small',{text:String(row.at||'')+' · '+(row.read?'Прочитано':'Новое')}),$('p',{text:String(row.message||'').slice(0,500)}));
    card.append(action('ПРОЧИТАНО',()=>{const all=get();const target=all.find(x=>x.id===row.id);if(target)target.read=true;save(all);paint()}));output.append(card);
   }
  }
  async function localTest(){
   if(!('Notification' in window)){live('Этот браузер не поддерживает уведомления','error');return}
   if(!window.isSecureContext){live('Для уведомлений необходим безопасный HTTPS/localhost','error');return}
   let permission=Notification.permission;
   if(permission==='default')permission=await Notification.requestPermission();
   if(permission!=='granted'){live('Пользователь не разрешил уведомления: '+permission,'warn');await inspect();return}
   const event={id:String(Date.now()),title:'NOX HELION · Тест',message:'Локальное уведомление. Удалённая Web Push доставка НЕ проверена.',at:new Date().toISOString(),read:false};
   try{new Notification(event.title,{body:event.message,tag:'nox-v19-local-test'})}catch(e){live('Системный показ HOLD: '+e.message,'error');return}
   const all=get();all.push(event);save(all);paint();await inspect();live('Локальное уведомление показано. Это не push-доставка на устройство.','ok');
  }
  c.append(status,row(action('ПРОВЕРИТЬ ПОДПИСКУ',inspect),action('ТЕСТ НА ЭТОМ УСТРОЙСТВЕ',localTest),action('НАСТРОЙКИ PUSH NOX',()=>location.assign('settings.html')),action('ОЧИСТИТЬ ЛОКАЛЬНУЮ ИСТОРИЮ',()=>{if(confirm('Удалить только локальную историю уведомлений этого браузера?')){save([]);paint();live('Удалена только локальная история','ok')}})),detail,output);
  detail.textContent='Реальная отправка через native-push-sw.js возможна лишь после подключения и проверки исходного API /api/ui/push, без фальшивого PASS.';
  paint();inspect();
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
   // Fuse.js runs only against the real approved local section catalog, never against invented data.
   let finder=null;
   try{
    await loadScript('./vendor/nox-extra/fuse.min.js');
    if(window.Fuse)finder=new window.Fuse(all,{keys:['page','section','id','actions'],threshold:0.33,ignoreLocation:true});
   }catch(e){live('Поиск: обычный режим (Fuse.js недоступен): '+e.message,'warn')}
   // Show clickable buttons only where a real existing route exists.
   // Retain all 130 requirements as READ-ONLY catalog data, not inert active controls.
   const mapping={'Кинотеатр':'cinema.html','Книги / Reader':'memory.html','GPU Training':'training.html','RAG':'memory.html','Ask NOX':'chat.html','System':'system.html','Главная':'index.html'};
   function paint(){
    list.replaceChildren();
    const q=query.value.trim().toLowerCase();
    const results=q?(finder?finder.search(q,{limit:130}).map(r=>r.item):all.filter(x=>(x.page+' '+x.section+' '+x.id+' '+x.actions).toLowerCase().includes(q))):all;
    let active=0,reference=0;
    for(const item of results.slice(0,130)){
      const link=mapping[item.page];
      if(link){
        const button=action(item.id+' · '+item.page,()=>location.assign(link));
        button.dataset.noxAction='navigate';
        list.append(button);active++;
      }else{
        const line=$('p',{class:'nox-v19-note',text:item.id+' · '+item.page+' — ТЗ, обработчик не подключён'});
        line.dataset.noxRequirement='not-a-button';
        list.append(line);reference++;
      }
    }
    live('Действующих кнопок перехода: '+active+' · только требования без обработчика: '+reference+'. Никаких ложных кнопок.');
   }
   query.addEventListener('input',paint);
   paint();live('Каталог загружен: '+all.length+' строк по утверждённой матрице');
  }catch(e){live('Каталог HOLD: '+e.message,'error')}
 }
 function boot(){document.body.append(root);window.NOX_UNIVERSE_V19=Object.freeze({open,close:dismiss,modules:modules.slice(),source:'V19_SHARED_UI_FUNCTIONS',noFakeRuntime:true})}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
