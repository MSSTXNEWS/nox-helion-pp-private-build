// NOX EXPRESS FAST01 · source-only geometry/usage regression, NOT installed E07.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {NOX_ICON_NAMES,createNoxLucideIcon} from './nox-lucide-icons.mjs';

function fakeDom(){
 return {createElementNS(ns,tag){
  assert.equal(ns,'http://www.w3.org/2000/svg');
  return {tag,attributes:{},children:[],classList:{values:[],add(n){this.values.push(n)}},
          setAttribute(n,v){this.attributes[n]=String(v)},append(el){this.children.push(el)},prepend(el){this.children.unshift(el)}};
 }};
}
test('112 distinct licensed local vector symbols in one reusable module',()=>{
 assert.equal(NOX_ICON_NAMES.length,112);
 assert.equal(new Set(NOX_ICON_NAMES).size,112);
 for(const n of ['brain','cpu','gauge','book-open','arrow-left','settings','heart','globe','code','monitor','palette','film','chart-line']){
  assert.ok(NOX_ICON_NAMES.includes(n),n);
 }
});
test('all 112 symbols use real namespace SVG DOM and remain decorative',()=>{
 const doc=fakeDom();
 for(const name of NOX_ICON_NAMES){
  const icon=createNoxLucideIcon(doc,name);
  assert.equal(icon.tag,'svg');
  assert.equal(icon.attributes['aria-hidden'],'true');
  assert.equal(icon.attributes.focusable,'false');
  assert.equal(icon.attributes.viewBox,'0 0 24 24');
  assert.ok(icon.children.length>=1,name);
  for(const node of icon.children)assert.ok(['path','circle','rect','line','polyline','polygon','ellipse'].includes(node.tag),name);
 }
 assert.equal(createNoxLucideIcon(doc,'not-approved'),null);
});
test('native menu original actions remain unchanged by icon decorations',()=>{
 const menu=readFileSync(new URL('./selfbuilder-menu-v2.mjs',import.meta.url),'utf8');
 const css=readFileSync(new URL('./selfbuilder-menu-v2.css',import.meta.url),'utf8');
 const license=readFileSync(new URL('./nox-lucide-LICENSE.txt',import.meta.url),'utf8');
 assert.match(menu,/import \{createNoxLucideIcon\} from '\.\/nox-lucide-icons\.mjs'/);
 assert.match(menu,/ownerApprovedRoute\(item\.section,item\.routeId,item\.actionId\)===true/);
 assert.match(menu,/decorateNoxIcon\(doc,b,NOX_GROUP_ICON\[groupForNoxAction\(item\)\]\)/);
 assert.match(menu,/selfbuilder\.worker\.stop/);
 assert.match(css,/WOW FAST01/);
 assert.match(css,/prefers-reduced-motion:reduce/);
 assert.match(license,/Lucide Icons and Contributors/);
 assert.match(license,/The MIT License/);
});
