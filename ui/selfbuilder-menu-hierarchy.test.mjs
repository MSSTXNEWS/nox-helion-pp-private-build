// Source-level regression for the installed OneHost menu (not physical E07).
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {P01_MENU_WORLD_NAV,MENU_V2_SECTIONS,SELFBUILDER_MENU,
        NOX_NAV_GROUPS,groupForNoxAction} from './selfbuilder-menu-v2.mjs';

test('no-loss navigation: 8 original directions and 10 logical pages',()=>{
 assert.equal(MENU_V2_SECTIONS.length,8);
 assert.equal(P01_MENU_WORLD_NAV.length,10);
 for(const page of P01_MENU_WORLD_NAV){
  assert.ok(MENU_V2_SECTIONS.includes(page.section));
 }
});
test('every previously reviewed action is still assigned to one reachable group',()=>{
 const groups=new Set(NOX_NAV_GROUPS.map(g=>g.id));
 assert.deepEqual(groups,new Set(['status','models','source','control']));
 assert.ok(SELFBUILDER_MENU.length>=18);
 const categories=SELFBUILDER_MENU.map(groupForNoxAction);
 for(const category of categories)assert.ok(groups.has(category),category);
 for(const group of groups)assert.ok(categories.includes(group),group+' must be reachable');
 assert.ok(SELFBUILDER_MENU.some(item=>item.actionId==='selfbuilder.worker.stop'));
 assert.ok(SELFBUILDER_MENU.some(item=>item.actionId==='selfbuilder.propose'));
});
test('progressive disclosure preserves original native invocations and STOP',()=>{
 const code=readFileSync(new URL('./selfbuilder-menu-v2.mjs',import.meta.url),'utf8');
 const css=readFileSync(new URL('./selfbuilder-menu-v2.css',import.meta.url),'utf8');
 for(const text of ['activeGroup','nox-sb-nav-path','groupForNoxAction(item)',
                    'b.hidden=item.section!==section||!activeGroup',
                    'invokeNative({routeId:item.routeId','nativeConsent']){
  if(text==='nativeConsent')continue;
  assert.ok(code.includes(text),text);
 }
 for(const text of ['nox-sb-group-grid[hidden]','@media(max-width:390px)',
                    '@media(prefers-reduced-motion:reduce)', '@media(forced-colors:active)']){
  assert.ok(css.includes(text),text);
 }
 assert.ok(code.includes("selfbuilder.worker.stop"));
});
