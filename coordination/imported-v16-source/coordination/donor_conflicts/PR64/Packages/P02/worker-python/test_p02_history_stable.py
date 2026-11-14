"""Real SQLite file/backup/VACUUM tests. No model, voice or network fixtures."""
import pathlib
import sqlite3
import tempfile
import unittest
import uuid
from p02_history_stable import migrate_host_history, stable_history, HistoryHold

SCHEMA = """
CREATE TABLE p02_chats(id TEXT PRIMARY KEY,tenant TEXT NOT NULL,principal TEXT NOT NULL,created_at INTEGER NOT NULL);
CREATE TABLE p02_messages(id TEXT PRIMARY KEY,chat_id TEXT NOT NULL REFERENCES p02_chats(id) ON DELETE CASCADE,role TEXT,content TEXT,created_at INTEGER);
CREATE TABLE p02_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT INTO p02_meta VALUES ('schema','1');
"""

class V2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.db = sqlite3.connect(self.root/'canonical-host.sqlite')
        self.addCleanup(self.db.close)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript(SCHEMA)
        self.db.execute('INSERT INTO p02_chats VALUES (?,?,?,?)',('c','t','u',1))
        for i,role in enumerate(['user','assistant','user']):
            self.db.execute('INSERT INTO p02_messages VALUES(?,?,?,?,?)',
                            (uuid.uuid4().hex,'c',role,str(i),100))
        self.db.commit()
        self.backup=self.root/'protected-backup.sqlite'

    def migrate(self):
        return migrate_host_history(self.db,self.backup,native_owner_approved=True,writers_quiesced=True,verified_writer_v2_compatible=True)

    def test_00_blocks_old_positional_insert_writer(self):
        with self.assertRaisesRegex(HistoryHold, 'ORIGINAL_P02_WRITER_V2_COMPATIBILITY_NOT_VERIFIED'):
            migrate_host_history(self.db,self.backup,native_owner_approved=True,writers_quiesced=True)
        self.assertFalse(self.backup.exists())
    def test_00b_requires_foreign_keys(self):
        self.db.execute('PRAGMA foreign_keys=OFF')
        with self.assertRaisesRegex(HistoryHold, 'P02_FOREIGN_KEYS_DISABLED'):self.migrate()
        self.assertFalse(self.backup.exists())
    def test_00c_rejects_corrupt_v2_contract(self):
        self.migrate()
        self.db.execute('DROP TRIGGER p02_messages_stable_insert')
        self.db.commit()
        with self.assertRaisesRegex(HistoryHold,'P02_V2_SEQUENCE_CONTRACT_HOLD'):
            stable_history(self.db,'t','u','c')
    def test_00d_old_positional_insert_breaks_without_fix(self):
        self.migrate()
        with self.assertRaises(sqlite3.OperationalError):
            self.db.execute('INSERT INTO p02_messages VALUES(?,?,?,?,?)',('n','c','user','new',101))
        self.db.rollback()
    def test_01_requires_consent(self):
        with self.assertRaises(HistoryHold):
            migrate_host_history(self.db,self.backup,native_owner_approved=False,writers_quiesced=True)
    def test_02_requires_quiescence(self):
        with self.assertRaises(HistoryHold):
            migrate_host_history(self.db,self.backup,native_owner_approved=True,writers_quiesced=False)
    def test_03_never_overwrites_backup(self):
        self.backup.write_bytes(b'important')
        with self.assertRaises(HistoryHold):self.migrate()
        self.assertEqual(self.backup.read_bytes(),b'important')
    def test_04_never_commits_foreign_transaction(self):
        self.db.execute("INSERT INTO p02_chats VALUES('other','t','u',1)")
        with self.assertRaises(HistoryHold):self.migrate()
        self.db.rollback()
        self.assertFalse(self.backup.exists())
    def test_05_migration_and_checksum(self):
        receipt=self.migrate()
        self.assertEqual(receipt.messages_migrated,3)
        self.assertEqual(len(receipt.backup_sha256),64)
        self.assertEqual(self.db.execute("SELECT value FROM p02_meta WHERE key='schema'").fetchone(),('2',))
    def test_06_same_second_order(self):
        self.migrate()
        self.assertEqual([x['content'] for x in stable_history(self.db,'t','u','c')],['0','1','2'])
    def test_07_vacuum_does_not_reorder(self):
        self.migrate()
        self.db.execute("DELETE FROM p02_messages WHERE content='1'");self.db.commit()
        self.db.execute('VACUUM')
        self.assertEqual([x['content'] for x in stable_history(self.db,'t','u','c')],['0','2'])
    def test_08_new_messages_stable(self):
        self.migrate()
        self.db.execute('INSERT INTO p02_messages(id,chat_id,role,content,created_at) VALUES(?,?,?,?,?)',
                        ('new','c','assistant','new',100));self.db.commit()
        self.assertEqual([x['content'] for x in stable_history(self.db,'t','u','c')],['0','1','2','new'])
    def test_09_acl_denies_foreign_principal(self):
        self.migrate()
        with self.assertRaises(PermissionError):stable_history(self.db,'t','attacker','c')
    def test_10_rejects_bool_limits(self):
        self.migrate()
        with self.assertRaises(ValueError):stable_history(self.db,'t','u','c',True)
    def test_11_backup_restores_original_v1(self):
        self.migrate()
        with sqlite3.connect(self.backup) as old:
            self.assertEqual(old.execute("SELECT value FROM p02_meta WHERE key='schema'").fetchone(),('1',))
            self.assertEqual(old.execute('SELECT count(*) FROM p02_messages').fetchone()[0],3)
    def test_12_never_silently_migrates_v1(self):
        with self.assertRaises(HistoryHold):stable_history(self.db,'t','u','c')
    def test_13_does_not_migrate_twice(self):
        self.migrate()
        another=self.root/'backup-second.sqlite'
        with self.assertRaises(HistoryHold):
            migrate_host_history(self.db,another,native_owner_approved=True,writers_quiesced=True)
    def test_14_incompatible_schema_holds(self):
        self.db.execute('ALTER TABLE p02_messages ADD COLUMN unusual TEXT');self.db.commit()
        with self.assertRaises(HistoryHold):self.migrate()
    def test_15_rejects_parallel_original_history(self):
        self.db.execute('CREATE TABLE chats(id TEXT)');self.db.commit()
        with self.assertRaises(HistoryHold):self.migrate()
        self.assertFalse(self.backup.exists())
    def test_16_unknown_schema_no_empty_backup(self):
        self.db.execute('ALTER TABLE p02_messages ADD COLUMN unknown_extra TEXT');self.db.commit()
        with self.assertRaises(HistoryHold):self.migrate()
        self.assertFalse(self.backup.exists())
    def test_17_tail_read_last_two(self):
        self.migrate()
        self.assertEqual([x['content'] for x in stable_history(self.db,'t','u','c',2)],['1','2'])

if __name__ == '__main__':unittest.main()
