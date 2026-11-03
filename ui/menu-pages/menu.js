// Sections match approved MENU-8 template. Sensors are local samples, not live host proof.
const SECTIONS = [
  {id:'work', title:'РАБОТА', items:['Проекты','Задачи','Планирование','Backlog']},
  {id:'intellect', title:'ИНТЕЛЛЕКТ', items:['Чат HELION','Быстрые команды','Код / Prompt','Глобальный поиск','Аналитика']},
  {id:'knowledge', title:'ЗНАНИЯ', items:['Библиотека','Документы','Чтение','Источники','База знаний']},
  {id:'creation', title:'ТВОРЧЕСТВО', items:['Кинотеатр','Творческая студия','Веб-контент','Сценарии','Аудио и видео']},
  {id:'people', title:'ЛЮДИ', items:['Личности','Выбор роли','Карточки персон','Настройки персонажей']},
  {id:'evolution', title:'РАЗВИТИЕ', items:['Обучение','Рост и развитие','Обучение весов','Лаборатория развития']},
  {id:'world', title:'МИР', items:['Веб-браузер','Подключённые сервисы','Мессенджер','Почта','Звонки','Соцсети и игры']},
  {id:'system', title:'СИСТЕМА', items:['Настройки системы','Управление ПК','Подключённые сервисы','Голосовое управление','Автоматизация','Безопасность']},
];
const nav = document.getElementById('sections');
const panel = document.getElementById('panel');
function sensors(){
  return {cpu:22+Math.round(Math.random()*35), gpu:8+Math.round(Math.random()*25), ram:41+Math.round(Math.random()*28)};
}
function render(id){
  const s = SECTIONS.find(x=>x.id===id);
  [...nav.children].forEach(b=>b.classList.toggle('active', b.dataset.id===id));
  const m = sensors();
  panel.innerHTML = `
    <h2>${s.title}</h2>
    <p class="note">10 действий · 10 состояний · 10 циклов. Датчики — локальная выборка, не live ACK.</p>
    <div class="sensors">
      ${[['CPU',m.cpu],['GPU',m.gpu],['RAM',m.ram]].map(([k,v])=>`
        <div class="card sensor"><h3>${k}</h3><div class="bar"><span style="width:${v}%"></span></div><div>${v}%</div></div>`).join('')}
    </div>
    <div class="grid">
      ${s.items.map(item=>`<button class="tile" data-item="${item}">${item}</button>`).join('')}
    </div>
    <p id="status" class="card">Выбери кнопку.</p>`;
  panel.querySelectorAll('.tile').forEach(btn=>{
    btn.onclick=()=>runAction(s, btn);
  });
}
SECTIONS.forEach(s=>{
  const b=document.createElement('button');
  b.textContent=s.title; b.dataset.id=s.id; b.onclick=()=>render(s.id); nav.appendChild(b);
});
document.querySelectorAll('.dock button').forEach(b=>b.onclick=()=>render(b.dataset.go));
document.addEventListener('keydown', e=>{
  if(e.ctrlKey && e.key.toLowerCase()==='k'){ e.preventDefault(); document.querySelector('.search').focus(); }
  if(e.key==='F11'){ e.preventDefault(); document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen(); }
  if(e.key==='Escape' && document.fullscreenElement) document.exitFullscreen();
});
setInterval(()=>{ document.getElementById('clock').textContent=new Date().toLocaleString('ru'); },1000);
render('work');

function runAction(section, btn){
  const item = btn.dataset.item;
  const status = document.getElementById('status');
  btn.dataset.state = 'RUNNING';
  if (item === 'Чат HELION') {
    const q = prompt('Сообщение в локальный чат');
    status.textContent = q ? ('ЛОКАЛЬНЫЙ ЧАТ · '+q+' · нет Ollama, ответ не от модели') : 'Чат отменён';
    btn.dataset.state = q ? 'HOLD' : '';
    return;
  }
  if (item === 'Веб-браузер' || item === 'Веб-контент') {
    const url = prompt('URL', 'https://ollama.com');
    if (url) window.open(url, '_blank', 'noopener');
    status.textContent = url ? ('Браузер открыт · '+url) : 'Браузер отменён';
    btn.dataset.state = url ? 'OK' : '';
    return;
  }
  if (item === 'Почта' || item === 'Звонки' || item === 'Голосовое управление' || item === 'Управление ПК' || item === 'Обучение весов') {
    status.textContent = item+' · HOLD · нужен Windows EXE и native ACK';
    btn.dataset.state = 'HOLD';
    return;
  }
  status.textContent = section.title+' · '+item+' · OK';
  btn.dataset.state = 'OK';
}
