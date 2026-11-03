import test from 'node:test';
import assert from 'node:assert/strict';
import {DIRECTIONS,WORLDS,CORE_IDS,PERSONAS,PRIMARY,ROUTE_COUNT,getWorld,getRoute} from './express-layout.mjs';
import {readFileSync} from 'node:fs';
test('EXPRESS 10 graphical worlds nested in eight fixed directions and separate CoreID',()=>{
 assert.equal(DIRECTIONS.length,8);assert.equal(WORLDS.length,10);assert.equal(CORE_IDS.length,8);
 assert.deepEqual(PRIMARY,['CHAT','INSTALL','MODELS','LEARN','REPORTS']);assert.equal(PERSONAS.length,5);
 for(const w of WORLDS){assert.ok(DIRECTIONS.some(d=>d[0]===w.section));assert.equal(getWorld(w.id),w);}
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
 assert.match(src,/const chooseCore=v=>\{core=v;selectedCore=/);
 assert.match(src,/const choosePersona=v=>\{persona=v;selectedPersona=/);
});
