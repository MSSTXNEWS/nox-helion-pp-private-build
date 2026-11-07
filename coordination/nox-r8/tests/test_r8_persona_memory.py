"""D03 R8 original SQLite Persona and NO-LOSS source contract. No owner-PC claims."""
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

src = Path(__file__).resolve().parent / "src"
cs = (src / "MainWindow.xaml.cs").read_text(encoding="utf-8")
web = (src / "index.html").read_text(encoding="utf-8")
for guard in (
    'MigratePersonaStorage(db);',
    'CheckpointSqlite(db, "PRE_PERSONA_MIGRATION")',
    'CheckpointSqlite(db, "PRE_VUNEO_IMPORT")',
    'source.BackupDatabase(dest)', 'PRAGMA quick_check',
    'private static string Sha256File(string file)',
    'SHA256.HashData(stream)',
    'string sha = Sha256File(file);',
    'NOX_BACKUP_DESTINATION_EXISTS_HOLD',
    'NOX_BACKUP_DESTINATION_REPARSE_HOLD',
    'FileMode.CreateNew',
    'File.Move(stage, target);',
    'NOX_BACKUP_EXPORT_CHECKSUM_HOLD',
    'NOX_BACKUP_EXPORT_READBACK_HOLD',
    'NOX_PERSONA_GENERATION_ACTIVE_HOLD',
    'PersistChat(prompt, answer.ToString(), persona)',
    'BuildLocalContext(prompt, persona)',
    'FROM chat_history WHERE persona=$persona ORDER BY id DESC LIMIT 100',
    'FROM chat_history WHERE persona=$persona ORDER BY id DESC LIMIT 3',
    'FROM memory_notes WHERE persona=$persona ORDER BY id DESC LIMIT 6',
    'FROM memory_notes WHERE persona=$persona ORDER BY id DESC LIMIT 150',
    'DELETE FROM memory_notes WHERE id=$id AND persona=$persona',
    'SELECT timestamp,prompt,answer FROM chat_history',
    'SELECT created_at,title,content FROM memory_notes',
    'NOX_MEMORY_QUERY_LIMIT_HOLD',
    'prompt.Contains(query, StringComparison.OrdinalIgnoreCase)',
    'answer.Contains(query, StringComparison.OrdinalIgnoreCase)',
    'SELECT prompt,answer FROM chat_history WHERE persona=$persona ORDER BY id DESC LIMIT 600 OFFSET 3',
    'SELECT title,content FROM memory_notes WHERE persona=$persona ORDER BY id DESC LIMIT 300 OFFSET 6',
    'Send("persona.changed"',
    'if (consent != MessageBoxResult.Yes) return',
):
    assert guard in cs, guard
assert "case 'persona.changed':" in web

# D03 owner export safety: staging and SHA readback must precede a
# no-overwrite final rename. Existing backups must never be truncated.
export = cs.split('private void BackupLocalDatabase()', 1)[1].split('// An explicit native consent gate', 1)[0]
assert export.index('CheckpointSqlite(source, "OWNER_EXPORT")') < export.index('FileMode.CreateNew')
assert export.index('FileMode.CreateNew') < export.index('NOX_BACKUP_EXPORT_CHECKSUM_HOLD')
assert export.index('NOX_BACKUP_EXPORT_CHECKSUM_HOLD') < export.index('File.Move(stage, target);')
assert export.index('File.Move(stage, target);') < export.index('NOX_BACKUP_EXPORT_READBACK_HOLD')
assert 'OverwritePrompt = false' in export
assert 'DataSource = dialog.FileName' not in export
checkpoint = cs.split('private string CheckpointSqlite(', 1)[1].split('private static bool HasPersonaColumn(', 1)[0]
assert checkpoint.index('PRAGMA quick_check') < checkpoint.index('string sha = Sha256File(file);')
assert 'File.ReadAllBytes(file)' not in checkpoint

ddls = re.findall(r'cmd.CommandText = "(ALTER TABLE (?:chat_history|memory_notes) ADD COLUMN persona [^"]+)";', cs)
assert len(ddls) == 2, ddls
with tempfile.TemporaryDirectory() as temp:
    original = Path(temp) / "chat.sqlite3"
    checkpoint = Path(temp) / "prior.sqlite3"
    with closing(sqlite3.connect(original)) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE chat_history(id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, prompt TEXT NOT NULL, answer TEXT NOT NULL)')
        db.execute('CREATE TABLE memory_notes(id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL)')
        db.execute("INSERT INTO chat_history(timestamp,prompt,answer) VALUES('now','legacy','bytes')")
        db.execute("INSERT INTO memory_notes(created_at,title,content) VALUES('now','legacy','bytes')")
        db.commit()
        with closing(sqlite3.connect(checkpoint)) as snapshot:
            db.backup(snapshot)
        with closing(sqlite3.connect(checkpoint)) as proof:
            assert proof.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        with db:
            for ddl in ddls:
                db.execute(ddl)
        assert db.execute('SELECT prompt,answer,persona FROM chat_history').fetchone() == ('legacy','bytes','KV')
        assert db.execute('SELECT title,content,persona FROM memory_notes').fetchone() == ('legacy','bytes','KV')
        db.execute("INSERT INTO chat_history(timestamp,prompt,answer,persona) VALUES('now','AM','private','AM')")
        db.execute("INSERT INTO memory_notes(created_at,title,content,persona) VALUES('now','AM','private','AM')")
        db.commit()
        assert db.execute("SELECT prompt FROM chat_history WHERE persona='KV'").fetchall() == [('legacy',)]
        assert db.execute("SELECT prompt FROM chat_history WHERE persona='AM'").fetchall() == [('AM',)]
        assert db.execute("SELECT title FROM memory_notes WHERE persona='KV'").fetchall() == [('legacy',)]
        assert db.execute("DELETE FROM memory_notes WHERE id=1 AND persona='AM'").rowcount == 0
        assert db.execute("SELECT COUNT(*) FROM memory_notes").fetchone()[0] == 2
    with closing(sqlite3.connect(checkpoint)) as proof:
        assert proof.execute('SELECT COUNT(*) FROM chat_history').fetchone()[0] == 1
        assert proof.execute('SELECT COUNT(*) FROM memory_notes').fetchone()[0] == 1
print('D03 R8 SOURCE_ONLY: WAL snapshot, real SQLite legacy migration, KV/AM isolation, NO-LOSS PASS')

# Targeted D03 SOURCE_ONLY regression: Russian-case search and bounded,
# parameterized KV/AM RAG candidate fetch. Never touches owner's SQLite.
with tempfile.TemporaryDirectory() as temp:
    with closing(sqlite3.connect(Path(temp) / "isolated_rag.sqlite3")) as db:
        db.execute("CREATE TABLE chat_history(id INTEGER PRIMARY KEY, timestamp TEXT, prompt TEXT, answer TEXT, persona TEXT)")
        db.execute("CREATE TABLE memory_notes(id INTEGER PRIMARY KEY, created_at TEXT, title TEXT, content TEXT, persona TEXT)")
        for i in range(1, 9):
            db.execute("INSERT INTO chat_history VALUES(?,?,?,?,?)", (i,"now","recent" if i > 5 else "История ПРОЕКТ НОКС", "same persona", "KV"))
        db.execute("INSERT INTO chat_history VALUES(9,'now','СЕКРЕТ ПРОЕКТ НОКС','foreign','AM')")
        db.execute("INSERT INTO memory_notes VALUES(1,'now','ПРОЕКТ НОКС','старое знание','KV')")
        db.execute("INSERT INTO memory_notes VALUES(2,'now','СЕКРЕТ ПРОЕКТ НОКС','private','AM')")
        db.commit()
        older = db.execute("SELECT prompt,answer FROM chat_history WHERE persona=? ORDER BY id DESC LIMIT 600 OFFSET 3", ("KV",)).fetchall()
        matching = [(p,a) for p,a in older if "проект нокс" in (p+" "+a).casefold()]
        assert len(matching) == 5 and all("СЕКРЕТ" not in p for p,a in matching)
        search = db.execute("SELECT prompt,answer FROM chat_history WHERE persona=? ORDER BY id DESC LIMIT 1500", ("KV",)).fetchall()
        assert len([1 for p,a in search if "проект нокс" in (p+" "+a).casefold()]) == 5
        assert db.execute("SELECT COUNT(*) FROM memory_notes WHERE persona=?", ("KV",)).fetchone()[0] == 1
print("D03 R8 SOURCE_ONLY: Unicode recall, older same-Persona RAG and NO-LOSS PASS")

# D03 NO-LOSS owner routes consolidated onto current R8 native-Qwen base.
# This test is SOURCE_ONLY; native UI consent and actual Windows disks need physical QA.
delete_native = cs.split('private void DeleteNote(long id)', 1)[1].split('private void SaveFeedback(', 1)[0]
assert delete_native.index('MessageBox.Show(this') < delete_native.index('CheckpointSqlite(db, "PRE_NOTE_DELETE")')
assert delete_native.index('if (consent != MessageBoxResult.Yes)') < delete_native.index('CheckpointSqlite(db, "PRE_NOTE_DELETE")')
assert delete_native.index('CheckpointSqlite(db, "PRE_NOTE_DELETE")') < delete_native.index('db.BeginTransaction()')
assert 'id=$id AND persona=$persona' in delete_native
assert 'AND title=$title AND content=$content AND created_at=$created' in delete_native
assert 'NOX_NOTE_CHANGED_OR_FOREIGN_HOLD' in delete_native
assert delete_native.index('tx.Commit()') < delete_native.index('NOX_NOTE_DELETE_READBACK_HOLD')
assert 'notes.delete.receipt' in delete_native
doc_import = cs.split('private void ImportKnowledgeByDialog()', 1)[1].split('private void BackupLocalDatabase()', 1)[0]
assert doc_import.index('if (consent != MessageBoxResult.Yes) return;') < doc_import.index('CheckpointSqlite(db, "PRE_KNOWLEDGE_IMPORT")')
assert doc_import.index('CheckpointSqlite(db, "PRE_KNOWLEDGE_IMPORT")') < doc_import.index('knowledge.ImportFiles(files)')
assert 'File.Delete(' not in doc_import and 'File.Move(' not in doc_import
# Isolated SQLite oracle: denied consent/no backup failure may delete a note.
with tempfile.TemporaryDirectory() as temp:
    with closing(sqlite3.connect(Path(temp) / "owner_test.sqlite3")) as db:
        db.execute("CREATE TABLE memory_notes(id INTEGER PRIMARY KEY,created_at TEXT,title TEXT,content TEXT,persona TEXT)")
        db.execute("INSERT INTO memory_notes VALUES(1,'now','keep','original','KV')")
        db.execute("INSERT INTO memory_notes VALUES(2,'now','secret','private','AM')")
        db.commit()
        # A foreign Persona must never match the exact owner predicate.
        foreign = db.execute("""DELETE FROM memory_notes WHERE id=? AND persona=?
            AND title=? AND content=? AND created_at=?""", (2,"KV","secret","private","now"))
        assert foreign.rowcount == 0
        assert db.execute("SELECT COUNT(*) FROM memory_notes").fetchone()[0] == 2
        # A changed note must not be deleted using a stale pre-consent readback.
        db.execute("UPDATE memory_notes SET content='newer' WHERE id=1")
        db.commit()
        stale = db.execute("""DELETE FROM memory_notes WHERE id=? AND persona=?
            AND title=? AND content=? AND created_at=?""", (1,"KV","keep","original","now"))
        assert stale.rowcount == 0
        assert db.execute("SELECT content FROM memory_notes WHERE id=1").fetchone()[0] == "newer"
print("D03 R8 SOURCE_ONLY: native owner consent, preimage, exact-row delete, isolated SQLite preservation PASS")
