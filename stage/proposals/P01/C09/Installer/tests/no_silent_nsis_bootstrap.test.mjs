// Read-only source regression. This test MUST NOT invoke makensis/PowerShell/CI.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const source = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../../../../../coordination/e06/build_onehost_installer.ps1'), 'utf8');
test('NSIS source builder never installs packages silently', () => {
  assert.doesNotMatch(source, /^\s*(?:&\s*)?(?:choco|winget|scoop)\s+install\b/im);
  assert.match(source, /NSIS_PREINSTALLED_BINARY_REQUIRED_NO_AUTO_INSTALL/);
});
test('reuses preinstalled makensis or fails before execution', () => {
  assert.match(source, /Get-Command 'makensis\.exe'/);
  assert.ok(source.includes('C:\\Program Files (x86)\\NSIS\\makensis.exe'));
  assert.ok(source.includes('C:\\Program Files\\NSIS\\makensis.exe'));
  assert.ok(source.indexOf('NSIS_PREINSTALLED_BINARY_REQUIRED_NO_AUTO_INSTALL') < source.indexOf('& $makensisPath /V2'));
});
test('existing payload SHA gate remains before separately authorized NSIS invocation', () => {
  assert.ok(source.indexOf("'ORIGINAL_NSIS_PAYLOAD_SHA_GATE_HOLD'") < source.indexOf('& $makensisPath /V2'));
  assert.ok(source.includes("if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $setup -PathType Leaf))"));
});
