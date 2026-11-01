import test from 'node:test';
import assert from 'node:assert/strict';
import {MENU_V2_SECTIONS,P01_MENU_WORLD_NAV,menuWorldsForSection}
  from '../../ui/selfbuilder-menu-v2.mjs';
import {LOGICAL_MENU_PARENTS} from './scene-contract.mjs';

test('existing 8 top-level physical tiles, not 10 generated graphics',()=>{
  assert.equal(MENU_V2_SECTIONS.length,8);
  assert.equal(new Set(MENU_V2_SECTIONS).size,8);
  assert.equal(P01_MENU_WORLD_NAV.length,10);
  assert.equal(new Set(P01_MENU_WORLD_NAV.map(w=>w.id)).size,10);
});
test('every existing logical world is reached through exactly one approved physical tile',()=>{
  const all=MENU_V2_SECTIONS.flatMap(section=>menuWorldsForSection(section));
  assert.equal(all.length,10);
  assert.deepEqual(new Set(all.map(w=>w.id)),new Set(Object.keys(LOGICAL_MENU_PARENTS)));
  for(const world of all){
    assert.equal(MENU_V2_SECTIONS.includes(world.section),true);
    assert.equal(typeof world.label,'string');
    assert.ok(world.label.length>3);
  }
  assert.deepEqual(menuWorldsForSection('UNTRUSTED'),[]);
});
test('existing Development menu owns real learning and source builder subsection',()=>{
  assert.deepEqual(menuWorldsForSection('РАЗВИТИЕ').map(w=>w.id),['learning']);
  assert.deepEqual(menuWorldsForSection('СИСТЕМА').map(w=>w.id),['pc']);
  assert.deepEqual(menuWorldsForSection('ТВОРЧЕСТВО').map(w=>w.id),['entertainment','creative']);
});
