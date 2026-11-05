// B02 exact original WPF owner-provenance depth source contract. SOURCE_ONLY.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
const root = new URL("../../", import.meta.url);
const src = readFileSync(new URL("coordination/e06/OneHostP02WebView2Bridge.cs",root),"utf8");
const builder = readFileSync(new URL("coordination/e06/build_onehost_installer.ps1",root),"utf8");
const compiler = readFileSync(new URL("coordination/e06/t06_compile_original_wpf_p02.py",root),"utf8");
const sha = createHash("sha1").update("blob "+Buffer.byteLength(src)+"\0").update(src).digest("hex");
assert.match(src, /NativeResultExplicitlyDenied\(JsonElement\? candidate, int depth = 0\)/);
assert.match(src, /if \(depth >= 4\) return result.ValueKind is JsonValueKind.Array or JsonValueKind.Object;/);
assert.match(src, /if \(result.GetArrayLength\(\) > 128\) return true;/);
assert.match(src, /NativeResultExplicitlyDenied\(child, depth \+ 1\)/);
assert.match(src, /NativeResultExplicitlyDenied\(field.Value, depth \+ 1\)/);
assert.equal(src.includes("NativeResultExplicitlyDenied(field.Value)"),false);
assert.ok(builder.includes("blob='"+sha+"'"),"NSIS stage must pin original WPF bridge SHA");
assert.ok(compiler.includes('"coordination/e06/OneHostP02WebView2Bridge.cs":"'+sha+'"'),"Compiler must pin original WPF bridge SHA");

const main = readFileSync(new URL("coordination/e06/MainWindow.NativeP02.cs",root),"utf8");
const mainSha = createHash("sha1").update("blob "+Buffer.byteLength(main)+"\0").update(main).digest("hex");
assert.match(main,/if \(depth>=4\) return value.ValueKind is JsonValueKind.Array or JsonValueKind.Object;/);
assert.match(main,/if \(value.GetArrayLength\(\)>128\) return true;/);
assert.match(main,/LegacyOwnerDenial\(child,depth\+1\)/);
assert.ok(builder.includes("sha='"+mainSha+"'"),"NSIS original MainWindow must pin current source Git blob");
assert.ok(compiler.includes('"coordination/e06/MainWindow.NativeP02.cs":"'+mainSha+'"'),"compiler original MainWindow must pin current source");
console.log("B02_WPF_OWNER_NESTED_ARRAY_DEPTH_SOURCE_CONTRACT PASS SOURCE_ONLY (not .NET/Windows)");