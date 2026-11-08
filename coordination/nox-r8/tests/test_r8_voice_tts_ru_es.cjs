'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('coordination/nox-r8/overrides/src/index.html','utf8');
for(const s of ['id="voiceSpeechLocale"','value="ru-RU"','value="es-ES"','id="voiceListRefresh"','id="voiceAvailable"','function installedSpeechVoice(locale)',"getVoices()","voiceschanged","v?.lang?.toLowerCase()===locale.toLowerCase()","u.voice=installed","window.speechSynthesis.cancel()","window.speechSynthesis.speak(u)","голос не установлен · HOLD","u.onerror="])
 assert(html.includes(s),'TTS_RU_ES_SOURCE_MISSING '+s);
assert((html.match(/<button class="core /g)||[]).length===8,'NOX_EIGHT_ORBS_CHANGED');
assert(html.includes("case 'complete':"),'QWEN_STOP_AND_COMPLETION_UNTOUCHED');
assert(!html.includes('getUserMedia'),'MICROPHONE_CLAIM_UNVERIFIED');
console.log('NOX_R8_INSTALLED_VOICE_RU_ES_SOURCE_PASS');
