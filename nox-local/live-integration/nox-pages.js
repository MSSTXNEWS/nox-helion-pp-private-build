/* All values come from localhost NOX APIs; no fake data or synthetic models. */
(()=>{'use strict';
const $=s=>document.querySelector(s), page=document.body.dataset.noxPage;
const set=(id,t)=>{const el=document.getElementById(id);if(el)el.textContent=t};
const ask=async path=>{const r=await fetch(path,{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!r.ok)throw Error('HTTP '+r.status);return await r.json()};
const make=(t,c,text)=>{let e=document.createElement(t);if(c)e.className=c;if(text!==undefined)e.textContent=text;return e};
function label(text,value){const r=make('div','nox-data-row');r.append(make('span','',text),make('strong','',value));return r}
const area=$('#nox-live-content');
const notice=txt=>{if(!area)return;area.replaceChildren(make('p','nox-muted',txt))};
const niceSize=n=>Number.isFinite(Number(n))?(Number(n)/1024/1024/1024).toFixed(2)+' GB':'Н/Д';
async function models(){let d=await ask('/api/status');let list=d.models||[];if(!list.length)return notice('OLLAMA OFFLINE / модели отсутствуют. Никакие данные не имитируются.');area.replaceChildren();for(const m of list){let row=make('div','nox-data-row');const info=make('div');info.append(make('strong','',m.name),make('small','',niceSize(m.size)));const btn=make('a','nox-act','Открыть в CHAT');btn.href='./chat.html?model='+encodeURIComponent(m.name);row.append(info,btn);area.append(row)} }
async function memory(){const d=await ask('/api/nox/discover');area.replaceChildren();let x=d.s03_candidates||[];if(!x.length)return notice('S03: HOLD. Не найден подтверждённый путь к исходной памяти.');area.append(make('p','nox-muted','Найденные SQLite базы (только чтение; запись запрещена до проверки схемы):'));for(const it of x){let item=make('div','nox-data-row');item.append(make('strong','',it.path),make('small','',it.tables.join(', ')||'Нет доступных таблиц'));area.append(item)}}
async function system(){const d=await ask('/api/pc-metrics');area.replaceChildren();for(let [key,title] of [['cpu_percent','CPU'],['ram_percent','RAM'],['gpu_percent','GPU'],['gpu_temperature_c','Температура GPU'],['cpu_temperature_c','Температура CPU'],['vram_used_gb','VRAM GB']]){let n=d[key];area.append(label(title,Number.isFinite(Number(n))&&n!==null?String(n)+(key.includes('temperature')?'°C':key.includes('percent')?'%':''):'Н/Д'))}area.append(label('Источник GPU',d.gpu_source||'Н/Д'));}
async function install(){area.replaceChildren();let d=await ask('/api/nox/discover');area.append(label('C:\\NOX_HELION',d.root_available?'Доступен':'HOLD'));area.append(label('Подключение к существующему ИИ','Доступно через CHAT'));area.append(make('p','nox-muted','Установка драйверов, удаление и перенос моделей требуют отдельного разрешения.'))}
async function projects(){area.replaceChildren(make('p','nox-muted','Проекты: HOLD. Для работы с файлами нужен подтверждённый оригинальный каталог проектов и разрешения. Выдуманные проекты не показываются.'))}
async function settings(){area.replaceChildren();for(const key of ['MAX','BALANCED','ECO']){const b=make('button','nox-act',key);b.onclick=()=>{localStorage.setItem('nox-visual-mode',key);set('nox-settings-status','Режим сохранён: '+key+'. Применяется после перехода на HOME.');};area.append(b)}let p=make('p','nox-muted','Reduced Motion: учитывается системная настройка браузера.');area.append(p);area.append(make('p','nox-muted','',));area.append(make('div','nox-muted','Системные уведомления требуют отдельного разрешения; Web Push — проверенной доставки.'))}
const handlers={models,memory,system,install,projects,settings};
if(handlers[page])handlers[page]().catch(e=>notice('HOLD: '+e.message));
const refresh=$('#nox-refresh');if(refresh)refresh.onclick=()=>handlers[page]?.().catch(e=>notice('HOLD: '+e.message));
})();