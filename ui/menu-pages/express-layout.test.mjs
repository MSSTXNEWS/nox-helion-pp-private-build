import test from 'node:test';
import assert from 'node:assert/strict';
import {DIRECTIONS,WORLDS,CORE_IDS,PERSONAS,PRIMARY,ROUTE_COUNT,getWorld,getRoute} from './express-layout.mjs';
import {readFileSync} from 'node:fs';
test('EXPRESS 10 graphical worlds nested in eight fixed directions and separate CoreID',()=>{
 assert.equal(DIRECTIONS.length,8);assert.equal(WORLDS.length,10);assert.equal(CORE_IDS.length,8);
 assert.deepEqual(PRIMARY,['CHAT','INSTALL','MODELS','LEARN','SETTINGS']);assert.equal(PERSONAS.length,5);
 for(const w of WORLDS){assert.ok(DIRECTIONS.some(d=>d[0]===w.section));assert.equal(getWorld(w.id),w);}
});
test('the fifth graphical primary action opens the EXISTING settings route, not REPORTS',()=>{
 const source=readFileSync(new URL('./menu.js',import.meta.url),'utf8');
 const functionText=source.match(/function mainAction\(name\)\{[\s\S]*?\n\}/)?.[0];
 assert.ok(functionText,'real menu primary action function must remain present');
 const opened=[];
 const actual=new Function('openRoute','return ('+functionText+');')(route=>opened.push(route));
 for(const label of PRIMARY)actual(label);
 assert.deepEqual(opened,['chat','system','model-library','evolution','settings']);
 assert.ok(WORLDS.some(world=>world.section==='system'&&world.routes.some(route=>route.id==='settings')));
 actual('REPORTS');
 assert.equal(opened.length,5,'deprecated REPORTS primary may not be silently substituted');
 assert.match(source,/P\.actions\.append\(b\)/);
});
test('all 64 route ids are unique and discoverable',()=>{
 const ids=WORLDS.flatMap(w=>w.routes.map(r=>r.id));
 assert.equal(ROUTE_COUNT,64);assert.equal(ids.length,new Set(ids).size);
 ids.forEach(id=>assert.equal(getRoute(id)?.id,id));
});
test('incomplete feature dialog owns acceleration; no fake telemetry or direct internet window',()=>{
 const src=readFileSync(new URL('./menu.js',import.meta.url),'utf8');
 assert.match(src,/function pending\(/);assert.match(src,/УСКОРИТЬ NOX/);
 assert.match(src,/selfbuilder\.propose/);assert.match(src,/createNativeMenuClient/);
 assert.doesNotMatch(src,/Math\.random|window\.open|fetch\(/);
 assert.match(src,/if\(!client\)/); // attempt native submission only when host is connected
 assert.match(src,/else\{/); // otherwise prepare a copyable task, never fake an ACK
});

test('priority routes owner-selected native scope and truthful S03 ACK',()=>{
 const src=readFileSync(new URL('./menu.js',import.meta.url),'utf8');
 assert.match(src,/selectedCore=null,selectedPersona=null/);
 assert.match(src,/canonicalChatContext\(selectedCore,PERSONA_TO_OWNER\[selectedPersona\]\)/);
 assert.match(src,/else if\(!scope\)\{offerCopy\(\)/);
 assert.match(src,/selfbuilder\.propose',task,\.\.\.scope/);
 assert.match(src,/receipt\?\.ack===true/);
 assert.match(src,/\^S03-/);
 assert.match(src,/receipt\.source_head/);
 assert.doesNotMatch(src,/Разработка и обучение выполняются/);
 assert.match(src,/chip\.addEventListener\('keydown'/);
 assert.match(src,/b\.dataset\.core=id/);
});

test('LIVE chat source still retains model selection, streaming, STOP and terminal receipt',()=>{
 const src=readFileSync(new URL('./menu.js',import.meta.url),'utf8');
 for(const token of ["function liveChat(","isNativeChatTerminal", "helion.chat", "chat.stop", "chat.model", "chatInFlight", "STREAMING"])assert.ok(src.includes(token),token);
 assert.match(src,/const chooseCore=v=>\{\s*const changed=core!==v;core=v;selectedCore=/);
 assert.match(src,/const choosePersona=v=>\{\s*const changed=persona!==v;persona=v;\s*selectedPersona=/);
 assert.match(src,/if\(changed\)invalidateModelScope\(\)/);
});

test('EXPRESS HOME actually draws exactly eight graphical directions, keeps legacy routes nested',()=>{
 const js=readFileSync(new URL('./menu.js',import.meta.url),'utf8');
 const html=readFileSync(new URL('./index.html',import.meta.url),'utf8');
 const orbBlock=js.match(/DIRECTIONS\.forEach\(\(\[id,title\],index\)=>\{[\s\S]*?P\.planets\.append\(b\);\n\}\);/)?.[0];
 assert.ok(orbBlock,'original HOME must render graphic direction planets');
 const planets=[];
 const target={append(b){planets.push(b);}};
 const mkButton=(label,cls,onclick)=>({
   label,cls,onclick,dataset:{},attributes:{},style:{setProperty(k,v){this[k]=v;}},
   setAttribute(k,v){this.attributes[k]=v;},append(...content){this.content=content;}
 });
 const mkEl=(tag,cls,text)=>({tag,cls,text});
 new Function('DIRECTIONS','WORLDS','button','direction','P','el',orbBlock)(
   DIRECTIONS,WORLDS,mkButton,()=>{}, {planets:target},mkEl);
 assert.equal(planets.length,8,'EXPRESS HOME has exactly eight direction spheres');
 assert.deepEqual(planets.map(p=>p.dataset.section),DIRECTIONS.map(d=>d[0]));
 for(const orb of planets){
   assert.equal(orb.cls,'planet planet-'+orb.dataset.section);
   assert.ok(orb.attributes['aria-label'].includes('функций'));
   assert.equal(orb.attributes['aria-pressed'],'false');
 }
 assert.equal(WORLDS.length,10,'legacy worlds are preserved as nested routes (NO-LOSS)');
 assert.equal(ROUTE_COUNT,64,'legacy route registry must not be deleted');
 assert.deepEqual(PRIMARY,['CHAT','INSTALL','MODELS','LEARN','SETTINGS']);
 assert.match(js,/P\.planets\.querySelectorAll\('button'\).*b\.dataset\.section===w\.section/);
 assert.match(html,/НАПРАВЛЕНИЯ HELION/);
 assert.doesNotMatch(html,/>10 миров/);
 assert.doesNotMatch(js,/P\.title\.textContent='10 МИРОВ HELION'/);
 assert.match(js,/const routes=\{CHAT:'chat',INSTALL:'system',MODELS:'model-library',LEARN:'evolution',SETTINGS:'settings'\}/);
});