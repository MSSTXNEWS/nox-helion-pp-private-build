'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('coordination/nox-r8/overrides/src/index.html','utf8');
const donor=fs.readFileSync('coordination/nox-r8/integrations/v16/proposals/NOX-CINEMA-FX/nox-cinema.mjs','utf8');
for(const s of ['NOX_V16_CINEMA_FX_INTEGRATED','installNoxCinemaFX({root,orbs,profile:',"id:'HELION'","'CONSCIOUSNESS','ATLAS','REFLECTION','NEXUS','FORGE','CORE','VOICE','PERSONA'",'window.noxCinemaFX=fx','window.addEventListener(\'pagehide\'','watcher.disconnect();fx.destroy()','const watcher=new MutationObserver','fx.setProfile(reduced?\'REDUCED\':value)'])
  assert(html.includes(s),'MISSING_CINEMA_INTEGRATION '+s);
for(const k of ['gravitationalSample','installNoxCinemaFX','NOX_FX_ALREADY_MOUNTED'])
  assert(html.includes(k)&&donor.includes(k),'SOURCE_NOT_EMBEDDED '+k);
assert(html.includes('.constellation button.core.nox-cinema-orb{position:absolute}'),'LAYOUT_PROTECTION_LOST');
assert((html.match(/<button class="core /g)||[]).length===8,'CORE_COUNT_CHANGED');
assert(html.includes('<body class="reduced">'),'BODY_PREIMAGE_CHANGED');
const blocks=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
assert(blocks.length===2,'SCRIPT_COUNT_CHANGED');
for(const [i,b] of blocks.entries())new vm.Script(b[1],{filename:'NOX-script-'+i+'.js'});
console.log('R8 V16 CINEMA NINE ORBS DOM + SYNTAX SOURCE PASS');
