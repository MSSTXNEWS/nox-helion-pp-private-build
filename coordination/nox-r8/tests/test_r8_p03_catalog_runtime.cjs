"use strict";
// P03 original source-only and actual WebView2 handler validation; no download or owner-GPU claim.
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const root=path.resolve(__dirname,".."),src=path.join(root,"overrides","src");
const html=fs.readFileSync(path.join(src,"index.html"),"utf8");
const native=fs.readFileSync(path.join(src,"MainWindow.xaml.cs"),"utf8");
const catalog=fs.readFileSync(path.join(root,"integrations","v16","P03","Source","P03.ModelCenter","ModelCatalog.cs"),"utf8");
assert.ok((catalog.match(/Family\("/g)||[]).length>=24,"P03_OFFICIAL_FAMILIES_SOURCE_HOLD");
assert.match(catalog,/EvidenceStatus = CatalogEvidenceStatus.FamilyListed/);
assert.match(native,/case "model.catalog":/);
assert.match(native,/Nox\.P03\.ModelCatalog\.OfficialFamilies\.Select/);
assert.match(html,/id="modelCatalog"/);
assert.match(html,/if\(id==='nexus'\)post\('model.catalog'\)/);
assert.match(html,/\$\('healthButton'\)\.onclick=.*post\('model.catalog'\)/);
const start=html.indexOf("case 'model.catalog':{"),end=html.indexOf("\ncase 'health':",start);
assert.ok(start>=0&&end>start,"P03_ACTUAL_WEBVIEW_HANDLER_MISSING");
const handler=html.slice(start,end);
assert.ok(!handler.includes("innerHTML")&&!handler.includes("model.pull"),"P03_DISCOVERY_MUST_NOT_PULL_OR_HTML_INJECT");
const node={textContent:""},calls=[];
vm.runInNewContext("switch('model.catalog'){"+handler+"}",{
  $:id=>{calls.push(id);assert.equal(id,"modelCatalog");return node;},
  v:[{id:"qwen3",name:"<img src=x onerror=alert(1)>",evidenceStatus:"FamilyListed",oneClickVerified:false},
     {id:"bad",name:"unverified",evidenceStatus:"ArtifactVerified",oneClickVerified:true}]
},{timeout:1500});
assert.deepEqual(calls,["modelCatalog"]);
assert.ok(node.textContent.includes("<img src=x onerror=alert(1)>"),"P03_USER_VISIBLE_CATALOG_TEXT_MISSING");
assert.ok(!node.textContent.includes("unverified"),"P03_UNREVIEWED_ARTIFACT_OFFERED");
console.log("P03_ORIGINAL_CATALOG_NATIVE_AND_WEBVIEW_SOURCE_ONLY_PASS; OWNER_GPU_NOT_TESTED");
