'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict'),vm=require('node:vm');
const cs=fs.readFileSync('coordination/nox-r8/overrides/src/MainWindow.xaml.cs','utf8');
const html=fs.readFileSync('coordination/nox-r8/overrides/src/index.html','utf8');
for(const s of ['using System.Speech.Recognition;','SpeechRecognitionEngine.InstalledRecognizers()',
'engine.SetInputToDefaultAudioDevice()','new DictationGrammar()','RecognizeMode.Single',
'localAsrTimeout.Start()','TimeSpan.FromSeconds(20)','MessageBoxButton.YesNo',
'case "asr.start": BeginLocalAsr(Text("locale"), Text("requestId"));',
'case "asr.stop": StopLocalAsr(Text("requestId"));',
'StopLocalAsrInternal("WINDOW_CLOSING", notify: false)',
'engine.RecognizeAsyncCancel()'])
 assert(cs.includes(s),'NATIVE_ASR_GUARD_MISSING '+s);
for(const s of ['id="asrInventory"','id="asrStart"','id="asrStop"','id="asrLocale"',
"post('asr.start',{locale,requestId})","post('asr.stop',{requestId:activeAsrRequestId})",
"case 'asr.complete':","case 'asr.denied':","case 'asr.installed':"])
 assert(html.includes(s),'VOICE_ASR_UI_GUARD_MISSING '+s);
assert((html.match(/<button class="core /g)||[]).length===8,'EIGHT_ORBS_CHANGED');
assert(html.includes('route(\'consciousness\');'),'ROUTE_MISSING');
assert(cs.includes('Browser.CoreWebView2.PermissionRequested += (_, args) => args.State = CoreWebView2PermissionState.Deny;'),'BROWSER_MIC_PERMISSION_UNEXPECTED');
const scripts=[...html.matchAll(/<script(?: [^>]*)?>([\s\S]*?)<\/script>/g)];
for(const s of scripts) new vm.Script(s[1]);
console.log('NOX_R8_NATIVE_RU_ES_CONSENTED_ASR_SOURCE_PASS');
