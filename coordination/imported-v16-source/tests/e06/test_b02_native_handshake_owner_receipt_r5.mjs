// B02 G2/G3 exact-source regression. Source-only: NOT a Windows/E07 receipt.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
const read=p=>readFileSync(p,"utf8");
const blob=s=>{const b=Buffer.from(s,"utf8");return createHash("sha1").update(Buffer.concat([Buffer.from("blob "+b.length+"\0"),b])).digest("hex");};
const main=read("coordination/e06/MainWindow.NativeP02.cs"),stage=read("coordination/e06/stage_native_p02.py");
const compiler=read("coordination/e06/t06_compile_original_wpf_p02.py"),builder=read("coordination/e06/build_onehost_installer.ps1");
const owner=read("Packages/P02/worker-python/p02_onehost.py");
const start=main.indexOf('var handshake=await transport.RequestAsync("chat.model"');
const end=main.indexOf("_nativeP02Core=core;",start);
assert.ok(start>=0 && end>start,"native inventory proof must precede bridge admission");
const gate=main.slice(start,end);
for(const fragment of [
"!handshake.Accepted", "!string.IsNullOrWhiteSpace(handshake.ErrorCode)",
"handshake.Result is not JsonElement nativeInventory",
"nativeInventory.ValueKind != JsonValueKind.Object",
"LegacyOwnerDenial(handshake.Result)",
'inventoryModels.ValueKind != JsonValueKind.Array',
'inventoryState.ValueKind != JsonValueKind.String',
'string.IsNullOrWhiteSpace(inventoryState.GetString())',
"P02_REAL_NATIVE_INGRESS_OWNER_RECEIPT_HOLD"
]) assert.ok(gate.includes(fragment),"owner receipt gate absent: "+fragment);
assert.ok(owner.includes("'models': models") && owner.includes("'provider_state': 'OFFLINE' if offline"),"backend original inventory contract drift");
assert.ok(stage.includes('ADDON_SHA="'+blob(main)+'"'),"stage pin mismatch");
assert.ok(compiler.includes('"coordination/e06/MainWindow.NativeP02.cs":"'+blob(main)+'"'),"compiler addon pin mismatch");
assert.ok(compiler.includes('"coordination/e06/stage_native_p02.py":"'+blob(stage)+'"'),"compiler stage pin mismatch");
assert.ok(builder.includes("@{p=$t06Addon;sha='"+blob(main)+"'}"),"builder addon pin mismatch");
assert.ok(builder.includes("@{p=$t06Stage;sha='"+blob(stage)+"'}"),"builder stage pin mismatch");
console.log("B02_NATIVE_HANDSHAKE_OWNER_SOURCE_ONLY_PASS 15/15; WINDOWS_NOT_RUN");
