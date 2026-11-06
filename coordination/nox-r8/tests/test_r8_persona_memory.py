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
    'NOX_PERSONA_GENERATION_ACTIVE_HOLD',
    'PersistChat(prompt, answer.ToString(), persona)',
    'BuildLocalContext(prompt, persona)',
    'FROM chat_history WHERE persona=$persona ORDER BY id DESC LIMIT 100',
    'FROM chat_history WHERE persona=$persona ORDER BY id DESC LIMIT 3',
    'FROM memory_notes WHERE persona=$persona ORDER BY id DESC LIMIT 6',
    'FROM memory_notes WHERE persona=$persona ORDER BY id DESC LIMIT 150',
    'DELETE FROM memory_notes WHERE id=$id AND persona=$persona',
    'persona=$persona AND (instr(lower(prompt)',
    'persona=$persona AND (instr(lower(title)',
    'Send("persona.changed"',
    'if (consent != MessageBoxResult.Yes) return',
):
    assert guard in cs, guard
assert "case 'persona.changed':" in web

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
