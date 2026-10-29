'use strict';
// G1-A source-only installer regression. Run: node test_G1-A_activation_attestation_r30_20261029.cjs
// Does not invoke PowerShell, NSIS, Windows installers, network or CI.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const file = fs.readFileSync(path.join(__dirname, 'NOX-HELION-Setup.nsi'), 'utf8');
function install(s) {
  const a = s.indexOf('Section "NOX HELION application"');
  const b = s.indexOf('Function RestorePrevious');
  assert.ok(a >= 0 && b > a, 'installer section present');
  return s.slice(a, b);
}
const src = install(file);
const trust = '-TrustedUninstaller "$PLUGINSDIR\\Uninstall.exe"';
function eligible(s) {
  const staging = s.indexOf('-Root "$StageDir" -Manifest "$StageDir\\payload.sha256.json" -AllowInstalledMetadata ' + trust);
  const activated = s.indexOf('-Root "$INSTDIR" -Manifest "$INSTDIR\\payload.sha256.json" -AllowInstalledMetadata ' + trust);
  const firstRename = s.indexOf('Rename "$INSTDIR" "$BackupDir"');
  const registry = s.indexOf('WriteRegStr HKCU');
  const quarantine = s.indexOf('Rename "$INSTDIR" "$StageDir"', s.indexOf('InstallPostActivationRecovery:'));
  const restore = s.indexOf('Rename "$BackupDir" "$INSTDIR"', s.indexOf('InstallPostActivationRecovery:'));
  return staging >= 0 && activated >= 0 && firstRename >= 0 && registry >= 0 &&
    staging < firstRename && activated > firstRename && activated < registry &&
    s.indexOf('Goto InstallPostActivationRecovery') >= 0 &&
    quarantine >= 0 && restore > quarantine &&
    s.indexOf('WriteUninstaller "$INSTDIR\\Uninstall.exe"') < 0;
}
let pass = 0;
function check(name, condition) { assert.ok(condition, name); pass++; }
check('staged and activated payload attested before registry', eligible(src));
check('uninstaller generated before first rename',
  src.indexOf('WriteUninstaller "$PLUGINSDIR\\Uninstall.exe"') >= 0 &&
  src.indexOf('WriteUninstaller "$PLUGINSDIR\\Uninstall.exe"') < src.indexOf('Rename "$INSTDIR" "$BackupDir"'));
check('uninstaller copied into stage before rename',
  src.indexOf('CopyFiles /SILENT "$PLUGINSDIR\\Uninstall.exe" "$StageDir"') >= 0 &&
  src.indexOf('CopyFiles /SILENT "$PLUGINSDIR\\Uninstall.exe" "$StageDir"') < src.indexOf('Rename "$INSTDIR" "$BackupDir"'));
check('marker readback preserved before preparation',
  src.indexOf('StrCmp $3 "NOXHELION.P01 V16$\\r$\\n" MarkerReady MarkerReadbackFailed') >= 0);
check('clean failure before rename', src.includes('InstallUninstallerPreparationFailed:') &&
  src.includes('Abort "Could not prepare a trusted uninstaller; no application directories moved."'));
check('fail-closed verification before rename',
  src.includes('Abort "Staged uninstaller or payload SHA-256 verification failed; no application directories moved."'));
check('after-activation verification linked to recovery',
  src.includes('Goto InstallPostActivationRecovery') && src.includes('InstallRecoveryHold:'));
check('preserves new and previous apps', src.includes('Rename "$INSTDIR" "$StageDir"') &&
  src.includes('Rename "$BackupDir" "$INSTDIR"'));
check('no recursive removal of user files', !/RMDir\s+\/r\b/i.test(src) &&
  !/Remove-Item\s+-Recurse/.test(src));
check('success bypasses failure labels', src.includes('Goto FinishInstall\n  InstallUninstallerPreparationFailed:'));
check('both trusted hash checks same source',
  src.split(trust).length - 1 === 2);
check('NSIS conditional macros balanced',
  (src.match(/\$\{If\}/g) || []).length === (src.match(/\$\{EndIf\}/g) || []).length);
const negative = [
  ['lost live SHA attestation', s => s.replace('-Root "$INSTDIR" -Manifest "$INSTDIR\\payload.sha256.json" -AllowInstalledMetadata ' + trust,
    '-Root "$INSTDIR" -Manifest "$INSTDIR\\payload.sha256.json" -AllowInstalledMetadata')],
  ['lost staged source attestation', s => s.replace('-Root "$StageDir" -Manifest "$StageDir\\payload.sha256.json" -AllowInstalledMetadata ' + trust,
    '-Root "$StageDir" -Manifest "$StageDir\\payload.sha256.json" -AllowInstalledMetadata')],
  ['unverified registry published first', s => s.replace('  ; Re-hash the live activated directory BEFORE changing the registry.',
    '  WriteRegStr HKCU "TEST" "TEST" "UNVERIFIED"\n  ; Re-hash the live activated directory BEFORE changing the registry.')],
  ['no failure recovery', s => s.replace('Goto InstallPostActivationRecovery', 'Goto FinishInstall')],
  ['late overwrite of uninstaller', s => s.replace('  CreateDirectory "$SMPROGRAMS\\NOX HELION"',
    '  WriteUninstaller "$INSTDIR\\Uninstall.exe"\\n  CreateDirectory "$SMPROGRAMS\\NOX HELION"')]
];
for (const [name, mutate] of negative) {
  const changed = mutate(src);
  assert.notEqual(changed, src, 'negative mutation applied: ' + name);
  assert.ok(!eligible(changed), 'negative mutation detected: ' + name);
  pass++;
}
console.log('G1-A SOURCE_ONLY PASS ' + pass + '/17 checks; NSIS/PowerShell/Windows NOT_RUN');
