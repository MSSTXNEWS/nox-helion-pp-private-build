"""P02 C2 real original P02Store SQLite STOP precommit regression; no installed E07."""
import sqlite3, tempfile, threading, unittest
from pathlib import Path
from p02_runtime import P02Store, Cancelled
from p02_chat_bridge import ChatBridge

class NativeOwnerSqliteCommitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=sqlite3.connect(':memory:')
        self.store=P02Store(self.db,Path(self.temp.name)/'att')
        self.store.initialize()
        self.store.create_chat('tenant','owner','chat')
        self.stop=threading.Event()
        self.db.create_function('stop_p02_insert',0,lambda: self.stop.set() or 0)
    def tearDown(self):
        self.db.close()
        self.temp.cleanup()
    def arm(self,role=None):
        condition='' if role is None else " WHEN NEW.role='"+role+"'"
        self.db.execute('CREATE TEMP TRIGGER p02_stop AFTER INSERT ON p02_messages'+
                        condition+' BEGIN SELECT stop_p02_insert(); END')
    def count(self):
        return self.db.execute('SELECT COUNT(*) FROM p02_messages').fetchone()[0]
    def test_01_original_legacy_writer_unchanged(self):
        self.store.add_message('tenant','owner','chat','user','hello')
        self.assertEqual(self.count(),1)
    def test_02_stop_during_sqlite_insert_rolls_back_user(self):
        self.arm('user')
        with self.assertRaisesRegex(Cancelled,'STOP before P02 SQLite commit'):
            self.store.add_message('tenant','owner','chat','user','hello',stop=self.stop)
        self.assertEqual(self.count(),0)
        self.assertFalse(self.db.in_transaction)
    def test_03_real_bridge_cannot_start_cancelled_persist(self):
        class FakeModel:
            def models(self): return ['local']
            def stream(self,*args): raise AssertionError('No model after STOP')
        self.arm('user')
        with self.assertRaises(Cancelled):
            list(ChatBridge(self.store,FakeModel()).send(
                'tenant','owner','chat','local','hello',self.stop))
        self.assertEqual(self.count(),0)
    def test_04_assistant_stop_rolls_back_without_complete(self):
        class FakeModel:
            def models(self): return ['local']
            def stream(self,model,messages,stop):
                yield {'delta':'OK','done':False}
                yield {'delta':'','done':True}
        self.arm('assistant')
        frames=list(ChatBridge(self.store,FakeModel()).send(
            'tenant','owner','chat','local','hello',self.stop))
        self.assertEqual(frames[-1]['type'],'chat.error')
        self.assertEqual(frames[-1]['code'],'STOP')
        self.assertNotIn('chat.complete',[x['type'] for x in frames])
        self.assertEqual(self.count(),1)
        self.assertEqual(self.store.history('tenant','owner','chat')[0]['role'],'user')
        self.assertFalse(self.db.in_transaction)
    def test_05_foreign_owner_still_denied(self):
        with self.assertRaises(PermissionError):
            self.store.add_message('tenant','foreign','chat','user','hello',stop=self.stop)
        self.assertEqual(self.count(),0)
    def test_06_stop_before_begin_makes_no_write(self):
        self.stop.set()
        with self.assertRaises(Cancelled):
            self.store.add_message('tenant','owner','chat','user','hello',stop=self.stop)
        self.assertEqual(self.count(),0)
if __name__=='__main__':
    unittest.main(verbosity=2)
