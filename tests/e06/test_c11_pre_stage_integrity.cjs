'use strict';
// Existing NOX Express OneHost NSIS builder: original C11 guard must reject corrupt
// installed bytes BEFORE extracting a new stage, avoiding a stranded stage on HOLD.
// Source-only regression: does NOT represent Windows/Setup/E07 execution.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const builder = fs.readFileSync(path.join(root, 'coordination/e06/build_onehost_installer.ps1'), 'utf8');
const owner = fs.readFileSync(path.join(root, 'stage/proposals/P01/C09/Installer/NOX-HELION-Setup.nsi'), 'utf8');
function projectedNsi(builderSource) {
  const anchor = builderSource.match(/\$c11Anchor='([^']+)'/);
  const injection = builderSource.match(/\$c11Guard=@'\r?\n([\s\S]*?)\r?\n'@/);
  assert.ok(anchor && injection, 'original C11 builder must retain exact injection contract');
  const pos = owner.indexOf(anchor[1]);
  assert.ok(pos >= 0 && owner.indexOf(anchor[1], pos + 1) < 0, 'unique NSIS insertion anchor');
  return owner.slice(0, pos) + injection[1] + '\n' + owner.slice(pos);
}
function evidence(source) {
  const oldGuard = source.indexOf('-Root "$INSTDIR" -Manifest "$INSTDIR\\payload.sha256.json" -AllowInstalledMetadata');
  const firstStage = source.indexOf('  StagePayload:');
  const firstExtract = source.indexOf('  SetOutPath "$StageDir"');
  const firstInit = source.indexOf('  InitPluginsDir');
  const firstEarlyVerifier = source.indexOf('  File "/oname=$PLUGINSDIR\\Verify-Payload.ps1"');
  const marker = source.indexOf('  IfFileExists "$INSTDIR\\nox-p01-owned.txt" 0 C11OldPayloadChecked');
  const abort = source.indexOf('Abort "Existing application payload is not rollback-safe; update refused."');
  return [
    ['old install verified before staging', oldGuard >= 0 && oldGuard < firstStage],
    ['old install verified before first payload extraction', oldGuard < firstExtract],
    ['existing preflight initializes plugin directory', firstInit >= 0 && firstInit < oldGuard],
    ['early verifier embedded before invocation', firstEarlyVerifier >= 0 && firstEarlyVerifier < oldGuard],
    ['owner marker controls installed-only verification', marker >= 0 && marker < oldGuard],
    ['abort preserves previously installed files before extraction', abort >= 0 && abort < firstExtract],
    ['original backup rename occurs only after verification', oldGuard < source.indexOf('Rename "$INSTDIR" "$BackupDir"')],
    ['original fresh stage and rollback verifiers remain', source.includes('-Root "$StageDir" -Manifest "$StageDir\\payload.sha256.json"') && source.includes('-Root "$BackupDir" -Manifest "$BackupDir\\payload.sha256.json" -AllowInstalledMetadata')]
  ];
}
const result = evidence(projectedNsi(builder));
for (const [name, condition] of result) assert.ok(condition, name);
// Explicit negative regression: old late-stage anchor must fail the core guarantee.
const legacy = builder.replace(
  "$c11Anchor='  StagePayload:'",
  '$c11Anchor=\'  SetOutPath "$TEMP" ; release current working directory before Rename\''
);
assert.notEqual(legacy, builder, 'legacy baseline must differ');
const old = evidence(projectedNsi(legacy));
assert.equal(old[0][1], false, 'old code wrongly verified current payload after staging');
assert.equal(old[5][1], false, 'old code could strand staged payload on integrity refusal');
console.log('C11 pre-stage source gate: ' + result.length + '/' + result.length + ' PASS; 2 negative checks RED as expected; native Windows NOT_RUN');
