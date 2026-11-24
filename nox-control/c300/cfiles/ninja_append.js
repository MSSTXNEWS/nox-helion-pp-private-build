
/* NOX · команды пульта в палитре Ctrl+K (добавлено исполнителем C) */
(function () {
  const items = [
    ['cmd:stop', 'STOP: остановить ответ', 'stop', 'stop', {}],
    ['cmd:health', 'Состояние шлюза чата', 'health', 'health', {}],
    ['cmd:svc', 'Состояние сервисов', 'svc.status', 'svc', {}],
    ['cmd:snapshot', 'Снимок состояния системы', 'snapshot', 'снимок', {}],
    ['cmd:sleep', 'Усыпить NOX', 'sleep', 'сон', {}],
    ['cmd:wake', 'Разбудить NOX', 'wake', 'разбудить', {}],
    ['cmd:backup', 'Создать бэкап состояния', 'backup.create', 'бэкап', {}]
  ];
  const add = () => {
    if (!window.NOXNinja || !window.NOXNinja.el || !window.NOXNinja.el.data || !window.NOXcmd) return setTimeout(add, 300);
    const el = window.NOXNinja.el;
    el.data = (el.data || []).filter((x) => !String(x.id).startsWith('cmd:')).concat(items.map(([id, title, name, kw]) => ({ id, title, section: 'Пульт NOX', keywords: kw + ' ' + name, handler: () => window.NOXcmd(name, {}) })));
  };
  const load = document.createElement('script');
  load.src = 'nox-cmd.js';
  document.head.appendChild(load);
  add();
  // палитра сбрасывает data при очистке поиска: возвращаем команды после каждого изменения
  const hook = setInterval(() => { if (window.NOXNinja && window.NOXNinja.el) { window.NOXNinja.el.addEventListener('change', () => setTimeout(add, 0)); clearInterval(hook); } }, 300);
})();
