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
  assert.equal((script.match(/^\$source=\(Resolve-Path -LiteralPath \$SourceRoot\)\.Path$/gm)||[]).length,1);
  assert.equal((script.match(/^\$original=\(Resolve-Path -LiteralPath \$PythonExe\)\.Path$/gm)||[]).length,1);
  assert.match(script,/^if \(\$RunId -cnotmatch '\^\[A-Za-z0-9\]\[A-Za-z0-9\._:-\]\{1,127\}\$'\) \{ throw 'E06_INVALID_RUN_ID_HOLD' \}$/m);
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

import { createHash } from 'node:crypto';
const theaterPage = fs.readFileSync(new URL('../../../integrations/creative/web/theater.html', import.meta.url));
const theaterScript = fs.readFileSync(new URL('../../../integrations/creative/web/theater.js', import.meta.url));
test('projector files must pass pre-stage SHA before output creation and enter NSIS manifest',()=>{
  assert.ok(script.includes('E06_APPROVED_THEATER_WEB_ROOT_REQUIRED_HOLD'));
  assert.ok(script.indexOf('E06_THEATER_SOURCE_SHA_HOLD') < script.indexOf('New-Item -ItemType Directory -Path $OutputRoot'));
  assert.ok(script.includes("Join-Path $assetsDest 'creative'"));
  assert.ok(script.indexOf('E06_THEATER_STAGED_SHA_HOLD') < script.indexOf('# Include the existing program files'));
  for (const marker of ['E06_THEATER_DEST_CONFLICT_HOLD','E06_THEATER_SOURCE_CHANGED_DURING_BUILD_HOLD','NO_LOSS_CREATIVE_OUTPUT_PATH_OVERLAP','E06_ORIGINAL_ASSET_ROOT_HOLD'])
    assert.ok(script.includes(marker));
});
test('existing theater HTML references the SHA-approved original D02 MENU asset and same script',()=>{
  assert.match(theaterPage.toString('utf8'), /url\('\/menu_sections\.png'\)/);
  assert.ok(!theaterPage.toString('utf8').includes('NOX_HELION_MENU_8_SECTIONS_COLLAGE_APPROVED_20261020.png'));
  assert.match(theaterPage.toString('utf8'), /<script src="theater\.js"><\/script>/);
});
test('source-to-payload theater SHA contract pins exact UTF-8 bytes',()=>{
  for (const [name,bytes] of [['theater.html',theaterPage],['theater.js',theaterScript]]) {
    const digest=createHash('sha256').update(bytes).digest('hex');
    assert.ok(script.includes("'"+name+"'='"+digest+"'"), name+': SHA mismatch');
  }
});

test('approved P01 owner tree and reparse-point output ancestry are protected before writes',()=>{
  const create=script.indexOf('New-Item -ItemType Directory -Path $OutputRoot');
  assert.ok(create > 0);
  for(const marker of [
    'NO_LOSS_APPROVED_P01_OUTPUT_PATH_OVERLAP',
    'NO_LOSS_OUTPUT_PARENT_REPARSE_HOLD',
    "$approvedCanon = [IO.Path]::GetFullPath($approvedRoot)",
    "$outputCandidateCanon = [IO.Path]::GetFullPath($OutputRoot)",
    '$outputCandidateCanon.StartsWith($approvedCanon',
    '$approvedCanon.StartsWith($outputCandidateCanon',
    'Test-Path -LiteralPath $parentToCheck',
    '[IO.FileAttributes]::ReparsePoint'
  ]) {
    const at = script.indexOf(marker);
    assert.ok(at >= 0 && at < create, 'pre-write required: ' + marker);
  }
  assert.equal((script.match(/NO_LOSS_APPROVED_P01_OUTPUT_PATH_OVERLAP/g)||[]).length,1);
  assert.equal((script.match(/NO_LOSS_OUTPUT_PARENT_REPARSE_HOLD/g)||[]).length,1);
});

test('P01 approved NSIS owner scripts keep identical pinned bytes from preflight to compiler',()=>{
  const preflight=script.indexOf('$approvedPreflightHashes = [ordered]@{}');
  const firstHash=script.indexOf('$approvedPreflightHashes[$name] = $digest');
  const firstWrite=script.indexOf('New-Item -ItemType Directory -Path $OutputRoot');
  const finalLoop=script.lastIndexOf('foreach ($name in $approvedHashes.Keys)');
  const compiler=script.indexOf('& $makensisPath /V2');
  assert.ok(preflight >= 0 && preflight < firstHash && firstHash < firstWrite);
  assert.ok(firstWrite < finalLoop && finalLoop < compiler);
  assert.equal((script.match(/foreach \(\$name in \$approvedHashes\.Keys\)/g)||[]).length,2);
  for(const marker of [
    'P01_OWNER_SOURCE_DISAPPEARED_BEFORE_NSIS_HOLD',
    'P01_OWNER_SOURCE_REPARSE_BEFORE_NSIS_HOLD',
    'P01_OWNER_SOURCE_MUTATED_DURING_BUILD_HOLD',
    '$digest -cne $approvedPreflightHashes[$name]'
  ]) assert.ok(script.indexOf(marker) > finalLoop && script.indexOf(marker) < compiler, marker);
  assert.ok(script.includes('NO_LOSS_APPROVED_P01_OUTPUT_PATH_OVERLAP'));
  assert.ok(script.includes('NO_LOSS_OUTPUT_PARENT_REPARSE_HOLD'));
});
