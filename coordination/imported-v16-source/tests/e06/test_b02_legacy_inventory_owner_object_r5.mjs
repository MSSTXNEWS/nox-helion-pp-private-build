// B02 · original WPF legacy native inventory owner proof. SOURCE_ONLY.
// Does NOT compile C#, exercise physical Windows E06, download a model or certify E07.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";
const root=new URL("../../",import.meta.url);
const read=p=>readFileSync(new URL(p,root),"utf8");
const blob=s=>{const b=Buffer.from(s,"utf8");return createHash("sha1").update(Buffer.concat([Buffer.from("blob "+b.length+"\0"),b])).digest("hex");};
const main=read("coordination/e06/MainWindow.NativeP02.cs");
const stage=read("coordination/e06/stage_native_p02.py");
const compiler=read("coordination/e06/t06_compile_original_wpf_p02.py");
const builder=read("coordination/e06/build_onehost_installer.ps1");
const route=main.split("private async Task DispatchLegacyNativeAsync")[1];
assert.ok(route,"missing original legacy WPF handler");
for(const gate of [
 'legacyReceipt.ValueKind != JsonValueKind.Object',
 'NATIVE_MODEL_INVENTORY_OBJECT_HOLD',
 'NATIVE_MODEL_CATALOG_ARRAY_HOLD',
 'legacyReceipt.TryGetProperty("models",out var ownerCatalog)',
 'ownerCatalog.ValueKind != JsonValueKind.Array',
 'list.ValueKind == JsonValueKind.Array',
 'ps.ValueKind == JsonValueKind.String',
 'ps.GetString() : "HOLD"',
 'LegacyOwnerDenial(result.Result)',
 'LegacyDocumentCurrent(source,epoch)',
 'Interlocked.Read(ref _a1OwnerStopEpoch)!=legacyChatStopEpoch'
]) assert.ok(route.includes(gate),"original owner gate missing: "+gate);
assert.ok(!route.includes('result.Result is JsonElement inventory && inventory.TryGetProperty("provider_state"'),"unsafe untyped state");
assert.ok(route.indexOf('NATIVE_MODEL_CATALOG_ARRAY_HOLD') < route.indexOf('PostMessage(new {kind="p02NativeResult"'),"catalog must not report success before native shape proof");
assert.ok(stage.includes('ADDON_SHA="'+blob(main)+'"'),"stage addon pin drift");
assert.ok(compiler.includes('"coordination/e06/MainWindow.NativeP02.cs":"'+blob(main)+'"'),"compile addon pin drift");
assert.ok(compiler.includes('"coordination/e06/stage_native_p02.py":"'+blob(stage)+'"'),"compile stage pin drift");
assert.ok(builder.includes("@{p=$t06Addon;sha='"+blob(main)+"'}"),"builder addon pin drift");
assert.ok(builder.includes("@{p=$t06Stage;sha='"+blob(stage)+"'}"),"builder stage pin drift");
console.log("B02_LEGACY_INVENTORY_OWNER_SOURCE_ONLY_PASS 19/19");
