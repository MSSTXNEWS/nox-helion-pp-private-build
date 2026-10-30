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
    return verifyConnection();
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
      <div id="cs5-cinema" class="cs5-cinema" data-cs5-scene="B01"
           aria-label="Контекст выбранного творческого сегмента">
        <div class="cs5-cinema-eyebrow">NOX HELION / CREATIVE STUDIO · SOURCE-ONLY</div>
        <div class="cs5-cinema-content">
          <div class="cs5-cinema-copy">
            <p id="cs5-cinema-kicker">ИССЛЕДОВАНИЕ</p>
            <h3 id="cs5-cinema-title">Исследовать мир</h3>
            <p id="cs5-cinema-detail">Проверяемые источники, наблюдения и оригинальные гипотезы.</p>
            <span class="cs5-cinema-state">ЛОКАЛЬНЫЕ ФУНКЦИИ · E11 HOLD</span>
          </div>
          <div class="cs5-cinema-object" aria-hidden="true"><span id="cs5-cinema-symbol">◈</span></div>
        </div>
      </div>
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
      <div class="panel" id="cs5-research-panel">
        <h3>Открытые исследовательские источники</h3>
        <div class="formrow">
          <label>API<select id="cs5-research-source"><option value="books">Google Books</option>
            <option value="openlibrary">Open Library</option><option value="apple">Apple Podcasts</option>
            <option value="crossref">Crossref</option><option value="worldbank">World Bank</option>
            <option value="wikimedia">Wikimedia Pageviews</option><option value="openalex">OpenAlex</option>
          </select></label>
          <label>Запрос<input id="cs5-research-query" maxlength="160" placeholder="Название / ES / es|España"></label>
        </div>
        <button class="action primary" id="cs5-research" type="button">Исследовать по запросу</button>
        <button class="action" id="cs5-research-all" type="button">МЕГА-ПОИСК · 4 открытых каталога</button>
        <div class="actions" aria-label="Управление результатами исследования">
          <button class="action" type="button" id="cs5-research-clear">Очистить результаты</button>
          <span id="cs5-research-count" class="muted" role="status">Источники ещё не запрошены</span>
        </div>
        <div class="grid" id="cs5-research-results" aria-live="polite"></div>
      </div>
      <div class="actions">
        <button class="action" type="button" id="cs5-status">Проверить подключение</button>
        <button class="action" type="button" id="cs5-export">Экспорт заметок / бренда (Markdown)</button>
        <button class="action primary" type="button" id="cs5-save">Сохранить в проект</button>
        <button class="action" type="button" id="cs5-list">История и SHA</button>
        <button class="action" type="button" id="cs5-older" disabled>Ранние записи</button>
        <button class="action" type="button" id="cs5-latest" disabled>Последние записи</button>
        <button class="action" type="button" id="cs5-produce">Производство · существующий движок</button>
        <button class="action" type="button" id="cs5-models">Каталог моделей · P03</button>
        <button class="action primary" type="button" id="cs5-pipeline">МЕГА-СБОРКА · Сценарий → Звук → Файлы</button>
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
  const cinemaScenes = Object.freeze({
    B01:['ИССЛЕДОВАНИЕ','Исследовать мир','Первоисточники, гипотезы и сравнительные наблюдения.','◈'],
    B02:['ИСТОРИИ','Создавать вселенные','Оригинальные идеи, сценарии, библии миров и редакторские версии.','✧'],
    B03:['МЕДИА','Производить кино','Музыка, фильмы, 2D/3D и раскадровки через действующие движки.','▣'],
    B04:['МОДЕЛИ','Лаборатория ИИ','Официальный каталог, лицензии, проверки весов и ModelCenter.','◇'],
    B05:['БРЕНДЫ','Создавать бренды','Публикационные проекты и доход только с настоящими квитанциями.','◆']
  });
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
    const scene = cinemaScenes[block.value];
    const stage = byId('cs5-cinema');
    if (stage && scene) {
      stage.dataset.cs5Scene = block.value;
      byId('cs5-cinema-kicker').textContent = scene[0];
      byId('cs5-cinema-title').textContent = scene[1];
      byId('cs5-cinema-detail').textContent = scene[2];
      byId('cs5-cinema-symbol').textContent = scene[3];
    }
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
      if (typeof item.source_url === 'string') {
        try {
          const verified = new URL(item.source_url);
          if (['http:', 'https:'].includes(verified.protocol) &&
              verified.hostname && !verified.username && !verified.password) {
            const source = document.createElement('a');
            source.href = verified.href;
            source.target = '_blank';
            source.rel = 'noopener noreferrer';
            source.textContent = 'Открыть первоисточник';
            card.append(source);
          }
        } catch {
          // Never turn malformed/untrusted stored metadata into a clickable URL.
        }
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
    return verifyConnection();
  });
  byId('cs5-export').addEventListener('click', () => perform('cs5_export'));
  const researchState = {generation:0,records:[],busy:false};
  function sourceLink(raw) {
    if (typeof raw !== 'string' || raw.length > 600 || /[\\x00-\\x1f]/.test(raw)) return '';
    try {
      const value = new URL(raw);
      if (!['https:','http:'].includes(value.protocol) || !value.hostname ||
          value.username || value.password) return '';
      return value.href;
    } catch {return '';}
  }
  function stageResearchItem(item, source) {
    const record = {
      provider:source,
      title:String(item.title || 'Без названия').slice(0,200),
      detail:String(item.detail || '').slice(0,500),
      url:sourceLink(item.source_url)
    };
    const text = [record.title,record.detail,'Источник: '+record.provider].filter(Boolean).join(' · ').slice(0,3000);
    return {record,text};
  }
  function showResearchRecord(item, source, generation) {
    if (generation !== researchState.generation) return;
    const {record,text} = stageResearchItem(item,source);
    researchState.records.push(record);
    const card = document.createElement('article');
    card.className = 'model';
    const title = document.createElement('h3');title.textContent = record.title;
    const detail = document.createElement('p');detail.textContent = record.detail;
    const metadata = document.createElement('small');
    metadata.textContent = source + ' · публичные метаданные, не фактчек и не продажи';
    const adopt = document.createElement('button');
    adopt.type='button';adopt.className='action';
    adopt.textContent='В проект · подготовить запись';
    adopt.addEventListener('click',()=>{
      byId('cs5-text').value=text;
      byId('cs5-source').value=record.url;
      block.value='B01';
      refreshKinds();
      kind.value='research';
      byId('cs5-result').textContent='Материал подготовлен в B01. Проверь его и нажми «Сохранить в проект». Автосохранения нет.';
      byId('cs5-text').focus();
    });
    card.append(title,detail,metadata,adopt);
    if(record.url) {
      const link=document.createElement('a');
      link.href=record.url;link.target='_blank';link.rel='noopener noreferrer';
      link.textContent='Первоисточник';card.append(link);
    }
    byId('cs5-research-results').append(card);
    byId('cs5-research-count').textContent=researchState.records.length+' записей из открытых каталогов';
  }
  byId('cs5-research-clear').addEventListener('click',()=>{
    researchState.generation++;
    researchState.records=[];
    byId('cs5-research-results').replaceChildren();
    byId('cs5-research-count').textContent='Результаты очищены';
  });
  byId('cs5-research').addEventListener('click', async () => {
    const dest = byId('cs5-research-results');
    if (researchState.busy) return;
    dest.replaceChildren();
    researchState.records=[];
    const generation=++researchState.generation;
    const source = byId('cs5-research-source').value;
    const query = byId('cs5-research-query').value.trim();
    if (!query || query.length > 160) {
      byId('cs5-result').textContent = 'Нужен запрос от 1 до 160 символов';
      return;
    }
    researchState.busy=true;
    let result;
    try {
      result=await task('cs5_research',{source,query,project_id:projectId()},'cs5-result');
    } catch(e) {
      byId('cs5-result').textContent='HOLD: '+String(e?.message || e);
      return;
    } finally {researchState.busy=false;}
    if(generation!==researchState.generation || !result || !Array.isArray(result.items)) return;
    for (const item of result.items) showResearchRecord(item,source,generation);
  });
  byId('cs5-research-all').addEventListener('click', async () => {
    if (loading || researchState.busy) return;
    researchState.busy=true;
    const query = byId('cs5-research-query').value.trim();
    if (!query || query.length > 160) {
      byId('cs5-result').textContent = 'Нужен запрос длиной 1–160 символов';
      researchState.busy=false;
      return;
    }
    const id = projectId();
    const sources = ['books','openlibrary','crossref','openalex'];
    const dest = byId('cs5-research-results');
    dest.replaceChildren();
    researchState.records=[];
    const generation=++researchState.generation;
    const results = [];
    const button = byId('cs5-research-all');
    button.disabled = true;
    try {
      for (const source of sources) {
        byId('cs5-result').textContent = 'Открытые каталоги: ' +
          (results.length + 1) + '/4 · ' + source;
        try {
          const result = await task('cs5_research',
            {source,query,project_id:id},'cs5-result');
          if (!result || !Array.isArray(result.items)) {
            results.push(source + ': результат не подтверждён');
            continue;
          }
          results.push(source + ': ' + result.items.length + ' записей');
          for (const item of result.items) showResearchRecord(item,source,generation);
        } catch (e) {
          results.push(source + ': HOLD · ' + String(e?.message || e));
        }
      }
      byId('cs5-result').textContent = 'МЕГА-ПОИСК · результат по источникам:\n' +
        results.join('\n') + '\nПоказатели не являются продажами или проверенными фактами.';
    } finally {
      button.disabled = false;
      researchState.busy = false;
    }
  });
  byId('cs5-save').addEventListener('click', () => perform('cs5_append'));
  byId('cs5-list').addEventListener('click', () => perform('cs5_list'));
  byId('cs5-older').addEventListener('click', () => {
    if (previousBefore !== null) return perform('cs5_list', previousBefore);
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
  // Reuse the real owner task dispatcher; never create a second media engine.
  // Each stage is explicitly requested by the user, no unattended scheduling.
  let pipelineBusy = false;
  let pipelineCancelled = false;
  const pipelineButton = byId('cs5-pipeline');
  const originalStop = byId('stop');
  const cancelPipeline = () => { pipelineCancelled = true; };
  originalStop?.addEventListener('click', cancelPipeline);
  pipelineButton.addEventListener('click', async () => {
    if (pipelineBusy || loading) return;
    const output = byId('cs5-result');
    let id, prompt;
    try {
      id = projectId();
      prompt = byId('cs5-text').value.trim();
      if (prompt.length < 4 || prompt.length > 3000) {
        throw Error('Нужно описание проекта длиной 4–3000 символов');
      }
    } catch (error) {
      output.textContent = 'HOLD: ' + String(error.message || error);
      return;
    }
    pipelineBusy = true;
    pipelineCancelled = false;
    pipelineButton.disabled = true;
    const stages = [
      {name:'Сценарий и раскадровка',action:'storyboard',
       payload:{project_id:id,prompt,kind:'movie',scenes:3}},
      {name:'Музыкальный план',action:'create_text',
       payload:{project_id:id,prompt,kind:'sound'}},
      {name:'Реестр файлов проекта',action:'project_files',
       payload:{project_id:id}}
    ];
    const evidence = [];
    try {
      for (const stage of stages) {
        if (pipelineCancelled) throw Error('CS5_PIPELINE_STOP_REQUESTED');
        output.textContent = 'Выполнение ' + stage.name + ' (' +
          (evidence.length+1) + '/3). Штатный STOP доступен.\n' +
          evidence.join('\n');
        const result = await task(stage.action, stage.payload, 'cs5-result');
        if (pipelineCancelled) throw Error('CS5_PIPELINE_STOP_REQUESTED');
        if (!result || result.error || result.ok === false ||
            ['ERROR','FAILED','HOLD','CANCELLED','STOPPED'].includes(
              String(result.status || '').toUpperCase())) {
          throw Error('Шаг не принят штатным Worker: '+stage.name+' · '+
            JSON.stringify(result ?? null).slice(0,500));
        }
        // QUEUED/ACCEPTED means submitted, not that an output artifact exists.
        evidence.push(stage.name + ': ' +
          String(result.status || 'ANSWER_RECEIVED_UNVERIFIED'));
      }
      output.textContent = 'Мегамаршрут передан штатным движкам.\n' +
        evidence.join('\n') +
        '\nПроверь фактические файлы и задания: это не подтверждение созданного фильма.';
    } catch (error) {
      output.textContent = 'Мегамаршрут остановлен / HOLD после '+
        evidence.length + ' шагов.\n'+evidence.join('\n')+'\n'+
        String(error.message || error);
    } finally {
      pipelineBusy = false;
      pipelineButton.disabled = false;
    }
  });
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
