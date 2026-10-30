// NOX CS5: subordinate screen inside existing R13 Creative Studio.
// Does not replace HOME, MENU, WPF, the installer or the existing model hub.
(() => {
  'use strict';
  if (document.getElementById('screen-five')) return;
  const nav = document.querySelector('nav.nav');
  const content = document.querySelector('.layout main.content');
  if (!nav || !content || typeof rpc !== 'function' || typeof navigate !== 'function') return;

  let previousStudioScreen = 'create';
  const allowedReturnScreens = new Set(['create','models','jobs','theater','immersive','about']);
  const tab = document.createElement('button');
  tab.type = 'button';
  tab.dataset.nav = 'five';
  tab.textContent = '◈ 5 блоков';
  tab.addEventListener('click', () => {
    const activeId = document.querySelector('.screen.active')?.id || '';
    const candidate = activeId.startsWith('screen-') ? activeId.slice(7) : '';
    if (allowedReturnScreens.has(candidate)) previousStudioScreen = candidate;
    // Preserve the selected NOX Creative project instead of inventing a second one.
    const originalProject = document.getElementById('project')?.value.trim();
    const selected = document.getElementById('cs5-project');
    if (originalProject && /^[a-z0-9_-]{1,48}$/i.test(originalProject) && selected) {
      selected.value = originalProject;
    }
    navigate('five');
    verifyConnection();
  });
  nav.appendChild(tab);

  const screen = document.createElement('section');
  screen.id = 'screen-five';
  screen.className = 'screen';
  screen.innerHTML = `
    <div class="panel">
      <nav aria-label="Путь раздела" class="actions">
        <button type="button" class="action" id="cs5-back">← Назад в творчество</button>
        <span class="muted">NOX / ТВОРЧЕСТВО / 5 блоков</span>
      </nav>
      <h2>CREATIVE STUDIO · Единый проект, пять блоков</h2>
      <div id="cs5-segments" class="actions" role="group" aria-label="Пять сегментов Creative Studio"></div>
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
        <button class="action" type="button" id="cs5-status">Проверить подключение</button>
        <button class="action primary" type="button" id="cs5-save">Сохранить в проект</button>
        <button class="action" type="button" id="cs5-list">История и SHA</button>
        <button class="action" type="button" id="cs5-older" disabled>Ранние записи</button>
        <button class="action" type="button" id="cs5-latest" disabled>Последние записи</button>
        <button class="action" type="button" id="cs5-produce">Производство · существующий движок</button>
        <button class="action" type="button" id="cs5-models">Каталог моделей · P03</button>
        <button class="action" type="button" id="cs5-storyboard">Создать раскадровку через Ollama</button>
        <button class="action" type="button" id="cs5-music">Создать музыкальный план</button>
        <button class="action" type="button" id="cs5-files">Реальные файлы проекта</button>
        <button class="action" type="button" id="cs5-stop">STOP · штатная команда</button>
      </div>
      <pre id="cs5-result" aria-live="polite">Для проверки подключения открой вкладку или нажми кнопку.</pre>
      <div id="cs5-history" class="grid" aria-live="polite"></div>
    </div>`;
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
  const segments = byId('cs5-segments');
  const segmentLabels = {
    B01: 'Исследование', B02: 'Истории', B03: 'Медиа',
    B04: 'Модели', B05: 'Бренды'
  };
  for (const [key, name] of Object.entries(segmentLabels)) {
    const control = document.createElement('button');
    control.type = 'button';
    control.className = 'action';
    control.textContent = name;
    control.dataset.cs5Segment = key;
    control.setAttribute('aria-pressed', key === block.value ? 'true' : 'false');
    control.addEventListener('click', () => {
      block.value = key;
      refreshKinds();
    });
    segments.appendChild(control);
  }
  function refreshKinds() {
    for (const button of segments.children) {
      button.setAttribute('aria-pressed', button.dataset.cs5Segment === block.value ? 'true' : 'false');
    }
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
    // The original studio and the five-block panel share the same logical ProjectID.
    const originalProject = byId('project');
    if (originalProject) originalProject.value = value;
    return value;
  }
  let loading = false;
  let overviewInFlight = false;
  let overviewReady = false;
  async function verifyConnection() {
    if (overviewInFlight || overviewReady) return;
    overviewInFlight = true;
    const out = byId('cs5-result');
    out.textContent = 'Проверка штатного Creative Worker…';
    try {
      const result = await rpc('cs5_overview');
      overviewReady = true;
      out.textContent = JSON.stringify(result, null, 2);
    } catch (error) {
      out.textContent = 'CONTRACT_REQUIRED: ' + String(error?.message || error);
    } finally {
      overviewInFlight = false;
    }
  }
  let previousBefore = null;
  function renderHistory(result) {
    const destination = byId('cs5-history');
    destination.replaceChildren();
    for (const item of result.events || []) {
      const card = document.createElement('article');
      card.className = 'model'; // Original NOX Studio card material.
      const heading = document.createElement('h3');
      heading.textContent = (item.block || '') + ' · ' + (item.kind || '');
      const description = document.createElement('p');
      description.textContent = item.text || '';
      const provenance = document.createElement('small');
      provenance.textContent = (item.created_at_utc || 'Время не указано') +
        ' · ' + (item.evidence_status || 'UNKNOWN') +
        ' · SHA-256 ' + (item.sha256 || 'НЕТ ДАННЫХ');
      card.append(heading, description, provenance);
      if (item.source_url) {
        const source = document.createElement('a');
        source.href = item.source_url;
        source.target = '_blank';
        source.rel = 'noopener noreferrer';
        source.textContent = 'Открыть первоисточник';
        card.append(source);
      }
      destination.append(card);
    }
  }
  function updateHistoryControls(result, before) {
    previousBefore = result.next_before;
    byId('cs5-older').disabled = result.next_before === null;
    byId('cs5-latest').disabled = before === null;
  }
  async function perform(action, before = null) {
    if (loading) return;
    loading = true;
    const display = byId('cs5-result');
    display.textContent = 'Запрос к существующему NOX Creative Worker...';
    try {
      const payload = {project_id: projectId()};
      if (action === 'cs5_list' && before !== null) payload.before = before;
      if (action === 'cs5_append') {
        payload.block = block.value;
        payload.kind = kind.value;
        payload.text = byId('cs5-text').value;
        payload.source_url = byId('cs5-source').value.trim();
      }
      const result = await rpc(action, payload);
      if (action === 'cs5_list') {
        updateHistoryControls(result, before);
        renderHistory(result);
      } else if (action === 'cs5_append') {
        byId('cs5-history').replaceChildren();
        previousBefore = null;
        byId('cs5-older').disabled = true;
        byId('cs5-latest').disabled = true;
      }
      display.textContent = action === 'cs5_list'
        ? 'История проекта: всего ' + result.count + ' · показано ' + result.showing
        : JSON.stringify(result, null, 2);
    } catch(e) {
      display.textContent = 'HOLD / ERROR: ' + String(e && e.message || e);
    } finally {
      loading = false;
    }
  }
  byId('cs5-status').addEventListener('click', () => {
    overviewReady = false;
    verifyConnection();
  });
  byId('cs5-save').addEventListener('click', () => perform('cs5_append'));
  byId('cs5-list').addEventListener('click', () => perform('cs5_list'));
  byId('cs5-older').addEventListener('click', () => {
    if (previousBefore !== null) perform('cs5_list', previousBefore);
  });
  byId('cs5-latest').addEventListener('click', () => perform('cs5_list'));
  function handoffToOriginal(kind) {
    const target = byId('project');
    if (target) target.value = projectId();
    const originalPrompt = byId('prompt');
    if (originalPrompt && byId('cs5-text').value.trim()) originalPrompt.value = byId('cs5-text').value.trim();
    if (kind === 'models') navigate('models');
    else { navigate('create'); originalPrompt?.focus(); }
  }
  async function executeExisting(action, extras) {
    if (loading) return;
    try {
      const project_id = projectId();
      const prompt = byId('cs5-text').value.trim();
      if (action !== 'project_files' && prompt.length < 4) {
        throw Error('Сначала введи описание задачи (минимум 4 символа)');
      }
      const payload = { project_id, ...extras, ...(action === 'project_files' ? {} : {prompt}) };
      if (action === 'create_text') {payload.kind = 'sound';}
      // The original studio task() owns busy, status, RPC and provider error handling.
      await task(action, payload, 'cs5-result');
    } catch (e) {
      byId('cs5-result').textContent = 'HOLD / ERROR: ' + String(e?.message || e);
    }
  }
  byId('cs5-back').addEventListener('click', () => navigate(previousStudioScreen));
  byId('cs5-produce').addEventListener('click', () => handoffToOriginal('create'));
  byId('cs5-models').addEventListener('click', () => handoffToOriginal('models'));
  byId('cs5-storyboard').addEventListener('click', () =>
    executeExisting('storyboard', {kind:'movie', scenes:3}));
  byId('cs5-music').addEventListener('click', () => executeExisting('create_text', {}));
  byId('cs5-files').addEventListener('click', () => executeExisting('project_files', {}));
  byId('cs5-stop').addEventListener('click', () => byId('stop')?.click());
  // No Worker is started during page initialization; explicit action only.
})();
