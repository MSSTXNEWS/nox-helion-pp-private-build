// B02 G2/G3 source-derived native owner denial regression, not physical E06/E07.
import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";
const root=new URL("../../", import.meta.url);
const read=path=>readFileSync(new URL(path,root),"utf8");
const blob=s=>{const v=Buffer.from(s,"utf8");return createHash("sha1").update(Buffer.concat([Buffer.from("blob "+v.length+"\\0".replace("\\\\0","\\0")),v])).digest("hex");};
function check(x) {
  const parts={
    bridge:x.bridge.split("private static bool NativeOwnerStatusDenied")[1]?.split("private static bool NativeResultExplicitlyDenied")[0],
    legacy:x.main.split("private static bool LegacyOwnerStatusDenied")[1]?.split("private static bool LegacyOwnerDenial")[0]
  };
  function classifier(kind){
    let body=parts[kind]; if(!body)throw Error("native method not found: "+kind);
    let exactRegion=kind==="bridge"?
       body.match(/if \(value is ([\s\S]*?)\) return true;/)?.[1]:
       body.match(/foreach \(var exact in new\[\] \{([\s\S]*?)\}\)/)?.[1];
    let suffixRegion=kind==="bridge"?
       body:
       body.match(/foreach \(var suffix in new\[\] \{([\s\S]*?)\}\)/)?.[1];
    if(!exactRegion||!suffixRegion)throw Error("classifier format drift: "+kind);
    let exact=[...exactRegion.matchAll(/"([^"]+)"/g)].map(a=>a[1]);
    let suffix=kind==="bridge"?
       [...suffixRegion.matchAll(/value\.EndsWith\("([^"]+)"/g)].map(a=>a[1]):
       [...suffixRegion.matchAll(/"([^"]+)"/g)].map(a=>a[1]);
    let prefix=[...body.matchAll(/value\.StartsWith\("([^"]+)"/g)].map(a=>a[1]);
    if(exact.length<20||suffix.length<20)throw Error("missing original classifier tokens: "+kind+" "+exact.length+"/"+suffix.length);
    return status=>{
      if(typeof status!=="string"||!status.trim())return true;
      let v=status.trim().replace(/[\s-]+/g,"_").toUpperCase();
      return exact.includes(v)||suffix.some(t=>v.endsWith(t))||prefix.some(t=>v.startsWith(t));
    };
  }
  const bad=["UNAUTHORIZED","NO_CONSENT","INVALID","STALE","NOT_INSTALLED","TIMED_OUT","RIGHTS_MISSING","ACTION_DISALLOWED","OWNER_UNAUTHORIZED","OWNER_NO_CONSENT","OWNER_INVALID","OWNER_STALE","MODEL_NOT_INSTALLED","JOB_TIMED_OUT","MODEL_RIGHTS_MISSING","MODEL_ACTION_DISALLOWED","owner-unauthorized","owner no consent","HOLD","PROVIDER_OFFLINE"];
  const good=["QUEUED","RUNNING","COMPLETED","CANCEL_REQUESTED","STOP_REQUESTED","NAVIGATION_REQUESTED","MODEL_READY"];
  let checks=0;
  for(let kind of ["bridge","legacy"]){
    let fn=classifier(kind);
    for(let status of bad){if(!fn(status))throw Error(kind+" accepted denied owner "+status);checks++;}
    for(let status of good){if(fn(status))throw Error(kind+" rejected positive "+status);checks++;}
  }
  for(let s of [x.bridge,x.main]){
    if(!(s.includes("depth>=4")||s.includes("depth >= 4"))||!s.includes('"ownerReceipt"'))throw Error("native nested owner guard removed");
    checks+=2;
  }
  if(!x.stage.includes(x.shaMain)||!x.compiler.includes(x.shaStage)||
     !x.compiler.includes(x.shaMain)||!x.compiler.includes(x.shaBridge)||
     !x.builder.includes(x.shaStage)||!x.builder.includes(x.shaMain)||!x.builder.includes(x.shaBridge))
     throw Error("immutable build/stager pins inconsistent");
  checks+=7;
  return checks;
}
const main=read("coordination/e06/MainWindow.NativeP02.cs"),bridge=read("coordination/e06/OneHostP02WebView2Bridge.cs"),stage=read("coordination/e06/stage_native_p02.py"),compiler=read("coordination/e06/t06_compile_original_wpf_p02.py"),builder=read("coordination/e06/build_onehost_installer.ps1");
const n=check({main,bridge,stage,compiler,builder,shaMain:blob(main),shaBridge:blob(bridge),shaStage:blob(stage)});
console.log("B02_NATIVE_OWNER_DENIAL_SOURCE_ONLY_PASS "+n+"/"+n);
