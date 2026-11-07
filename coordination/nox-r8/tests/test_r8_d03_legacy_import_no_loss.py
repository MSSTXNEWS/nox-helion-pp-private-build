"""D03 R8 native SQLite legacy import: structural source guard + isolated SQLite rollback oracle."""
from pathlib import Path
import sqlite3, tempfile, json
# The repository tests/ layout and CI's copied r8/ layout must both use
# the real native WPF source. Fail closed on missing or ambiguous sources.
here = Path(__file__).resolve().parent
sources = [
    here / 'src' / 'MainWindow.xaml.cs',  # Windows CI: tests copied into r8/
    here.parent / 'overrides' / 'src' / 'MainWindow.xaml.cs',  # repository tree
]
present = [path for path in sources if path.is_file()]
assert len(present) == 1, 'NOX_D03_NATIVE_SOURCE_LAYOUT_HOLD'
cs = present[0].read_text(encoding='utf8')
m=cs.split('private void ImportLegacyJsonlIfNeeded(',1)[1].split('private async void OnMessage(',1)[0]
assert m.index('CheckpointSqlite(db, "PRE_LEGACY_IMPORT")') < m.index('db.BeginTransaction()')
assert m.index('if (skipped != 0') < m.index('receipt.CommandText') < m.index('tx.Commit()')
for x in ['FileAttributes.ReparsePoint','shaPrefix + sourceSha','NOX_LEGACY_JSONL_INCOMPLETE_HOLD','NOX_LEGACY_JSONL_CHANGED_AFTER_IMPORT_HOLD','NOX_LEGACY_JSONL_CHANGED_DURING_IMPORT_HOLD','tx.Rollback();','File.ReadLines(legacy)','INSERT INTO imported_sources(source,imported_at,rows)']:
    assert x in m,x
assert 'if (legacyImportHold != null) Send("notice", legacyImportHold);' in cs
# Previous releases may already have a partial import receipt without a SHA.
# Never silently accept it as evidence all old rows were copied.
assert 'if (priorSha == null)' in m
assert 'NOX_LEGACY_JSONL_UNVERIFIED_PRIOR_RECEIPT_HOLD' in m
assert 'NOX_LEGACY_JSONL_CHANGED_AFTER_IMPORT_HOLD' in m
assert m.index('if (rows == 0 && skipped == 0)') < m.index('receipt.CommandText')
assert 'NOX_LEGACY_JSONL_EMPTY_HOLD' in m
assert 'catch (UnauthorizedAccessException)' in m and 'catch (IOException)' in m
assert 'if (!selfTestRequested) ImportLegacyJsonlIfNeeded(db);' in cs
# No user file is deleted during migration; malformed input must roll back.
assert 'File.Delete(legacy)' not in m and 'File.Move(legacy' not in m

# D03: strict UTF-8 must fail closed instead of silently replacing invalid legacy bytes.
# This is a SOURCE_ONLY contract, not a native Windows migration acceptance.
assert 'File.ReadLines(legacy, new UTF8Encoding(false, true))' in m
assert 'ex is DecoderFallbackException' in m
assert 'NOX_LEGACY_JSONL_ENCODING_HOLD' in m
assert m.index('tx.Rollback();') < m.index('NOX_LEGACY_JSONL_ENCODING_HOLD')
with tempfile.TemporaryDirectory() as bad_dir:
    bad = Path(bad_dir) / 'corrupted.jsonl'
    bad.write_bytes(b'{"prompt":"broken-\\xff","answer":"answer"}\n'.replace(b'\\xff', bytes([0xff])))
    assert '\ufffd' in bad.read_text(encoding='utf-8', errors='replace')
    try:
        bad.read_text(encoding='utf-8', errors='strict')
    except UnicodeDecodeError:
        pass
    else:
        raise AssertionError('malformed UTF-8 was accepted')

with tempfile.TemporaryDirectory() as folder:
    db=sqlite3.connect(Path(folder)/'memory.sqlite3')
    db.execute('CREATE TABLE chat_history(prompt TEXT,answer TEXT)')
    db.execute('CREATE TABLE imported_sources(source TEXT PRIMARY KEY,rows INTEGER)')
    db.execute("INSERT INTO chat_history VALUES('original','intact')")
    db.commit()
    for lines,valid in [(['{"prompt":"new","answer":"yes"}','invalid'],False),(['{"prompt":"new","answer":"yes"}'],True)]:
        db.execute('BEGIN')
        skips=0
        for line in lines:
            try:
                item=json.loads(line)
                db.execute('INSERT INTO chat_history VALUES(?,?)',(item['prompt'],item['answer']))
            except json.JSONDecodeError: skips+=1
        if skips: db.rollback()
        else:
            db.execute("INSERT INTO imported_sources VALUES('NOX_NEW_CHAT_JSONL_V1',1)")
            db.commit()
        assert (skips==0)==valid
        assert db.execute("SELECT answer FROM chat_history WHERE prompt='original'").fetchone()==('intact',)
        assert db.execute('SELECT COUNT(*) FROM imported_sources').fetchone()[0]==int(valid)
    db.close()
print('D03 R8 SOURCE_ONLY: checkpoint-before-import, rollback-and-receipt contract PASS')
