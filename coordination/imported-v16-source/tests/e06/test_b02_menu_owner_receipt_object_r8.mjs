// B02 native MENU owner receipt: SOURCE_ONLY, never Windows E06/E07.
import {readFileSync} from 'node:fs';
import {strict as assert} from 'node:assert';
import {test} from 'node:test';
const root=new URL('../../',import.meta.url);
const read=p=>readFileSync(new URL(p,root),'utf8');
const main=read('coordination/e06/MainWindow.NativeP02.cs');
const scope=main.split('if (route == "menu.binding") {',2)[1]?.split('if (route == "menu.dispatch") {')[0]||'';
test('menu native owner completion requires object and nonempty receipt',()=>{
 for(const expr of ['ownerResult.Result is not JsonElement nativeResult',
   'nativeResult.ValueKind != JsonValueKind.Object',
   '!nativeResult.EnumerateObject().Any()',
   'name == "model"',
   'nativeResult.TryGetProperty("models", out var nativeCatalog)',
   'nativeCatalog.ValueKind != JsonValueKind.Array'])
   assert.ok(scope.includes(expr),expr);
 assert.ok(scope.indexOf('nativeResult.ValueKind != JsonValueKind.Object') <
           scope.indexOf('status = "MENU_NATIVE_OWNER_RESULT"'));
 assert.ok(scope.includes('await ConfirmP02NativeAsync(ownerRoute, ownerPayload, cancel)'));
 assert.ok(scope.includes('NativeP02Acl(ownerSid, ownerRoute)'));
});
