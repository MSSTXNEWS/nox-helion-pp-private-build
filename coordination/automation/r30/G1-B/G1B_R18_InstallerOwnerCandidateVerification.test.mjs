// NOX V16 G1-B: executable SOURCE-ONLY independent owner-patch regression.
// No NSIS compile, PowerShell execution, Windows installer or CI is performed.
// Usage: node G1B_R18_InstallerOwnerCandidateVerification.test.mjs owner.nsi verify.ps1 remove.ps1 preflight.ps1 r10_donor.nsi
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
const [nsiPath,verifyPath,removePath,preflightPath,donorPath]=process.argv.slice(2);
if(![nsiPath,verifyPath,removePath,preflightPath,donorPath].every(Boolean))
  throw Error("Usage: node test.mjs owner.nsi verify.ps1 remove.ps1 preflight.ps1 r10_donor.nsi");
const [N,V,R,P,D]=[nsiPath,verifyPath,removePath,preflightPath,donorPath].map(p=>readFileSync(p,"utf8"));
function gitBlob(x){const b=Buffer.from(x,"utf8");return createHash("sha1").update(Buffer.from("blob "+b.length+"\0")).update(b).digest("hex");}
const wanted=[
["owner nsi",N,"bc1ab71e6e57ac865fd1f98665ca6fb9919d6138"],
["owner verify",V,"e448f8266ba15e809c13bff669924fa825fd4bc1"],
["owner remove",R,"9975f9c1802040d0bb5f30b9563060a1ebd8c44b"],
["current preflight",P,"eb45add5a929eee99bc09ef87f2db3735556b78b"],
["old R10 donor",D,"c54ca1b6ca6b7566b46a89740da7aa1e7ade6b80"]];
for(const [name,source,sha] of wanted)if(gitBlob(source)!==sha)throw Error("P01_PINNED_GIT_BLOB_MISMATCH:"+name);
function contracts(n,v,r,p){
 const check=(b,m)=>{if(!b)throw Error(m);count++;};let count=0;
 const l=n.split(/\r?\n/),cut=l.findIndex(x=>x.includes('DetailPrint "NOX installed.'));
 const writes=l.slice(0,cut).reduce((a,x,i)=>{if(/^\s*WriteReg(?:Str|DWORD)\s+HKCU/.test(x))a.push(i);return a},[]);
 check(writes.length===5,"main HKCU write count:"+writes.length);
 check(writes.every(i=>/^\s*ClearErrors\s*$/.test(l[i-1])&&/^\s*IfErrors InstallRegistrationFailed\s*$/.test(l[i+1])),"unguarded HKCU write");
 const sc=l.findIndex(x=>/^\s*CreateShortcut\s+"\$SMPROGRAMS\\NOX HELION\\NOX HELION\.lnk"/.test(x));
 check(sc>0&&/^\s*ClearErrors\s*$/.test(l[sc-1])&&/^\s*IfErrors InstallRegistrationFailed\s*$/.test(l[sc+1]),"unguarded shortcut");
 check(/Var HadPrevRegVersion/.test(n)&&/Var PrevRegVersion/.test(n)&&/ReadRegStr \$PrevRegVersion HKCU/.test(n),"prior HKCU snapshot missing");
 const failed=n.indexOf("InstallRegistrationFailed:"),recovery=n.indexOf("InstallPostActivationRecovery:");
 check(failed>0&&recovery>failed&&/Goto InstallPostActivationRecovery/.test(n.slice(failed,recovery)),"HKCU failure not routed to recovery");
 const region=n.slice(recovery,n.indexOf("FinishInstall:",recovery));
 check(/Rename "\$INSTDIR" "\$StageDir"/.test(region)&&/Rename "\$BackupDir" "\$INSTDIR"/.test(region)&&!/RMDir\s+\/r|DeleteRegKey/i.test(region),"unsafe or absent recovery");
 check(n.indexOf('WriteUninstaller "$PLUGINSDIR\\Uninstall.exe"')>0&&n.indexOf('WriteUninstaller "$PLUGINSDIR\\Uninstall.exe"')<n.indexOf('Rename "$StageDir" "$INSTDIR"'),"uninstaller not prepared before activation");
 check((n.match(/-TrustedUninstaller "\$PLUGINSDIR\\Uninstall.exe"/g)||[]).length>=3,"missing trusted uninstaller checks");
 check(/\[switch\]\$ReportVersion\s*,/.test(v)&&/\[string\]\$TrustedUninstaller/.test(v)&&/if \(\$TrustedUninstaller -and -not \$AllowInstalledMetadata\)/.test(v),"Verify-Payload args or guard incompatible");
 check(/\[Console\]::Out\.Write\(\[string\]\$m\.version\)/.test(v)&&/\$m\.version -cnotmatch/.test(v),"invalid rollback version contract");
 check(/Get-FileHash -LiteralPath \$trustedFull -Algorithm SHA256/.test(v)&&/Get-FileHash -LiteralPath \$uninstaller -Algorithm SHA256/.test(v),"untrusted uninstaller integrity contract");
 check(/-InstallRoot "\$INSTDIR"/.test(n)&&/\[Parameter\(Mandatory=\$true\)\]\[string\]\$InstallRoot/.test(p)&&!/-PathOnly/.test(n),"unsupported preflight parameter");
 check(/if \(-not \$registered\.Contains\('NOX\.P01\.Shell\.exe'\)\)/.test(r)&&/^\s*foreach \(\$entry in \$checked\) \{[\s\S]*?Assert-VerifiedEntry \$entry[\s\S]*?Remove-Item -LiteralPath \$entry\.Full/m.test(r),"uninstall integrity guard missing");
 check(!/Remove-Item\s+-LiteralPath\s+\$root\b.*-Recurse|RMDir\s+\/r/.test(r),"recursive removal disallowed");
 return count;
}
const samples=[
["owner R16",N,V,R,P,true],
["old R10 donor",D,V,R,P,false],
["HKCU gate removed",N.replace(/IfErrors InstallRegistrationFailed/,"IfErrors 0"),V,R,P,false],
["shortcut gate removed",N.replace(/(CreateShortcut[^\r\n]*\r?\n)\s*IfErrors InstallRegistrationFailed/,"$1  IfErrors 0"),V,R,P,false],
["trust attestation removed",N.replace(/-TrustedUninstaller "\$PLUGINSDIR\\Uninstall\.exe"/,""),V,R,P,false],
["version validation removed",N,V.replace(/\$m\.version -cnotmatch/,"$m.version -cmatch"),R,P,false],
["uninstall entrypoint guard removed",N,V,R.replace(/if \(-not \$registered\.Contains\('NOX\.P01\.Shell\.exe'\)\)/,"if ($false)"),P,false]
];
let verified=0;
for(const [name,n,v,r,p,expectedSuccess] of samples){
 let good=false,err="";
 try {const a=contracts(n,v,r,p);good=true;if(expectedSuccess&&a!==14)throw Error("unexpected assertion count:"+a);}
 catch(e){err=String(e.message);}
 if(good!==expectedSuccess)throw Error("P01_REGRESSION_WRONG_RESULT:"+name+":"+err);
 verified++;
}
console.log("G1B_R18_PINNED_CROSSFILE_SECURITY_PASS cases="+verified+"/7 owner_assertions=14; SOURCE_STATIC_ONLY");
