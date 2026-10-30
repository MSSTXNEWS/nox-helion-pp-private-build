// NOX CS5: subordinate screen inside existing R13 Creative Studio.
// Does not replace HOME, MENU, WPF, the installer or the existing model hub.
(() => {
  'use strict';
  if (document.getElementById('screen-five')) return;
  const nav = document.querySelector('nav.nav');
  const content = document.querySelector('.layout main.content');
  if (!nav || !content || typeof rpc !== 'function' || typeof navigate !== 'function') return;

  const tab = document.createElement('button');
  tab.type = 'button';
  tab.dataset.nav = 'five';
  tab.textContent = '◈ 5 блоков';
  tab.addEventListener('click', () => navigate('five'));
  nav.appendChild(tab);

  const screen = document.createElement('section');
  screen.id = 'screen-five';
  screen.className = 'screen';
  screen.innerHTML = \`
    <div class="panel">
      <h2>CREATIVE STUDIO · Единый проект, пять блоков</h2>
      <p class="muted">Внутри существующего NOX. Исследования и редактура — локальные записи;
      производство — исходный Creative Worker; модели — штатный ModelCenter;
      публикации и доходы без провайдерских квитанций не подтверждены.</p>
      <div class="formrow">
        <label>ProjectID <input id="cs5-project" value="creative01" maxlength="48" autocomplete="off"></label>
        <label>Блок
          <select id="cs5-block">
            <option value="B01">01 · Global Intelligence</option>
            <option value="B02">02 · Story / Editorial</option>
            <option value="B03">03 · Media / Cinema</option>
            <option value="B04">04 · Model / Training Lab</option>
            <option value="B05">05 · Brand / Revenue</option>
          </select>
        </label>
        <label>Тип записи <select id="cs5-kind"></select></label>
      </div>
      <label>Текст заметки, исходной идеи или проекта
        <textarea id="cs5-text" maxlength="3000" placeholder="Сохранить проверяемую идею / источник / решение редактора"></textarea>
      </label>
      <label>URL первоисточника (необязательно)
        <input id="cs5-source" maxlength="600" placeholder="https://..." autocomplete="off">
      </label>
      <div class="actions">
        <button class="action primary" type="button" id="cs5-save">Сохранить в проект</button>
        <button class="action" type="button" id="cs5-list">История и SHA</button>
        <button class="action" type="button" id="cs5-produce">Производство · существующий движок</button>
        <button class="action" type="button" id="cs5-models">Каталог моделей · P03</button>
      </div>
      <pre id="cs5-result" aria-live="polite">Проверка состояния...</pre>
    </div>\`;
  content.appendChild(screen);
  const byId = id => document.getElementById(id);
  const kinds = {
    B01: [['hypothesis','Гипотеза'],['research','Наблюдение с источником']],
    B02: [['idea','Идея/сон'],['bible','Библия мира'],['editorial','Редакторская версия']],
    B03: [['production','Производственный план'],['asset','Ассет / SHA']],
    B04: [['model_note','Выбор модели / лицензии']],
    B05: [['brand','Бренд'],['publication_draft','Черновик публикации'],
          ['revenue_scenario','Сценарий дохода'],['receipt','Внешняя квитанция (НЕ проверена)']]
  };
  const block = byId('cs5-block');
  const kind = byId('cs5-kind');
  function refreshKinds() {
    kind.replaceChildren();
    for (const [value,label] of kinds[block.value]) {
      const opt = document.createElement('option');
      opt.value = value; opt.textContent = label; kind.append(opt);
    }
  }
  block.addEventListener('change', refreshKinds); refreshKinds();
  function projectId() {
    const value = byId('cs5-project').value.trim();
    if (!/^[a-z0-9_-]{1,48}$/i.test(value)) throw Error('ProjectID: только 1–48 букв, цифр, _ или -');
    return value;
  }
  let loading = false;
  async function perform(action) {
    if (loading) return;
    loading = true;
    const display = byId('cs5-result');
    display.textContent = 'Запрос к существующему NOX Creative Worker...';
    try {
      const payload = {project_id: projectId()};
      if (action === 'cs5_append') {
        payload.block = block.value;
        payload.kind = kind.value;
        payload.text = byId('cs5-text').value;
        payload.source_url = byId('cs5-source').value.trim();
      }
      const result = await rpc(action, payload);
      display.textContent = JSON.stringify(result, null, 2);
    } catch(e) {
      display.textContent = 'HOLD / ERROR: ' + String(e && e.message || e);
    } finally {
      loading = false;
    }
  }
  byId('cs5-save').addEventListener('click', () => perform('cs5_append'));
  byId('cs5-list').addEventListener('click', () => perform('cs5_list'));
  byId('cs5-produce').addEventListener('click', () => navigate('create'));
  byId('cs5-models').addEventListener('click', () => navigate('models'));
  rpc('cs5_overview').then(r => {
    byId('cs5-result').textContent = JSON.stringify(r,null,2);
  }).catch(e => {
    byId('cs5-result').textContent = 'CONTRACT_REQUIRED: ' + String(e.message || e);
  });
})();
