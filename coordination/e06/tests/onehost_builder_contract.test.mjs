import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const script = fs.readFileSync(new URL('../build_onehost_installer.ps1', import.meta.url), 'utf8');
test('NSIS -D values interpolate the three actual PowerShell script paths',()=>{
  for(const [key,variable] of [['VERIFY_SCRIPT','verifyScript'],['PREFLIGHT_SCRIPT','preflightScript'],['REMOVE_SCRIPT','removeScript']]) {
    assert.ok(script.includes('"/D'+key+'=$'+variable+'"'));
    assert.ok(!script.includes('"/D'+key+'=$$'+variable+'"'));
  }
});
test('bad RunID and non-Windows host are refused before any build output',()=>{
  const at=script.indexOf('$source=(Resolve-Path');
  assert.ok(at>0);
  assert.ok(script.indexOf('E06_INVALID_RUN_ID_HOLD')<at);
  assert.ok(script.indexOf('E06_WINDOWS_X64_REQUIRED')<at);
  assert.ok(script.includes('OUTPUT_ALREADY_EXISTS_NO_OVERWRITE'));
});
test('original P01 four-script SHA guard and numeric manifest version remain',()=>{
  for(const name of ['Preflight-InstallPath.ps1','Verify-Payload.ps1','Remove-InstalledPayload.ps1','NOX-HELION-Setup.nsi'])
    assert.ok(script.includes("'"+name+"' = @("));
  assert.match(script, /\$appVersion = '16\.0\.0'/);
  assert.match(script, /P01_OWNER_PREIMAGE_SHA_HOLD/);
});
test('one WPF host, original NSIS rollback/verify and no source overwrite',()=>{
  for(const marker of ['NOX.P01.Shell.csproj','dotnet publish','ORIGINAL_NSIS_PAYLOAD_SHA_GATE_HOLD','NO_LOSS_SOURCE_OUTPUT_PATH_OVERLAP','Remove-InstalledPayload.ps1'])
    assert.ok(script.includes(marker));
  assert.ok(!script.includes('Remove-Item -Recurse'));
});
