import test from 'node:test';
import assert from 'node:assert/strict';
import {isP01PrimaryRouteTarget} from './mount-p01.mjs';
import {readFileSync} from 'node:fs';

const element=(parent=null)=>({parent,contains(node){
  for(let current=node;current;current=current.parent)if(current===this)return true;
  return false;
}});
test('C07 nested approved submenu/button click never dispatches ancestor route',()=>{
  const tile=element(),world=element(tile),control=element(world);
  const tileIcon=element(tile),worldIcon=element(world),controlIcon=element(control);
  const routes=[{element:tile},{element:world},{element:control}];
  assert.equal(isP01PrimaryRouteTarget(routes[0],tileIcon,routes),true);
  assert.equal(isP01PrimaryRouteTarget(routes[0],worldIcon,routes),false);
  assert.equal(isP01PrimaryRouteTarget(routes[1],worldIcon,routes),true);
  assert.equal(isP01PrimaryRouteTarget(routes[0],controlIcon,routes),false);
  assert.equal(isP01PrimaryRouteTarget(routes[1],controlIcon,routes),false);
  assert.equal(isP01PrimaryRouteTarget(routes[2],controlIcon,routes),true);
  assert.equal(isP01PrimaryRouteTarget(routes[0],element(),routes),false);
  assert.equal(isP01PrimaryRouteTarget(routes[0],null,routes),false);
});

test('C07 accessible anchor Space and nested-route guard share native handler',()=>{
 const src=readFileSync(new URL('./mount-p01.mjs',import.meta.url),'utf8');
 assert.match(src,/isP01PrimaryRouteTarget\(item,event\?\.target,routeEntries\)/);
 assert.match(src,/target\.matches\?\.\('a\[href\]'\)/);
 assert.match(src,/\[' ','Spacebar'\]\.includes\(e\.key\)/);
 assert.match(src,/e\.preventDefault\?\.\(\);void handler\(e\)/);
});
