import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const src=readFileSync(new URL('./menu.js',import.meta.url),'utf8');
test('original SETTINGS routes to owner-verified HKCU, never direct registry access',()=>{
 assert.match(src,/if\(id==='settings'\)\{nativeSettings\(label\);return;\}/);
 assert.match(src,/createAutostartOwnerFlow\(\(route,payload\)=>client\.request\(route,payload\)\)/);
 assert.match(src,/settingsAutostartOwnerAdmission\(b,issued,event\)/);
 assert.match(src,/b\.id=AUTOSTART_UIA_IDS\[kind\]/);
 assert.match(src,/b\.dataset\.nativeRoute='system\.autostart'/);
 assert.doesNotMatch(src,/reg\s+add|window\.localStorage\.setItem\(['"]autostart/);
});
