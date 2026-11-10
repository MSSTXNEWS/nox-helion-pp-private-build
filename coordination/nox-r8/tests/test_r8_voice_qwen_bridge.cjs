'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('coordination/nox-r8/overrides/src/index.html','utf8');
for(const id of ['voiceTask','voiceLevel','voiceText','voiceChatSend','voiceTaskStatus','speak','silence','send','stop','prompt']){
  assert(html.includes('id="'+id+'"'),'VOICE_MISSING_'+id);
}
for(const label of ['ru-es','es-ru','maestro'])assert(html.includes('value="'+label+'"'),'VOICE_MODE_'+label);
assert(html.includes("route('core');"),'NO_SHARED_CORE');
assert(html.includes("$('send').click();"),'NO_SHARED_QWEN_CHAT');
assert(html.includes("if(busy)"),'NO_INFLIGHT_GUARD');
assert(html.includes("if(prior.trim())"),'NO_DRAFT_GUARD');
assert(html.includes("if(message.length>32000)"),'NO_MAX_SIZE');
assert(html.includes("if(!raw)"),'NO_EMPTY_GUARD');
assert(html.includes("getUserMedia")===false,'MICROPHONE_CLAIM_UNVERIFIED');
assert((html.match(/<button class="core /g)||[]).length===8,'CORE_ID_COUNT_CHANGED');
console.log('NOX_R8_VOICE_TRANSLATOR_SHARED_QWEN_SOURCE_PASS');
