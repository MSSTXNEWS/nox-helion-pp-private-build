'use strict';
const $=id=>document.getElementById(id);
let csrf='', selectedModel='', revision='', files=[], selectedKind='movie', busy=false, theater=null;
const bc='BroadcastChannel' in window ? new BroadcastChannel('nox-helion-theater'):null;
const CATS=[['movie','🎞','Полнометражное кино'],['cartoon2d','🖍','2D мультфильмы'],['cartoon3d','🧊','3D анимация'],['anime','🌸','Аниме / сериалы'],['adult18','🔞','18+ анимация'],['video','🎥','Клипы / реклама'],['photo','📸','Фотокачество'],['3d','🧬','3D-модели'],['voice','🎙','Озвучка / RU↔ES'],['sound','🎼','Оригинальная музыка'],['slides','📊','Презентации'],['site','🕸','Веб-сайты'],['code','💻','Программирование'],['memory','🧠','Память / RAG'],['learning','⚗','Обучение / LoRA']];
const SPACES=['Кинозал','Космос','Планетарий','Библиотека','Зал знаний','3D-мастерская','Монтажная','Рабочая студия','Персонажи','Мультимониторная сцена'];
const MATERIALS=['Жидкое солнце','Кора обсидиана','Вязкая лава','Янтарная корона','Внутренние потоки','Гравитационный выброс','Восемь орбит','Звёздная пыль','Жидкий металл','Огонь и угли','Титан','Синий атлас','Графит','Зеркальное ядро','Медь FORGE','Циановый голос','Осколки','Объёмный свет','Фокус камеры','Переходы света'];
const MODES=['тихий','легкий','медленный','теплый','холодный','глубокий','пульс','микропараллакс','киноблик','максимальный'];
function showToast(t,isError=false){const node=$('toast');node.textContent=t;node.classList.remove('hidden');node.style.borderColor=isError?'#fa6155':'#ffbd70';setTimeout(()=>node.classList.add('hidden'),4200)}
function output(id,data){$(id).textContent=typeof data==='string'?data:JSON.stringify(data,null,2)}
function navigate(id){document.querySelectorAll('.screen').forEach(el=>el.classList.toggle('active',el.id==='screen-'+id));document.querySelectorAll('[data-nav]').forEach(el=>el.setAttribute('aria-current',el.dataset.nav===id?'true':'false'));window.scrollTo({top:0,behavior:'smooth'})}
async function rpc(action,extra={}){
 const payload={action,...extra};
 if(window.parent!==window){
   return new Promise((resolve,reject)=>{
     const id=crypto.randomUUID();const timeout=setTimeout(()=>{window.removeEventListener('message',onResult);reject(Error('Native creative bridge timeout'))},320000);
     function onResult(event){if(event.origin!==location.origin || event.source!==window.parent || event.data?.kind!=='creativeResult' || event.data.requestId!==id)return;clearTimeout(timeout);window.removeEventListener('message',onResult);event.data.ok?resolve(event.data.data):reject(Error(event.data.error||'Native creative worker error'))}
     window.addEventListener('message',onResult);
     window.parent.postMessage({type:'nox.creative.request.v1',request_id:id,payload},location.origin);
   });
 }
 if(window.chrome?.webview?.postMessage){
   return new Promise((resolve,reject)=>{
     const id=crypto.randomUUID();const timer=setTimeout(()=>{window.chrome.webview.removeEventListener('message',handler);reject(Error('Native creative bridge timeout'))},320000);
     function handler(event){if(event.data?.kind!=='creativeResult'||event.data.requestId!==id)return;clearTimeout(timer);window.chrome.webview.removeEventListener('message',handler);event.data.ok?resolve(event.data.data):reject(Error(event.data.error||'Bridge error'))}
     window.chrome.webview.addEventListener('message',handler);window.chrome.webview.postMessage({action:'creativeInvoke',requestId:id,payload});
   });
 }
 if(!csrf)throw Error('NOX backend unavailable — use native host or localhost preview');
 const response=await fetch('/api/dispatch',{method:'POST',headers:{'Content-Type':'application/json','X-NOX-CSRF':csrf},body:JSON.stringify(payload)});
 const data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||'NOX adapter error');return data.data;
}
async function task(action,extra={},target='chat-output'){
 if(busy){showToast('Другая задача ещё выполняется',true);return}
 busy=true;output(target,'Запрос отправлен · ожидаем подтверждение реального движка');
 try{const r=await rpc(action,extra);output(target,r);showToast(r.status||'Ответ получен');return r}
 catch(e){output(target,{status:'HOLD / FAILED',reason:String(e.message||e)});showToast(String(e.message||e),true)}finally{busy=false}
}
function renderCategories(){const grid=$('categories'),select=$('kind');for(const [key,emoji,title] of CATS){const btn=document.createElement('button');btn.className='tile';const b=document.createElement('b');b.textContent=emoji+' '+title;const hint=document.createElement('small');hint.textContent=key==='adult18'?'Только совершеннолетние персонажи и зрители':'Выбор инструмента';btn.append(b,hint);btn.onclick=()=>{selectedKind=key;select.value=key;showToast('Выбрано: '+title);$('prompt').focus()};grid.append(btn);const o=document.createElement('option');o.value=key;o.textContent=title;select.append(o)}select.onchange=()=>selectedKind=select.value}
async function refresh(){try{const s=await rpc('status');const summary=Object.entries(s.engines).map(([k,v])=>'<div class="status-line"><span>'+k+'</span><strong class="'+(v?'ok':'error')+'">'+(v?'Готов':'OFFLINE')+'</strong></div>').join('');$('quick-status').innerHTML=summary;$('status').innerHTML=summary+'<pre>'+JSON.stringify(s,null,2)+'</pre>'}catch(e){$('quick-status').textContent='Backend HOLD: '+e.message;$('status').textContent='Backend HOLD: '+e.message}}
async function renderModels(){try{const r=await rpc('catalog');$('models').replaceChildren();for(const m of r.models){const card=document.createElement('div');card.className='model';const h=document.createElement('h3');h.textContent=m.name;const p=document.createElement('p');p.textContent=m.vram+' · '+m.category+(m.installed?' · Установлена':' · Ещё не загружена');const link=document.createElement('a');link.href=m.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='Карточка модели / лицензия';const btn=document.createElement('button');btn.className='action';btn.textContent='Выбрать веса';btn.onclick=()=>selectModel(m.id);card.append(h,p,link,document.createElement('br'),btn);$('models').append(card)}}catch(e){$('models').textContent='Каталог недоступен: '+e.message}}
async function selectModel(id){selectedModel=id;revision='';files=[];$('variants').replaceChildren();$('model-info').textContent='Запрашиваем реальные варианты и лицензию…';try{const r=await rpc('variants',{model_id:id});revision=r.revision;$('model-info').textContent=id+' · Revision: '+revision+' · License: '+r.license+' · '+r.files.length+' весовых файлов';for(const f of r.files){const label=document.createElement('label');const input=document.createElement('input');input.type='checkbox';input.style.width='20px';input.style.minHeight='20px';input.value=f.path;input.onchange=()=>{files=[...document.querySelectorAll('#variants input:checked')].map(x=>x.value)};label.append(input,document.createTextNode(' '+f.path+' · '+(f.bytes==null?'размер неизвестен':Math.round(f.bytes/1048576)+' МБ')));$('variants').append(label)}}catch(e){$('model-info').textContent='HOLD: '+e.message}}
const popup=(action,value)=>bc?.postMessage({action,value});
function openTheater(){
 if(window.parent!==window){window.parent.postMessage({type:'nox.creative.projector.v1'},location.origin);showToast('Окно проектора запрошено у NOX Windows');return;}
 theater=window.open('theater.html','nox-helion-projector','popup,width=1100,height=700');
 if(!theater)showToast('Разреши всплывающее окно для проектора',true);else showToast('Окно открыто — перенеси на проектор');
}
function wowOptions(){for(let i=0;i<20;i++)for(let j=0;j<10;j++){let o=document.createElement('option');o.value=i*10+j+1;o.textContent=`WOW ${String(i*10+j+1).padStart(3,'0')} · ${MATERIALS[i]} · ${MODES[j]}`;$('wow-preset').append(o)}}
function applyWow(){let value=Number($('wow-preset').value)||1;let i=Math.floor((value-1)/10),j=(value-1)%10;let perf=$('quality').value;document.body.className='mode-'+perf;document.documentElement.style.setProperty('--edge',j>6?'rgba(255,173,86,.65)':'rgba(223,147,64,.33)');document.documentElement.style.setProperty('--fx-hue',String(i*17)+'deg');document.documentElement.style.setProperty('--fx-intensity',String(.18+j*.07));document.documentElement.style.setProperty('--fx-speed',String(17-j)+'s');document.documentElement.style.setProperty('--fx-drift',String(2+i%8)+'px');$('fx-details').textContent=MATERIALS[i]+' / '+MODES[j]+'; профиль '+perf+'. Процедурный пресет (не новый GPU-движок).'}
async function init(){renderCategories();wowOptions();for(const b of document.querySelectorAll('[data-nav]'))b.onclick=()=>navigate(b.dataset.nav);$('route').onclick=()=>task('route_chat',{text:$('prompt').value});
$('chat-execute').onclick=async()=>{const r=await task('chat_execute',{text:$('prompt').value,project_id:$('project').value.trim(),scenes:Number($('scenes').value)},'chat-output');if(r?.project_id)$('project').value=r.project_id};
$('draft').onclick=()=>{const k=$('kind').value,p=$('prompt').value,id=$('project').value.trim();if(['movie','cartoon2d','cartoon3d','anime','adult18','video'].includes(k))task('storyboard',{kind:k,prompt:p,scenes:Number($('scenes').value),project_id:id}).then(r=>{if(r?.project_id)$('project').value=r.project_id});else if(['slides','site','code','voice','sound','memory','learning'].includes(k))task('create_text',{kind:k,prompt:p,project_id:id}).then(r=>{if(r?.project_id)$('project').value=r.project_id});else{navigate('jobs');showToast('Для '+k+' выбери реальный ComfyUI workflow или Blender') }};
$('stop').onclick=async()=>{if(!confirm('Остановить локальный FFmpeg? Сторонние ComfyUI-задания не удаляются.'))return;try{const r=await rpc('stop');output('chat-output',r);showToast(r.status)}catch(e){showToast('STOP: '+e.message,true)}};
$('refresh').onclick=refresh;$('download').onclick=()=>task('download',{model_id:selectedModel,revision,filenames:files,license_confirmed:$('license').checked},'model-output');
$('queue').onclick=async()=>{const result=await task('workflow',{workflow:$('workflow').value,text_node:$('node').value,prompt:$('prompt').value},'job-output');if(result?.prompt_id)$('prompt-id').value=result.prompt_id};
$('load-checkpoints').onclick=async()=>{try{const r=await rpc('checkpoints');$('checkpoint').replaceChildren();for(const c of r.checkpoints){const o=document.createElement('option');o.value=c;o.textContent=c;$('checkpoint').append(o)}showToast('Найдено checkpoint: '+r.checkpoints.length)}catch(e){showToast('HOLD: '+e.message,true)}};
$('basic-image').onclick=async()=>{const r=await task('basic_image_workflow',{checkpoint:$('checkpoint').value},'job-output');if(r?.workflow){$('workflow').value=r.workflow;$('node').value=r.text_node;navigate('jobs')}};
$('check').onclick=async()=>{const r=await task('history',{prompt_id:$('prompt-id').value},'job-output');const dest=$('job-files');dest.replaceChildren();if(r?.status==='COMPLETE'){for(const f of r.files||[]){const b=document.createElement('button');b.className='action';b.textContent='Импортировать '+f.filename;b.onclick=async()=>{const id=$('project').value.trim();if(!id){showToast('Сначала укажи ID проекта',true);return}await task('import_asset',{prompt_id:r.prompt_id,asset:f,project_id:id},'asset-output')};dest.append(b)}}};
$('assemble').onclick=()=>task('assemble',{project_id:$('project').value,clips:$('clips').value.split('\n').map(x=>x.trim()).filter(Boolean),soundtrack:$('soundtrack').value.trim(),subtitle_file:$('subtitles').value.trim()},'assemble-output');
$('upload-asset').onclick=async()=>{
 const id=$('project').value.trim();if(!id){showToast('Укажи ID проекта',true);return}
 if(window.parent!==window || window.chrome?.webview?.postMessage){
   const r=await task('native_import',{project_id:id},'asset-output');if(r?.path)showToast('Импортирован: '+r.path);return;
 }
 const f=$('asset-file').files[0];if(!f||!csrf){showToast('Выбери файл и проверь локальную сессию',true);return}
 try{const resp=await fetch('/api/upload',{method:'POST',headers:{'X-NOX-CSRF':csrf,'X-NOX-Project':id,'X-NOX-Filename':encodeURIComponent(f.name)},body:f});const data=await resp.json();output('asset-output',data.ok?data.data:data.error);if(data.ok)showToast('Импорт выполнен')}catch(e){showToast('Импорт недоступен: '+e.message,true)}
};
$('list-assets').onclick=()=>task('project_files',{project_id:$('project').value.trim()},'asset-output');
$('make-3d').onclick=async()=>{const r=await task('make_3d',{project_id:$('project').value.trim(),form:$('shape').value,color:$('shape-color').value},'3d-output');if(r?.project_id)$('project').value=r.project_id};
$('speak').onclick=async()=>{const r=await task('speak',{text:$('voice-text').value,language:$('voice-language').value,project_id:$('project').value.trim()},'voice-output');if(r?.project_id)$('project').value=r.project_id};
$('preview-movie').onclick=()=>{openTheater();showToast('Открой созданный MP4 в окне проектора через «Выбрать видео»')};
$('theater-open').onclick=openTheater;$('theater-title').oninput=()=>popup('title',$('theater-title').value); $('theater-play').onclick=()=>popup('play');$('theater-pause').onclick=()=>popup('pause');$('theater-full').onclick=()=>{popup('fullscreen');showToast('Полный экран должен быть подтверждён в окне проектора')};
const spaces=$('spaces');for(const s of SPACES){const b=document.createElement('button');b.className='tile';b.textContent=s;b.onclick=()=>{popup('space',s);showToast('Выбрана сцена: '+s)};spaces.append(b)}$('open-space').onclick=openTheater;$('apply-fx').onclick=applyWow;applyWow();
try{let response=await fetch('/api/bootstrap');if(response.ok){const b=await response.json();csrf=b.csrf}}catch{};
await refresh();await renderModels();}
init().catch(e=>showToast('Initialization failed: '+e.message,true));
