// P01 C09 R30 source-only regression: no NSIS, PowerShell, EXE, Windows or CI invocation.
// Run with: node stage/proposals/P01/C09/Installer/test_rollback_trusted_uninstaller_r30.cjs
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
function verifySource(nsis,verifier){
 const seg=nsis.split("Function RestorePrevious")[1]?.split('Section "Uninstall"')[0]||"";
 const checks=[
 ["trusted setup uninstaller prepared before any app rename",seg.indexOf('WriteUninstaller "$PLUGINSDIR\\Uninstall.exe"')>=0&&seg.indexOf('WriteUninstaller "$PLUGINSDIR\\Uninstall.exe"')<seg.indexOf('Rename "$INSTDIR" "$TmpDir"')],
 ["backup payload verified before preparation",seg.indexOf('-AllowInstalledMetadata -ReportVersion')>=0&&seg.indexOf('-AllowInstalledMetadata -ReportVersion')<seg.indexOf('WriteUninstaller "$PLUGINSDIR\\Uninstall.exe"')],
 ["trusted generated file existence required before rename",seg.indexOf('IfFileExists "$PLUGINSDIR\\Uninstall.exe"')>=0&&seg.indexOf('IfFileExists "$PLUGINSDIR\\Uninstall.exe"')<seg.indexOf('Rename "$INSTDIR" "$TmpDir"')],
 ["copy only after backed up tree activated",seg.indexOf('CopyFiles /SILENT "$PLUGINSDIR\\Uninstall.exe" "$INSTDIR"')>seg.indexOf('Rename "$BackupDir" "$INSTDIR"')],
 ["fail closed on copy failure",seg.includes('IfErrors RollbackUninstallerRecovery')],
 ["reverify installed uninstaller before registry publishes version",seg.indexOf('-TrustedUninstaller "$PLUGINSDIR\\Uninstall.exe"')>seg.indexOf('CopyFiles /SILENT "$PLUGINSDIR\\Uninstall.exe"')&&seg.indexOf('-TrustedUninstaller "$PLUGINSDIR\\Uninstall.exe"')<seg.indexOf('WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_ID}" "DisplayVersion"')],
 ["verification failure enters recovery",seg.includes('Goto RollbackUninstallerRecovery')&&seg.includes('RollbackUninstallerRecovery:')],
 ["recovery moves original back and never recurses deletes",seg.includes('Rename "$INSTDIR" "$BackupDir"\n    IfErrors RollbackRecoveryFailed\n    Rename "$TmpDir" "$INSTDIR"')&&!seg.includes('RMDir /r')],
 ["trusted comparison permitted only in installed metadata mode",verifier.includes('[string]$TrustedUninstaller')&&verifier.includes("trusted uninstaller requires installed metadata")],
 ["trusted source cannot self attest",verifier.includes('$trustedFull -ieq $uninstaller')&&verifier.includes("$trustedFull.StartsWith($rootFull+")],
 ["trusted source must be a normal nonreparse file",verifier.includes('$trustedInfo.PSIsContainer')&&verifier.includes('$trustedInfo.Attributes -band [IO.FileAttributes]::ReparsePoint')],
 ["exact installed vs generated SHA256 checked",verifier.includes('Get-FileHash -LiteralPath $trustedFull -Algorithm SHA256')&&verifier.includes('Get-FileHash -LiteralPath $uninstaller -Algorithm SHA256')&&verifier.includes("if ($installedSha -cne $trustedSha) { Fail 'trusted uninstaller SHA-256 mismatch' }")],
 ["existing marker exact readback retained",nsis.includes('FileRead $2 $3')&&nsis.includes('MarkerReadbackFailed:')],
 ["original payload hashes and version output retained",verifier.includes('sha mismatch $rel')&&verifier.includes('if ($ReportVersion) { [Console]::Out.Write([string]$m.version) }')]
 ];
 return checks.map(([name,pass])=>({name,pass:!!pass}));
}
const nsis=fs.readFileSync(path.join(__dirname,'NOX-HELION-Setup.nsi'),'utf8');
const verifier=fs.readFileSync(path.join(__dirname,'Verify-Payload.ps1'),'utf8');
const checks=verifySource(nsis,verifier);
for(const check of checks){assert.equal(check.pass,true,check.name); console.log('PASS '+check.name);}
const withoutCopy=nsis.replace('CopyFiles /SILENT "$PLUGINSDIR\\Uninstall.exe" "$INSTDIR"','; removed CopyFiles fixture');
const withoutDigest=verifier.replace("if ($installedSha -cne $trustedSha) { Fail 'trusted uninstaller SHA-256 mismatch' }","if ($false) { Fail 'disabled hash fixture' }");
assert.equal(verifySource(withoutCopy,verifier).find(x=>x.name==='copy only after backed up tree activated').pass,false,'negative CopyFiles fixture must be RED');
assert.equal(verifySource(nsis,withoutDigest).find(x=>x.name==='exact installed vs generated SHA256 checked').pass,false,'negative SHA fixture must be RED');
console.log('P01_R30_SOURCE_ONLY_PASS checks='+checks.length+' mutation_negatives=2');
