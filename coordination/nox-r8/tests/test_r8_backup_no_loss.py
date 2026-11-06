"""B03 R8 backup export regression: SOURCE_ONLY, not an owner Windows acceptance."""
from pathlib import Path

source = (Path(__file__).resolve().parent / 'src' / 'MainWindow.xaml.cs').read_text(encoding='utf-8')
start = source.index('private void BackupLocalDatabase()')
end = source.index('// An explicit native consent gate', start)
backup = source[start:end]
required = (
    'OverwritePrompt = false',
    'dialog.ShowDialog(this) != true',
    'Path.GetFullPath(dialog.FileName)',
    'NOX_BACKUP_LIVE_DATABASE_HOLD',
    'NOX_BACKUP_DEST_EXISTS_HOLD',
    'FileMode.CreateNew',
    'FileShare.None',
    'source.BackupDatabase(backup)',
    'SqliteOpenMode.ReadOnly',
    'PRAGMA quick_check',
    'NOX_BACKUP_INTEGRITY_HOLD',
    'SHA256.HashData(input)',
    'File.Move(staged, destination, overwrite: false)',
    'SHA256.HashData(output)',
    'NOX_BACKUP_SHA_READBACK_HOLD',
)
for phrase in required:
    assert phrase in backup, 'B03_R8_BACKUP_GUARD_MISSING: ' + phrase
for forbidden in ('OverwritePrompt = true', 'File.Copy(', 'File.Delete(', 'File.Move(staged, destination, true)'):
    assert forbidden not in backup, 'B03_R8_NO_LOSS_HOLD: ' + forbidden
assert source.count('private void BackupLocalDatabase()') == 1
assert 'private const string Api = "http://127.0.0.1:11436";' in source
assert 'private const string DefaultModel = "nox-qwen-clean:latest";' in source
print('B03 R8 SOURCE_ONLY backup no-overwrite/staged SQLite quick_check/SHA readback contracts PASS; Windows physical NOT_TESTED')
