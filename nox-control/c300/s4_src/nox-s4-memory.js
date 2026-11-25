/* S4 · Память: честная проверка сервера памяти + граф знаний в раскладке Obsidian (Cytoscape) по реальному индексу поиска /search. */
(function () {
  const of = window.fetch; let down = null;
  const probe = () => down || (down = of('/memory/health', { cache: 'no-store' }).then((r) => r.json()).then((j) => !!(j && (j.engine || /silero/i.test(JSON.stringify(j))))).catch(() => false));
  window.fetch = function (u, o) {
    if (o && o.method === 'POST' && /\/memory\/api$/.test(String(u))) return probe().then((bad) => bad ? new Response(JSON.stringify({ ok: false, up: false, error: 'сервер памяти не развёрнут' }), { status: 200, headers: { 'Content-Type': 'application/json' } }) : of.call(window, u, o));
    return of.call(window, u, o);
  };
  document.addEventListener('DOMContentLoaded', async () => {
    const wrap = document.querySelector('.wrap'), ph = wrap && wrap.querySelector('.ph'); if (!wrap || !window.cytoscape) return;
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const bad = await probe();
    const sec = document.createElement('section'); sec.className = 'card s4mg';
    sec.innerHTML = (bad ? '<div class="s4mb">Сервер памяти не развёрнут: факты и журнал правок недоступны. Ниже граф по индексу поиска NOX.</div>' : '')
      + '<h2>Граф знаний <span class="r mono" id="s4gi">…</span></h2><form class="s4mq" id="s4mf"><input type="search" id="s4mqi" placeholder="Что искать: страница, файл, запись" value="nox" maxlength="120" autocomplete="off"><sl-button size="medium" variant="primary" id="s4mgo"><sl-icon slot="prefix" library="tabler" name="search"></sl-icon>Найти</sl-button><sl-button size="medium" id="s4mfit"><sl-icon slot="prefix" library="tabler" name="focus-centered"></sl-icon>Вписать</sl-button></form>'
      + '<div class="s4mw"><div id="s4cy"></div><aside id="s4mi" class="s4mn muted">Нажмите на узел: двойной клик ищет по его названию, клик по ссылке открывает.</aside></div>';
    ph ? ph.after(sec) : wrap.prepend(sec);
    const COL = ['#e0654a', '#d9a441', '#6aa9d8', '#8fc28a', '#b48ad8', '#d68aa6', '#9a8f88'];
    const cy = cytoscape({ container: sec.querySelector('#s4cy'), elements: [], wheelSensitivity: .25, minZoom: .2, maxZoom: 3,
      style: [{ selector: 'node', style: { 'background-color': 'data(c)', width: 'data(s)', height: 'data(s)', label: 'data(l)', color: '#cfc4bd', 'font-size': 9, 'text-opacity': .0, 'text-valign': 'bottom', 'text-margin-y': 3, 'border-width': 0 } },
        { selector: 'node.hub', style: { 'text-opacity': .9, 'font-size': 11 } }, { selector: 'node:selected,node.hov', style: { 'text-opacity': 1, 'border-width': 2, 'border-color': '#fff' } },
        { selector: 'edge', style: { width: 1, 'line-color': 'rgba(255,235,220,.18)', 'curve-style': 'haystack' } }, { selector: '.dim', style: { opacity: .12 } }] });
    const kinds = {}; const kc = (k) => (kinds[k] = kinds[k] || COL[Object.keys(kinds).length % 7]);
    async function load(q, keep) {
      sec.querySelector('#s4gi').textContent = 'поиск…';
      let hits = []; try { const j = await (await of('/search?q=' + encodeURIComponent(q), { cache: 'no-store' })).json(); hits = (j.hits || []).slice(0, 60); } catch (e) { /* */ }
      if (!keep) cy.elements().remove();
      const qid = 'q:' + q; if (!cy.getElementById(qid).length) cy.add({ data: { id: qid, l: q, c: '#fff', s: 22 }, classes: 'hub' });
      hits.forEach((h, i) => { const k = h.kind || 'запись', kid = 'k:' + k, id = 'h:' + (h.url || h.title) + i;
        if (!cy.getElementById(kid).length) { cy.add({ data: { id: kid, l: k, c: kc(k), s: 16 }, classes: 'hub' }); cy.add({ data: { id: 'e' + kid + qid, source: qid, target: kid } }); }
        if (!cy.getElementById(id).length) { cy.add({ data: { id, l: h.title || h.url, c: kc(k), s: 8, url: h.url, text: h.text, kind: k } }); cy.add({ data: { id: 'e' + id, source: kid, target: id } }); } });
      cy.layout({ name: 'cose', animate: false, nodeRepulsion: 9000, idealEdgeLength: 60, randomize: !keep }).run(); cy.fit(undefined, 30);
      sec.querySelector('#s4gi').textContent = hits.length ? hits.length + ' записей' : 'ничего не найдено';
      if (!hits.length) sec.querySelector('#s4mi').innerHTML = 'По запросу «' + esc(q) + '» индекс поиска пуст.';
    }
    sec.querySelector('#s4mf').onsubmit = (e) => { e.preventDefault(); const q = sec.querySelector('#s4mqi').value.trim(); if (q.length > 1) load(q); };
    sec.querySelector('#s4mgo').onclick = () => sec.querySelector('#s4mf').requestSubmit(); sec.querySelector('#s4mfit').onclick = () => cy.fit(undefined, 30);
    cy.on('tap', 'node', (e) => { const d = e.target.data(); sec.querySelector('#s4mi').innerHTML = '<b>' + esc(d.l) + '</b><br><small class="mono">' + esc(d.kind || 'узел') + '</small>' + (d.text ? '<p>' + esc(String(d.text).slice(0, 240)) + '</p>' : '') + (d.url ? '<a class="s4ml" href="' + esc(d.url) + '">Открыть</a>' : ''); });
    cy.on('dbltap', 'node', (e) => { const d = e.target.data(); if (d.l && d.l.length > 1) { sec.querySelector('#s4mqi').value = d.l; load(d.l, true); } });
    cy.on('mouseover', 'node', (e) => { const n = e.target; cy.elements().addClass('dim'); n.closedNeighborhood().removeClass('dim'); n.addClass('hov'); }); cy.on('mouseout', 'node', () => { cy.elements().removeClass('dim hov'); });
    load('nox'); addEventListener('resize', () => cy.resize());
  });
})();
