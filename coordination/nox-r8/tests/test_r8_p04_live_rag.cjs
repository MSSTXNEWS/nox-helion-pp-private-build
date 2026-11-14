"use strict";
/* P04 original semantic RAG source-only bridge. Real Windows native UI test
 * separately proves a no-index retrieval through WPF to WebView2. */
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const root=path.resolve(__dirname,".."),src=path.join(root,"overrides","src");
const html=fs.readFileSync(path.join(src,"index.html"),"utf8");
const native=fs.readFileSync(path.join(src,"MainWindow.xaml.cs"),"utf8");
const rag=fs.readFileSync(path.join(root,"integrations","v16","P04","Rag","RagService.cs"),"utf8");
const ingest=fs.readFileSync(path.join(root,"integrations","v16","P04","Rag","RagIngestionService.cs"),"utf8");
assert.match(native,/case "rag\.search": await HandleP04RagSearchAsync/);
assert.match(native,/case "rag\.import": await HandleP04RagImportAsync/);
assert.match(native,/WindowsIdentity\.GetCurrent\(\)\.User/);
assert.match(native,/picker\.ShowDialog\(this\) != true/);
assert.match(native,/P04PersonaScope\(persona\)/);
assert.match(native,/qwen3-embedding:0\.6b/);
assert.match(native,/selfTestRequestedStatic \? "rag_selftest\.json"/);
assert.match(html,/id="ragResults"/);
assert.match(html,/case 'rag\.search\.results':/);
assert.match(html,/case 'rag\.denied':/);
assert.match(html,/id="ragImport"/);
assert.match(rag,/AllowAutoRedirect = false/);
assert.match(rag,/UseProxy = false/);
assert.match(rag,/if \(!File\.Exists\(_indexPath\)\) return new IndexDocument/);
assert.match(ingest,/private static readonly HashSet<string> SupportedExtensions/);
assert.match(ingest,/\.txt", "\.md/);
assert.doesNotMatch(html,/ragResults\)\.innerHTML/);
console.log("P04_RAG_SAME_EXE_BRIDGE_SOURCE_ONLY_PASS; INDEX_IMPORT_NEEDS_OWNER_PERMISSION");
