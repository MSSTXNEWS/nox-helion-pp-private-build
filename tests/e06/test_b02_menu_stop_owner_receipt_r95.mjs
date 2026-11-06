// B02 G2/G3: original native MENU STOP may ACK only on the actual
// PACK01 owner stopRequested=true receipt and current native document.
// SOURCE_ONLY; not an installed runtime, model test, or final E07.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";
const root = new URL("../../",import.meta.url);
const read = p => readFileSync(new URL(p,root),"utf8");
const main=read("coordination/e06/MainWindow.NativeP02.cs");
const owner=read("proposals/NOX-PACK01-50/native_bridge.py");
const stage=read("coordination/e06/stage_native_p02.py");
const compiler=read("coordination/e06/t06_compile_original_wpf_p02.py");
const builder=read("coordination/e06/build_onehost_installer.ps1");
const blob = s => {
  const b=Buffer.from(s,"utf8");
  // Git object header ends with one NUL byte, not a backslash and digit 0.
  return createHash("sha1").update(Buffer.concat([Buffer.from("blob "+b.length+"\0","utf8"),b])).digest("hex");
};
assert.ok(owner.includes('return {"stopRequested":True}'),"real PACK01 STOP owner receipt contract");
const start=main.indexOf('if (name == "stop")');
const end=main.indexOf('// A graphical binding is not an owner-executed operation',start);
assert.ok(start>=0&&end>start,"original menu.stop block");
const route=main.slice(start,end);
for(const guard of [
  'payload.EnumerateObject().Count() != 1',
  'NativeP02Acl(stopSid, "chat.stop")',
  '"chat.stop", JsonSerializer.SerializeToElement(new { }), cancel',
  '!nativeStop.Accepted',
  '!string.IsNullOrEmpty(nativeStop.ErrorCode)',
  'stopReceipt.ValueKind != JsonValueKind.Object',
  'stopReceipt.TryGetProperty("stopRequested", out var nativeStopRequested)',
  'nativeStopRequested.ValueKind != JsonValueKind.True',
  'LegacyOwnerDenial(nativeStop.Result)',
  'cancel.IsCancellationRequested || !NativeP02Acl(stopSid, "chat.stop")',
  '!ReferenceEquals(_nativeP02Core, core)',
  '!ReferenceEquals(_nativeP02Bridge, bridge) || bridge.BrowserExternalActive',
  '"MENU_STOP_REVOKED_HOLD"',
  '"MENU_STOP_REQUESTED"'
]) assert.ok(route.includes(guard),"missing native owner stop gate: "+guard);
assert.ok(stage.includes(blob(main)),"MainWindow addon Git blob pin");
assert.ok(compiler.includes(blob(main)) && builder.includes(blob(main)),"direct builder addon pins");
assert.ok(compiler.includes(blob(stage))&&builder.includes(blob(stage)),"stager pin");

// B02 R5 same CoreWebView2 object survives native consent / STOP during reload.
const binding=main.slice(main.indexOf('if (route == "menu.binding")'),main.indexOf('if (route == "menu.dispatch")'));
assert.ok(binding.includes('var bindingEpoch = Interlocked.Read(ref _nativeDocumentEpoch);'),
  "original native MENU must bind async owner operations to the live document");
assert.equal((binding.match(/Interlocked.Read\(ref _nativeDocumentEpoch\) != bindingEpoch/g)||[]).length,3,
  "STOP postawait and model/selfbuilder postconsent/postdispatch must fence epoch");
assert.ok(route.includes('Interlocked.Read(ref _nativeDocumentEpoch) != bindingEpoch'),
  "STOP ACK must be rejected after a WebView2 navigation or reload");
const modelBinding=binding.slice(binding.indexOf('var ownerRoute ='));
assert.equal((modelBinding.match(/Interlocked.Read\(ref _nativeDocumentEpoch\) != bindingEpoch/g)||[]).length,2,
  "owner model/command operation must fence epoch before and after dispatch");

console.log("B02_MENU_STOP_OWNER_RECEIPT_SOURCE_ONLY_PASS; PHYSICAL/E07 NOT_RUN");
