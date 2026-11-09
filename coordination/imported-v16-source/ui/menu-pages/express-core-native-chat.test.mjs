import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const menu=readFileSync(new URL('./menu.js',import.meta.url),'utf8');

test('each of eight original CoreID buttons enters same native chat route',()=>{
 assert.match(menu,/CORE_IDS\.forEach\(id=>\{/);
 assert.match(menu,/selectedCore=id;[\s\S]{0,220}openRoute\('chat'\)/);
 assert.match(menu,/if\(id==='chat'\)\{liveChat\(label\);return;\}/);
 assert.match(menu,/client\.request\('helion\.chat'/);
 assert.match(menu,/client\.request\('chat\.stop'/);
});
test('existing native chat starts on selected HOME CoreID and persona, not CORE default',()=>{
 assert.match(menu,/selectedCore&&CORE_IDS\.includes\(selectedCore\)\?'core\.'\+selectedCore\.toLowerCase\(\):'core\.core'/);
 assert.match(menu,/nativePersonaIds\[PERSONAS\.indexOf\(selectedPersona\)\]/);
 assert.match(menu,/selectedModel/);
 assert.match(menu,/nativeCompleted\(ack\)/);
});
test('no invented provider status or duplicate backend',()=>{
 assert.doesNotMatch(menu,/fakeResponse|mockCompletion|setTimeout\([^)]*PASS/);
 assert.match(menu,/!isNativeChatTerminal\(reply\)/);
});

test('AUTO CORE reselects a native model after a changed CoreID or Persona',()=>{
 assert.match(menu,/const invalidateModelScope=[\s\S]{0,750}void loadModels\(\);void refreshNativePanels\(\);/);
 assert.match(menu,/if\(!modelsRow\.isConnected\|\|inventoryEpoch!==scopeEpoch\)return;/);
 assert.match(menu,/inventoryEpoch===scopeEpoch&&scopeEpoch===0&&names\.includes\(reply\.result\.selectedModel\)/);
 assert.match(menu,/if\(inventoryEpoch===scopeEpoch\)\{modelSelectionPending=false;redraw\(\);\}/);
});
test('S03 history and GPU preflight ignore stale native scope receipts',()=>{
 assert.match(menu,/const epoch=\+\+panelEpoch,context=scopeEpoch,requestedCore=core,requestedPersona=persona;/);
 assert.match(menu,/safe\('chat\.history',\{core_id:requestedCore,persona_id:requestedPersona,limit:10\}\)/);
 assert.match(menu,/epoch!==panelEpoch\|\|context!==scopeEpoch\|\|requestedCore!==core\|\|requestedPersona!==persona/);
});
