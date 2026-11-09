// NOX EXPRESS · source-level navigation regression, not installed E07 proof.
// Runs with node --test. No native services, downloads, writes, or fake ACK.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {DIRECTIONS,WORLDS,ROUTE_COUNT,getRoute,worldGroups} from './express-layout.mjs';

test('all 8 directions, 10 pages and every existing route remain reachable',()=>{
 assert.equal(DIRECTIONS.length,8);
 assert.equal(WORLDS.length,10);
 assert.equal(ROUTE_COUNT,64);
 const universe=WORLDS.flatMap(world=>world.routes.map(route=>route.id));
 assert.equal(new Set(universe).size,universe.length,'route IDs must be unique');
 for(const world of WORLDS){
  const groups=worldGroups(world.id);
  assert.ok(groups.length>0,world.id+' must have a page');
  const grouped=groups.flatMap(group=>group.routes);
  assert.deepEqual(new Set(grouped.map(route=>route.id)),
                   new Set(world.routes.map(route=>route.id)),world.id+' no-loss');
  assert.ok(groups.every(group=>group.routes.length>0&&group.routes.length<=5),
            world.id+' max five visible actions per subsection');
  assert.ok(grouped.every(route=>getRoute(route.id)?.world.id===world.id));
 }
});
test('navigation uses the original callbacks and a bounded search',()=>{
 const code=readFileSync(new URL('./menu.js',import.meta.url),'utf8');
 assert.match(code,/function catalogBreadcrumb\(/);
 assert.match(code,/function world\(id,subsectionId=null\)/);
 assert.match(code,/worldGroups\(id\)/);
 assert.match(code,/function direction\(id\)/);
 assert.match(code,/pageSize=12/);
 assert.match(code,/openRoute\(route\.id\)/);
 assert.match(code,/client\.request\(/);
 assert.match(code,/chatStopPending/);
 assert.doesNotMatch(code,/window\.open\(/);
});
test('premium navigation stays accessible and reduced-motion safe',()=>{
 const css=readFileSync(new URL('./menu.css',import.meta.url),'utf8');
 for(const token of ['.nox-breadcrumb','.nox-category-grid','.nox-action-grid',
                     '.nox-catalog-card',':focus-visible','@media(max-width:520px)',
                     '@media(prefers-reduced-motion:reduce)','@media(forced-colors:active)']){
  assert.ok(css.includes(token),token);
 }
});
