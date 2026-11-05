// B02 G2/G3: reject malformed native browser owner navigation proof (SOURCE_ONLY).
// Passing here is NOT a C# compile, physical E06, live provider, or independent E07.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";
const root=new URL("../../", import.meta.url);
const read=path=>readFileSync(new URL(path,root),"utf8");
const bridge=read("coordination/e06/OneHostP02WebView2Bridge.cs");
const compiler=read("coordination/e06/t06_compile_original_wpf_p02.py");
const builder=read("coordination/e06/build_onehost_installer.ps1");
const blob=source=>{const bytes=Buffer.from(source,"utf8");return createHash("sha1").update(Buffer.concat([Buffer.from("blob "+bytes.length+"\0"),bytes])).digest("hex");};
const start=bridge.indexOf('if (route == "browser.open")');
const end=bridge.indexOf("// P03's existing C# queue stays",start);
assert.ok(start>=0&&end>start,"original owner route missing");
const route=bridge.slice(start,end);
for (const proof of ["navigation.Accepted","string.IsNullOrEmpty(navigation.ErrorCode)","navigation.Result is JsonElement navReceipt", "navReceipt.ValueKind == JsonValueKind.Object", "navReceipt.EnumerateObject().Count() == 1", 'navReceipt.TryGetProperty("status", out var navState)', "navState.ValueKind == JsonValueKind.String", 'navState.GetString() == "NAVIGATION_REQUESTED"', "!NativeResultExplicitlyDenied(navigation.Result)", "!navigationConfirmed && IsCurrent(source, epoch)", '"HOLD", navigation.ErrorCode ?? "BROWSER_NATIVE_ACK_HOLD"']) assert.ok(route.includes(proof),"missing owner proof: "+proof);
assert.ok(!route.includes("if (!navigation.Accepted && IsCurrent(source, epoch))"));
assert.ok(!route.includes('Reply(source, epoch, id, route, "COMPLETED"'));
assert.ok(bridge.includes("RevokeDocument()")&&bridge.includes("NativeSidMatches()"));
assert.ok(compiler.includes('"coordination/e06/OneHostP02WebView2Bridge.cs":"'+blob(bridge)+'"'));
assert.ok(builder.includes("relative='coordination/e06/OneHostP02WebView2Bridge.cs'")&&builder.includes("blob='"+blob(bridge)+"'"));
console.log("B02_BROWSER_NATIVE_ACK_FAILCLOSED_SOURCE_ONLY_PASS; Windows/E07 NOT_RUN");
