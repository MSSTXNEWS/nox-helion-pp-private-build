// B02 R5 · original WPF legacy chatModels must not synthesize a model inventory.
// SOURCE_ONLY regression, not an installed Windows E06/E07 acceptance.
import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";
const read = path => readFileSync(path, "utf8");
const blob = s => {
 const bytes=Buffer.from(s,"utf8");
 return createHash("sha1").update(Buffer.concat([
  Buffer.from("blob "+bytes.length+"\0"),bytes])).digest("hex");
};
test("B02 Git blob helper uses canonical Git NUL byte header",()=>{
 assert.equal(blob("test content\n"),"d670460b4b4aece5915caf5c68d12f560a9fe3e4");
});
test("B02 original chatModels fail-closed owner receipt; dependent staging pins",()=>{
 const main=read("coordination/e06/MainWindow.NativeP02.cs");
 const start=main.indexOf('if (action == "chatModels") {');
 const end=main.indexOf('} else if (action=="openModelCenter") {',start);
 assert.ok(start>=0 && end>start,"real legacy owner route missing");
 const code=main.slice(start,end);
 for(const fragment of [
  '!legacyReceipt.TryGetProperty("models",out var list)',
  'list.ValueKind != JsonValueKind.Array',
  '!legacyReceipt.TryGetProperty("provider_state",out var ps)',
  'ps.ValueKind != JsonValueKind.String',
  'string.IsNullOrWhiteSpace(ps.GetString())',
  'throw new NativePipeHold("NATIVE_MODEL_INVENTORY_RECEIPT_HOLD")',
  'var models = list.Clone();','var modelState = ps.GetString();'
 ]) assert.ok(code.includes(fragment),"missing original WPF guard: "+fragment);
 assert.ok(!code.includes('JsonSerializer.SerializeToElement(Array.Empty<string>())'));
 assert.ok(!code.includes('ps.GetString() : "HOLD"'));
 const stage=read("coordination/e06/stage_native_p02.py");
 const compiler=read("coordination/e06/t06_compile_original_wpf_p02.py");
 const builder=read("coordination/e06/build_onehost_installer.ps1");
 assert.ok(stage.includes('ADDON_SHA="'+blob(main)+'"'),"original addon stage SHA pin");
 assert.ok(compiler.includes('"coordination/e06/MainWindow.NativeP02.cs":"'+blob(main)+'"'),"compiler addon SHA pin");
 assert.ok(compiler.includes('"coordination/e06/stage_native_p02.py":"'+blob(stage)+'"'),"compiler stage SHA pin");
 assert.ok(builder.includes("@{p=$t06Addon;sha='"+blob(main)+"'}"),"builder addon SHA pin");
 assert.ok(builder.includes("@{p=$t06Stage;sha='"+blob(stage)+"'}"),"builder stage SHA pin");
});
