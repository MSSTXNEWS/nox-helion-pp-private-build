#!/usr/bin/env node
"use strict";
// Read-only SHA-pinned source comparison for T06, no writer privileges or QA signature.
function parity(donorSource,liveSource,donorTests,liveTests){
 const errors=[];const added='                    "/" in name or chr(92) in name or ":" in name or\n                    any(ord(ch) < 32 or ord(ch) == 127 for ch in name) or\n';
 if(liveSource.split(added).length!==2||liveSource.replace(added,"")!==donorSource)errors.push("SOURCE_OR_SECURITY_CHANGED");
 function methodMap(s){const lines=s.split("\n"),r={},re=/^    def (test_[a-z0-9_]+)\(self\):/;let start=0,name=null;for(let i=0;i<=lines.length;i++){const m=i<lines.length?lines[i].match(re):null,stop=i===lines.length||(i<lines.length&&/^if __name__/.test(lines[i]));if(m||stop){if(name)r[name]=lines.slice(start,i).join("\n").trimEnd();if(m){name=m[1];start=i}else name=null;}}return r;}
 const prev=methodMap(donorTests),cur=methodMap(liveTests),extra=Object.keys(cur).filter(k=>!(k in prev)).sort(),allowed=["test_rejects_control_character_shard_path","test_rejects_windows_backslash_shard_path","test_rejects_windows_drive_relative_shard_path"].sort();
 if(JSON.stringify(extra)!==JSON.stringify(allowed))errors.push("TEST_ADD_REMOVE_DRIFT");
 for(const [k,v] of Object.entries(prev)){const want=k==="test_rejects_control_character_tensor_name"?v.replace('{"t\\\\n"','{"t\\n"'):v;if(cur[k]!==want)errors.push("TEST_BODY_DRIFT:"+k)}
 for(const k of allowed)if(!cur[k]?.includes('"MODEL_SHARD_PATH_UNSAFE"'))errors.push("TEST_SECURITY_EXPECTATION_WEAK:"+k);
 if(Object.keys(prev).length!==29||Object.keys(cur).length!==32)errors.push("TEST_METHOD_COUNT_DRIFT");
 if(!liveSource.includes('MODEL_SHARD_TENSOR_MAP_MISMATCH')||!liveSource.includes('"HOLD"'))errors.push("CRITICAL_HOLD_CHECK_MISSING");
 return {pass:errors.length===0,errors,donor_test_count:Object.keys(prev).length,integrated_test_count:Object.keys(cur).length,new_security_tests:extra};
}
const EXPECTED=Object.freeze({"donor_source":"fe81cefda2970479f18cc50bae485d006d28f03f","integrated_source":"f5cf5df231ee9ba4344a6445358034b5aaad9241","donor_test":"1b9fd37a56a39c728b663b7eefda6f800037fded","integrated_test":"15a81d1bd44c65625d99fdb617abf434d5a6fe0e"});
module.exports={parity,EXPECTED};
if(require.main===module){
 const fs=require("node:fs"),crypto=require("node:crypto"),files=process.argv.slice(2);
 if(files.length!==4){console.error("Usage: node p04_parity_guard_r23.js donor.py live.py donor_test.py live_test.py");process.exit(64)}
 const raw=files.map(p=>fs.readFileSync(p)),names=["donor_source","integrated_source","donor_test","integrated_test"];
 const mismatch=names.filter((k,i)=>crypto.createHash("sha1").update(Buffer.from("blob "+raw[i].length+String.fromCharCode(0))).update(raw[i]).digest("hex")!==EXPECTED[k]);
 const result=parity(...raw.map(b=>b.toString("utf8")));
 console.log(JSON.stringify({status:result.pass&&!mismatch.length?"SOURCE_PARITY_LIMITED":"HOLD",blob_mismatch:mismatch,...result,warning:"No native/Python runtime or T08 QA acceptance"}));
 process.exit(result.pass&&!mismatch.length?0:2);
}
