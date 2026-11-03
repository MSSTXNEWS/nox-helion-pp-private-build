const SECTIONS = [
  {id:'work', title:'РАБОТА', items:[
    ['Проекты','задачи и планы'],['Задачи','текущие'],['Планирование','очередь'],['Backlog','отложенное']]},
  {id:'intellect', title:'ИНТЕЛЛЕКТ', items:[
    ['Чат HELION','локальный ввод'],['История чата','одна SQLite'],['RAG','контекст'],
    ['Быстрые команды','prompt'],['Код / Prompt','режим'],['Глобальный поиск','Ctrl+K'],['Аналитика','сводка']]},
  {id:'knowledge', title:'ЗНАНИЯ', items:[
    ['Библиотека','источники'],['Документы','файлы'],['Чтение','очередь'],
    ['Источники','provenance'],['База знаний','chunks']]},
  {id:'creation', title:'ТВОРЧЕСТВО', items:[
    ['Кинотеатр','cinema'],['Творческая студия','wow'],['Веб-контент','браузер'],
    ['Сценарии','черновики'],['Аудио и видео','медиа']]},
  {id:'people', title:'ЛЮДИ', items:[
    ['Личности','5 персон'],['Выбор роли','CoreID'],['Карточки персон','паспорта'],
    ['8 CoreID','ядра'],['Настройки персонажей','ACL']]},
  {id:'evolution', title:'РАЗВИТИЕ', items:[
    ['Обучение','старт'],['Рост и развитие','self-learn'],['Обучение весов','GPU'],
    ['STOP / PAUSE','контроль'],['ECO / BALANCED / INTENSIVE','профиль'],['Лаборатория развития','sandbox']]},
  {id:'world', title:'МИР', items:[
    ['Веб-браузер','URL'],['Подключённые сервисы','коннекторы'],['Мессенджер','чат'],
    ['Почта','HOLD'],['Звонки','HOLD'],['Соцсети и игры','внешнее']]},
  {id:'system', title:'СИСТЕМА', items:[
    ['Настройки системы','DPI'],['Управление ПК','HOLD'],['Каталог моделей 24+','реестр'],
    ['Pull / Cancel / Retry','модели'],['Голосовое управление','HOLD'],['Автоматизация','задачи'],
    ['Безопасность','ACL'],['События v3','журнал'],['5 полос прогресса','прогресс']]},
];
const nav=document.getElementById('sections'), panel=document.getElementById('panel');
function sensors(){return{cpu:22+Math.round(Math.random()*35),gpu:8+Math.round(Math.random()*25),ram:41+Math.round(Math.random()*28)};}
function render(id){
  const s=SECTIONS.find(x=>x.id===id);
  [...nav.children].forEach(b=>b.classList.toggle('active', b.dataset.id===id));
  const m=sensors();
  panel.innerHTML=`<h2>${s.title}</h2>
    <div class="sensors">${[['CPU',m.cpu],['GPU',m.gpu],['RAM',m.ram]].map(([k,v])=>`
      <div class="card sensor"><h3>${k}</h3><div class="bar"><span style="width:${v}%"></span></div><div>${v}%</div></div>`).join('')}</div>
    <div class="grid">${s.items.map(([t,sub])=>`<button class="tile" data-item="${t}"><b>${t}</b><small>${sub}</small></button>`).join('')}</div>
    <p id="status" class="card">Выбери кнопку.</p>`;
  panel.querySelectorAll('.tile').forEach(btn=>btn.onclick=()=>runAction(s,btn));
}
function runAction(section, btn){
  const item=btn.dataset.item, status=document.getElementById('status');
  btn.dataset.state='RUNNING';
  if(item==='Чат HELION'){
    const q=prompt('Сообщение');
    status.textContent=q?('ЛОКАЛЬНЫЙ ЧАТ · '+q+' · нет Ollama'):'отменено';
    btn.dataset.state=q?'HOLD':''; return;
  }
  if(item==='Веб-браузер'||item==='Веб-контент'){
    const url=prompt('URL','https://ollama.com');
    if(url) window.open(url,'_blank','noopener');
    status.textContent=url?('открыто · '+url):'отменено';
    btn.dataset.state=url?'OK':''; return;
  }
  const hold=['Почта','Звонки','Голосовое управление','Управление ПК','Обучение весов','История чата','RAG','Каталог моделей 24+','Pull / Cancel / Retry','STOP / PAUSE','События v3'];
  if(hold.includes(item)){ status.textContent=item+' · HOLD · нужен Windows EXE'; btn.dataset.state='HOLD'; return; }
  status.textContent=section.title+' · '+item+' · OK'; btn.dataset.state='OK';
}
SECTIONS.forEach(s=>{const b=document.createElement('button'); b.textContent=s.title; b.dataset.id=s.id; b.onclick=()=>render(s.id); nav.appendChild(b);});
document.querySelectorAll('.dock button').forEach(b=>b.onclick=()=>render(b.dataset.go));
document.addEventListener('keydown',e=>{
  if(e.ctrlKey&&e.key.toLowerCase()==='k'){e.preventDefault();document.querySelector('.search').focus();}
  if(e.key==='F11'){e.preventDefault();document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen();}
  if(e.key==='Escape'&&document.fullscreenElement) document.exitFullscreen();
});
setInterval(()=>{document.getElementById('clock').textContent=new Date().toLocaleString('ru');},1000);
render('work');
