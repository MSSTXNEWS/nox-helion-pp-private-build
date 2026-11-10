/* NOX MEGA-B R70: in-world MENU V2 subsections only; no new host or renderer.
 * UI visibility and source provenance are not native handler or E07 acceptance.
 */
const allowedRoutes = new Set(['chat', 'core-status', 'model-library']);
const worldIds = [
  'work','intelligence','knowledge','learning','entertainment',
  'people','creative','business','world','pc'
];
const specCounts = [18,18,18,22,33,13,14,15,15,27];
const expectedSource = Object.freeze({
  driveFileId: '1Ep0HKp-XZzN62mQ2IoNt9xXnOOi7rJGE',
  sha256: '4f311d1ca2d7c28fd54144cafe4747e94c9c83e74e4fa552dcda863ca11bbca4'
});
export function validateMenuV2(catalogue, originalWorlds) {
  if (!catalogue || catalogue.schema !== 'NOX-MENU-V2-193-EXACT-OWNER-SPEC-V1' ||
      catalogue.entry_count !== 193 || catalogue.world_count !== 10 ||
      catalogue.release_accepted !== false ||
      catalogue.source?.drive_file_id !== expectedSource.driveFileId ||
      catalogue.source?.sha256 !== expectedSource.sha256 ||
      catalogue.historical_route_ids_preserved_separately !== 54 ||
      catalogue.separate_eight_core_ids !== true ||
      !Array.isArray(catalogue.worlds) || catalogue.worlds.length !== 10 ||
      !Array.isArray(originalWorlds) || originalWorlds.length !== 10) {
    throw new Error('NOX_MENU_V2_ADMISSION_HOLD');
  }
  const used = new Set();
  let actual = 0;
  for (let i=0; i<10; i++) {
    const section = catalogue.worlds[i];
    if (section.id !== worldIds[i] || section.id !== originalWorlds[i].id ||
        !Array.isArray(section.items) || section.items.length !== specCounts[i]) {
      throw new Error('NOX_MENU_V2_OWNER_WORLD_ORDER_HOLD');
    }
    for (let j=0; j<section.items.length; j++) {
      const item = section.items[j];
      const expectedId = `MV2-${String(i+1).padStart(2,'0')}-${String(j+1).padStart(3,'0')}`;
      if (item.id !== expectedId || used.has(item.id) ||
          typeof item.label !== 'string' || !item.label || item.label.length > 180 ||
          !(item.group === null || (typeof item.group === 'string' && item.group.length <= 120)) ||
          (item.native_route !== null && !allowedRoutes.has(item.native_route)) ||
          item.handler_status === 'E07_ACCEPTED') {
        throw new Error('NOX_MENU_V2_HANDLER_SCOPE_HOLD');
      }
      if ((item.native_route === null && item.handler_status !== 'UNVERIFIED_HANDLER_HOLD') ||
          (item.native_route !== null && item.handler_status !== 'EXISTING_NAVIGATION_CANDIDATE_NOT_E07')) {
        throw new Error('NOX_MENU_V2_UNVERIFIED_ROUTE_MISLABELED_HOLD');
      }
      used.add(item.id);
      actual++;
    }
  }
  if (actual !== 193 || used.size !== 193) throw new Error('NOX_MENU_V2_ID_COUNT_HOLD');
  return Object.freeze(catalogue);
}

const el = (tag, text, cls) => {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
};

/* Reuse V27's proven navigation pattern in the EXISTING R58 asteroid world.
 * All 193 submenu entries are clickable NAVIGATION, not fake native actions.
 * Only the original trusted callback can wire an actual backend/route.
 */
export function appendMenuV2(controls, world, catalogue, createOwnerRouteButton) {
  if (!controls || !world || !catalogue || typeof createOwnerRouteButton !== 'function') {
    throw new Error('NOX_MENU_V2_NATIVE_ROUTE_OWNER_REQUIRED');
  }
  const section = catalogue.worlds.find(w => w.id === world.id);
  if (!section) throw new Error('NOX_MENU_V2_WORLD_NOT_FOUND');

  // Static in-world screen, not a disclosure/dropdown. The approved asteroid
  // selects the world; every subsection stays available as a visible button.
  const details = el('section', undefined, 'mega814-v2-section');
  details.setAttribute('aria-label', section.title + ' · MENU V2');
  const heading = el('h3', section.title + ' · ' + section.items.length + ' ПОДРАЗДЕЛОВ',
    'mega814-v2-section-title');
  const search = el('input', undefined, 'mega814-v2-search');
  search.type = 'search';
  search.placeholder = 'Поиск подраздела';
  search.setAttribute('aria-label', 'Поиск подраздела выбранного мира');
  const list = el('div', undefined, 'mega814-v2-subitems');
  list.setAttribute('role', 'group');
  list.setAttribute('aria-label', 'Все подразделы мира ' + section.title);
  const feature = el('section', undefined, 'mega814-v2-feature');
  feature.hidden = true;
  feature.setAttribute('aria-live', 'polite');
  const title = el('h3', undefined, 'mega814-v2-feature-title');
  const status = el('p', undefined, 'mega814-v2-feature-status');
  const back = el('button', '← К подразделам', 'mega814-button mega814-v2-back');
  back.type = 'button';
  const ownerMount = el('div', undefined, 'mega814-v2-owner-action');

  function closeFeature() {
    feature.hidden = true;
    list.hidden = false;
    search.hidden = false;
    back.setAttribute('aria-expanded', 'false');
    if (typeof search.focus === 'function') search.focus();
  }
  back.addEventListener('click', closeFeature);
  feature.append(title, status, back, ownerMount);

  const rows = [];
  for (const item of section.items) {
    const row = el('div', undefined, 'mega814-v2-subitem');
    const route = item.native_route;
    const button = el('button', item.label, 'mega814-button mega814-v2-navbutton');
    button.type = 'button';
    button.dataset.menuV2Id = item.id;
    button.setAttribute('aria-label', 'Открыть подраздел: ' + item.label);
    button.addEventListener('click', () => {
      title.textContent = item.label;
      ownerMount.replaceChildren();
      if (route) {
        try {
          const ownerAction = createOwnerRouteButton(route, item.label, null, world);
          if (!ownerAction) throw new Error('NOX_MENU_V2_NATIVE_OWNER_CALLBACK_HOLD');
          ownerMount.append(ownerAction);
          status.textContent = 'Существующий экран доступен · функция и права проверяются отдельно; E07 HOLD.';
        } catch {
          status.textContent = 'HOLD · прямой native обработчик недоступен; AI-помощник остаётся отдельным действием.';
        }
      } else {
        status.textContent = 'Прямой исполнитель не подтверждён · можно поручить NOX разобрать задачу и определить доступный безопасный способ.';
      }
      try {
        const parentNavigation = createOwnerRouteButton(
          'nox.parent-navigation', 'ОТКРЫТЬ РОДИТЕЛЬСКИЙ РАЗДЕЛ', null, world
        );
        if (parentNavigation) ownerMount.append(parentNavigation);
      } catch {
        status.textContent += ' · исходный родительский раздел недоступен.';
      }
      // Every catalog item gets an explicit route through the EXISTING AI pipe.
      // The response confirms only that AI replied; it does not prove the requested
      // operational task was executed.
      try {
        const prompt = {
          text: ('В разделе «' + section.title + '» помоги с пунктом «' + item.label +
            '». Используй только реально доступные разрешённые функции. Если прямое действие недоступно, ' +
            'объясни ограничение и предложи следующий безопасный шаг. Не утверждай, что действие выполнено без подтверждения.')
            .slice(0, 720)
        };
        const ask = createOwnerRouteButton('helion.chat', 'СПРОСИТЬ NOX', prompt);
        if (!ask) throw new Error('NOX_MENU_V2_AI_ROUTE_UNAVAILABLE');
        ownerMount.append(ask);
      } catch {
        status.textContent += ' · AI-канал пока недоступен.';
      }
      list.hidden = true;
      search.hidden = true;
      feature.hidden = false;
      back.setAttribute('aria-expanded', 'true');
      if (typeof back.focus === 'function') back.focus();
    });
    row.append(button, el('small', route ?
      'Навигация готова · существующий обработчик проверяется отдельно' :
      'Навигация готова · native функция HOLD'));
    list.append(row);
    rows.push({item, row});
  }

  search.addEventListener('input', () => {
    const term = String(search.value || '').toLocaleLowerCase();
    for (const {item,row} of rows) {
      const haystack = (item.label + ' ' + (item.group || '')).toLocaleLowerCase();
      row.hidden = !haystack.includes(term);
    }
  });
  details.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !feature.hidden) {
      event.preventDefault?.();
      event.stopPropagation?.();
      closeFeature();
    } else if ((event.ctrlKey || event.metaKey) && String(event.key).toLowerCase() === 'k') {
      event.preventDefault?.();
      event.stopPropagation?.();
      if (typeof search.focus === 'function') search.focus();
    }
  });
  details.append(heading, search, list, feature);
  controls.append(details);
  return details;
}
