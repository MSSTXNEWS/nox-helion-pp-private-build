// B02: canonical ownerReceipt + accepted native IPC refusal parity, SOURCE_ONLY.
// A pass here is NOT a compiled WPF, installed E06 or independent E07 pass.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
const root = new URL("../../", import.meta.url);
const read = path => readFileSync(new URL(path,root),"utf8");
const bridge = read("coordination/e06/OneHostP02WebView2Bridge.cs");
const legacy = read("coordination/e06/MainWindow.NativeP02.cs");
const p03 = read("Packages/P03/Source/python-host/p03_onehost_port.py");
const ingress = read("Packages/P02/worker-python/p02_native_ingress.py");
const builder = read("coordination/e06/build_onehost_installer.ps1");
const compiler = read("coordination/e06/t06_compile_original_wpf_p02.py");
const stager = read("coordination/e06/stage_native_p02.py");
const blob = text => createHash("sha1").update("blob "+Buffer.byteLength(text)+"\0").update(text).digest("hex");
// Inspect ORIGINAL C# owner receipt validators, not a mock IPC implementation.
const web = bridge.split("private static bool NativeResultExplicitlyDenied(",2)[1].split("private static bool NativeAutostartReceiptMatches(",1)[0];
const old = legacy.split("private static bool LegacyOwnerDenial(",2)[1].split("private async Task DispatchLegacyNativeAsync(",1)[0];
assert.match(web,/field.Name is "ok" or "ack" or "accepted" or "success"/);
assert.match(old,/p.Name is "ok" or "ack" or "accepted" or "success"/);
assert.match(web,/field.Name is "result" or "receipt" or "ownerReceipt" or "nativeResult"/);
assert.match(old,/p.Name is "result" or "receipt" or "ownerReceipt" or "nativeResult"/);
// The original Python owner uses snake_case aliases. An explicit denial in any
// of these nested receipts must block a positive transport ACK in BOTH WPF paths.
assert.match(web,/"ownerResult" or "owner_receipt" or "owner_result" or "native_result" &&/);
assert.match(old,/"ownerResult" or "owner_receipt" or "owner_result" or "native_result" &&/);
assert.match(ingress,/"owner_receipt", "ownerReceipt"/);
assert.match(ingress,/"owner_result", "ownerResult"/);
assert.match(web,/field.Value.ValueKind != JsonValueKind.True/);
assert.match(old,/p.Value.ValueKind!=JsonValueKind.True/);
assert.match(web,/NativeResultExplicitlyDenied\(field.Value, depth \+ 1\)/);
assert.match(old,/LegacyOwnerDenial\(p.Value,depth\+1\)/);
assert.ok(p03.includes('for nested_key in ("result", "receipt", "ownerReceipt"):'));
assert.ok(builder.includes("blob='"+blob(bridge)+"'"));
assert.ok(builder.includes("sha='"+blob(legacy)+"'"));
assert.ok(compiler.includes('"coordination/e06/OneHostP02WebView2Bridge.cs":"'+blob(bridge)+'"'));
assert.ok(compiler.includes('"coordination/e06/MainWindow.NativeP02.cs":"'+blob(legacy)+'"'));
assert.ok(stager.includes('ADDON_SHA="'+blob(legacy)+'"'));
console.log("B02_OWNER_RECEIPT_ALIAS_SOURCE_ONLY_PASS (not C#/Windows/E07)");
