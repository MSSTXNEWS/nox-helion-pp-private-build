// FAST02 source regression: only real native STREAMING drives motion.
// Does not replace physical E07, consent or active STOP acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

test('native neural flow is never a fake owner status or second host',()=>{
 const js=readFileSync(new URL('./onehost-menu-bindings.mjs',import.meta.url),'utf8');
 assert.match(js,/const setNeuralFlow=state=>/);
 assert.match(js,/client\.request\('helion\.chat'/);
 assert.match(js,/if\(typeof event\?\.delta==='string'&&event\.delta\.trim\(\)\)\{/);
 assert.match(js,/receivedNonemptyStream=true;\s*if\(visible\(\)\)setNeuralFlow\('STREAMING'\)/);
 assert.match(js,/setNeuralFlow\('STOP_REQUESTED'\)/);
 assert.match(js,/if\(visible\(\)\)setNeuralFlow\(nativeCompletedOwnerReply\(reply\)&&verifiedNativeText\(reply\)\?'COMPLETED':'HOLD'\)/);
 assert.ok(js.includes("client.request('chat.stop'"));
 assert.ok(js.includes('if(chatScene&&chatLog&&chatScene.contains(chatLog)'));
 assert.ok(js.includes("neuralFlow.setAttribute('aria-hidden','true')"));
});
test('neural animation is streaming-only and obeys reduced motion',()=>{
 const css=readFileSync(new URL('./nox-r11-wow.css',import.meta.url),'utf8');
 assert.ok(css.includes('#chat[data-nox-neural-flow="STREAMING"] .nox-native-flow svg'));
 assert.ok(css.includes('FAST02 · native neural flow'));
 assert.ok(css.includes('@media(prefers-reduced-motion:reduce)'));
 assert.ok(css.includes('body[data-fx="ECO"]'));
 assert.ok(css.includes('pointer-events:none'));
 assert.ok(css.includes('animation:none!important'));
});
