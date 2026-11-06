// B02 G2/G3 original WPF/WebView2 source-only regression: renderer JSON
// duplicates must be rejected BEFORE any WPF-native owner consent/action.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";
const root=new URL("../../",import.meta.url);
const read=p=>readFileSync(new URL(p,root),"utf8");
const src=read("coordination/e06/OneHostP02WebView2Bridge.cs");
const pipe=read("Packages/P02/worker-chat/NativePythonPipe.cs");
const builder=read("coordination/e06/build_onehost_installer.ps1");
const compiler=read("coordination/e06/t06_compile_original_wpf_p02.py");
const body=src.slice(src.indexOf("private static bool UnambiguousPagePayload("),src.indexOf("private static bool NativeAutostartRequestValid("));
assert.match(body,/new HashSet<string>\(StringComparer\.Ordinal\)/);
assert.match(body,/!keys\.Add\(property\.Name\) \|\| !UnambiguousPagePayload\(property\.Value\)/);
assert.match(body,/foreach \(var item in node\.EnumerateArray\(\)\)/);
assert.match(body,/!UnambiguousPagePayload\(item\)/);
const ingress=src.slice(src.indexOf("private async void OnWebMessageReceived("),src.indexOf("public void Dispose()"));
const nonce=ingress.indexOf("!_usedIds.Add(id)");
const fence=ingress.indexOf("if (!UnambiguousPagePayload(payload))");
const acl=ingress.indexOf("!NativeSidMatches() || !_nativeAcl(_ownerWindowsSid, route)");
const consent=ingress.indexOf("!await _nativeConsent(");
assert.ok(nonce>=0&&nonce<fence&&fence<acl&&acl<consent);
assert.match(ingress,/Reply\(source, epoch, id, route, "HOLD", "PAGE_JSON_DUPLICATE_FIELD_DENIED"\)/);
assert.match(pipe,/RequireUnambiguousJson\(root\)/); // Python path preserved.
assert.match(src,/stopProof\.TryGetProperty\("stopRequested", out var stopFlag\)/);
const sha=createHash("sha1").update("blob "+Buffer.byteLength(src)+"\0").update(src).digest("hex");
assert.ok(builder.includes("blob='"+sha+"'"));
assert.ok(compiler.includes('"coordination/e06/OneHostP02WebView2Bridge.cs":"'+sha+'"'));
console.log("B02_WEBVIEW_NATIVE_DUPLICATE_PAYLOAD_SOURCE_ONLY_PASS; PHYSICAL/E07 NOT_RUN");
