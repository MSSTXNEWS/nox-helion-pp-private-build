'use strict';
/* D04 WebView2: malformed or throwing OS media query must never disable
 * eight native CoreID routes, their IPC dispatch or keyboard access.
 * Executes the actual production route() function in Node's V8.
 * SOURCE_ONLY, not native Windows WebView2 or owner's GPU acceptance. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const candidates = [
  path.resolve(__dirname, 'src', 'index.html'),
  path.resolve(__dirname, '..', 'overrides', 'src', 'index.html')
];
const file = candidates.find(x => fs.existsSync(x));
assert.ok(file, 'Original R8 embedded WebView2 index.html must exist');
const html = fs.readFileSync(file, 'utf8');
const routeSource = html.match(/^function route\(id\)\{[^\n]+\}$/m)?.[0];
assert.ok(routeSource, 'Test must execute the production WebView2 route, not a copied mock');
const headings = {consciousness:'CONSCIOUSNESS', atlas:'ATLAS / TASKS',
  reflection:'REFLECTION / HISTORY', nexus:'NEXUS / MODELS',
  forge:'FORGE / TRAINING', core:'CORE / LIVE CHAT', voice:'VOICE', persona:'PERSONA'};
const ids = Object.keys(headings);
const scenarios = [
  ['os_query_throws', () => {throw Error('OS_MEDIA_QUERY_FAILED');}, false],
  ['os_query_null', () => null, false],
  ['os_matches_getter_throws',
    () => Object.defineProperty({}, 'matches', {get(){throw Error('OS_MQL_GETTER_FAILED');}}), false],
  ['compact', () => ({matches:true}), true],
  ['wide', () => ({matches:false}), false],
  ['no_matchMedia', null, false],
  ['os_matchMedia_property_getter_throws', () => ({}), false]
];
const actions = {consciousness:['health'], atlas:['tasks.list'],
  reflection:['history','knowledge.stats'], nexus:['health'],
  forge:['training','learn.queue'], core:[], voice:[], persona:['settings.get']};
for (const [scenario, matchMedia, shouldScroll] of scenarios) {
  const posts = [];
  const side = {scrollTop:70}, title = {textContent:''};
  const btns = ids.map(route => ({dataset:{route},
    classList:{toggle(){}}, setAttribute(){}, removeAttribute(){}}));
  const panels = ids.map(panel => ({dataset:{panel}, classList:{toggle(){}}}));
  const document = {
    querySelectorAll(selector) {
      return selector === '.core[data-route]' ? btns :
        selector === '.panel[data-panel]' ? panels : [];
    },
    querySelector(selector) {return selector === 'aside.side' ? side : null;}
  };
  const window = matchMedia ? {matchMedia} : {};
  if (scenario === 'os_matchMedia_property_getter_throws')
    Object.defineProperty(window, 'matchMedia', {get(){throw Error('OS_MEDIA_PROPERTY_GETTER_FAILED');}});
  const route = Function('headings','document','window','post','$',
    routeSource + '\nreturn route;')(
      headings, document, window, (...parts) => posts.push(parts[0]),
      id => id === 'routeTitle' ? title : {});
  for (const id of ids) assert.equal(route(id), true,
    scenario + ': route ' + id + ' must remain reachable');
  assert.deepEqual(posts, ids.flatMap(id => actions[id]),
    scenario + ': all native IPC route requests must survive');
  assert.equal(title.textContent, 'PERSONA',
    scenario + ': last CoreID heading updated');
  assert.equal(side.scrollTop, shouldScroll ? 0 : 70,
    scenario + ': compact scroll not incorrectly applied');
  assert.equal(route('not_a_core'), false, scenario + ': unknown route denied');
}
console.log('D04 WebView2 route media-query 7x8 SOURCE_ONLY PASS; owner Windows E2E NOT_TESTED');
