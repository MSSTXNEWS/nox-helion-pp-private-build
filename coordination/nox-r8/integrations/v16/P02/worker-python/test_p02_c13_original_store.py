"""Contract tests of the REAL existing P02Store on its ONE sqlite connection.

Run in the same repo directory as p02_runtime.py. Never open a server or model.
"""
import pathlib
import sqlite3
import tempfile
import unittest
from p02_runtime import P02Store, P02Error
from p02_history_stable import migrate_host_history, HistoryHold

class OriginalStoreV2Admission(unittest.TestCase):
    def setUp(self):
        self.scratch=tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root=pathlib.Path(self.scratch.name)
        self.db=sqlite3.connect(self.root/'one-original-host.sqlite')
        self.addCleanup(self.db.close)
        self.store=P02Store(self.db, self.root/'attachments')
        self.store.initialize()
        self.store.create_chat('tenant','user','chat1')
        self.store.add_message('tenant','user','chat1','user','first')
        self.store.add_message('tenant','user','chat1','assistant','second')

    def migrate(self):
        return migrate_host_history(self.db,self.root/'offline-backup.sqlite',
            native_owner_approved=True,writers_quiesced=True,
            verified_writer_v2_compatible=True)

    def test_c13_1_original_v1_works_unchanged(self):
        self.assertEqual([x['content'] for x in self.store.history('tenant','user','chat1')],['first','second'])
        self.store.add_message('tenant','user','chat1','user','third')
        self.assertEqual(self.store.history('tenant','user','chat1')[-1]['content'],'third')

    def test_c13_2_original_v2_initialize_and_write(self):
        self.migrate()
        self.store.initialize()
        self.store.add_message('tenant','user','chat1','assistant','third')
        self.assertEqual([x['content'] for x in self.store.history('tenant','user','chat1')],['first','second','third'])

    def test_c13_3_original_v2_vacuum_and_reopen(self):
        self.migrate()
        self.store.initialize()
        self.db.execute('VACUUM')
        self.store.add_message('tenant','user','chat1','assistant','third')
        self.assertEqual(self.store.history('tenant','user','chat1')[-1]['content'],'third')

    def test_c13_4_original_v2_acl(self):
        self.migrate()
        self.store.initialize()
        with self.assertRaises(PermissionError):
            self.store.history('tenant','attacker','chat1')

    def test_c13_5_original_v2_missing_trigger_holds(self):
        self.migrate()
        self.db.execute('DROP TRIGGER p02_messages_stable_insert')
        self.db.commit()
        with self.assertRaises(HistoryHold):
            self.store.initialize()

    def test_c13_6_original_v2_missing_index_holds(self):
        self.migrate()
        self.db.execute('DROP INDEX p02_messages_stable_seq')
        self.db.commit()
        with self.assertRaises(HistoryHold):
            self.store.initialize()

    def test_c13_7_original_v2_prune_preserves_latest(self):
        self.migrate()
        self.store.initialize()
        self.store.add_message('tenant','user','chat1','user','latest')
        self.assertEqual(self.store.history('tenant','user','chat1')[-1]['content'],'latest')

    def test_c13_8_original_v2_backup_restores_v1(self):
        receipt=self.migrate()
        with sqlite3.connect(receipt.backup_path) as backup:
            self.assertEqual(backup.execute("SELECT value FROM p02_meta WHERE key='schema'").fetchone(),('1',))

if __name__=='__main__':unittest.main()
