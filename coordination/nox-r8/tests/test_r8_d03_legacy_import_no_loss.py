"""D03 R8 native SQLite legacy import: structural source guard + isolated SQLite rollback oracle."""
from pathlib import Path
import sqlite3, tempfile, json
cs=(Path(__file__).parent/'src'/'MainWindow.xaml.cs').read_text(encoding='utf8')
m=cs.split('private void ImportLegacyJsonlIfNeeded(',1)[1].split('private async void OnMessage(',1)[0]
assert m.index('CheckpointSqlite(db, "PRE_LEGACY_IMPORT")') < m.index('db.BeginTransaction()')
assert m.index('if (skipped != 0') < m.index('receipt.CommandText') < m.index('tx.Commit()')
for x in ['FileAttributes.ReparsePoint','shaPrefix + sourceSha','NOX_LEGACY_JSONL_INCOMPLETE_HOLD','NOX_LEGACY_JSONL_CHANGED_AFTER_IMPORT_HOLD','NOX_LEGACY_JSONL_CHANGED_DURING_IMPORT_HOLD','tx.Rollback();','File.ReadLines(legacy)','INSERT INTO imported_sources(source,imported_at,rows)']:
    assert x in m,x
assert 'if (legacyImportHold != null) Send("notice", legacyImportHold);' in cs
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
