"""A5 existing S03 actor contract, sqlite memory only for tests."""
import hashlib
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from src.nox_selfbuilder.original_store_adapter import OriginalStoreChatAdapter, StoreActorHold

CONTENT='reviewed knowledge source'
EVIDENCE={'status':'NATIVE_S03_RIGHTS_REVIEWED','owner_consented':True,
          'source_sha256':'a'*64,'text_sha256':hashlib.sha256(CONTENT.encode()).hexdigest(),
          'rights_receipt_id':'OWNER-REVIEW-01'}

class S03PostCommitTests(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(':memory:')
        self.conn.execute('CREATE TABLE entries (id TEXT PRIMARY KEY, body TEXT)')
        self.store=SimpleNamespace(conn=self.conn)
        self.adapter=OriginalStoreChatAdapter.__new__(OriginalStoreChatAdapter)
        self.adapter.actor=SimpleNamespace(call=lambda cb:cb(self.store))
        self.stopped=False
        self.granted=True
    def tearDown(self):self.conn.close()
    def find(self, store, row):
        cur=store.conn.execute('SELECT body FROM entries WHERE id=?',(row['source_sha256'],))
        item=cur.fetchone()
        if item is None:return None
        return row if item[0]==row['content'] else {'content':item[0]}
    def write(self,store,row):
        store.conn.execute('INSERT INTO entries VALUES (?,?)',
                          (row['source_sha256'],row['content']))
    def call(self,*,find=None,write=None):
        with patch.object(OriginalStoreChatAdapter,'_scope',return_value=('project','core','chat')):
            return self.adapter.ingest_verified_knowledge('local','native','default',
                evidence=EVIDENCE,text=CONTENT,authorize=lambda:self.granted,
                stopped=lambda:self.stopped,find_saved=find or self.find,
                write_saved=write or self.write)
    def test_real_sqlite_postcommit_and_dedup(self):
        result=self.call()
        self.assertEqual(result['state'],'S03_COMMITTED_READBACK')
        self.assertFalse(self.conn.in_transaction)
        self.assertEqual(self.call()['state'],'S03_DEDUPLICATED_READBACK')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM entries').fetchone()[0],1)
    def test_native_stop_rolls_back_before_commit(self):
        def write_then_stop(store,row):
            self.write(store,row)
            self.stopped=True
        with self.assertRaises(PermissionError):
            self.call(write=write_then_stop)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM entries').fetchone()[0],0)
    def test_readback_failure_never_reports_ack(self):
        read_count=[0]
        def bad_after_commit(store,row):
            read_count[0]+=1
            return None if read_count[0]>=3 else self.find(store,row)
        with self.assertRaisesRegex(StoreActorHold,'POSTCOMMIT_READBACK'):
            self.call(find=bad_after_commit)
        # SQLite may already be committed: never assert a false rollback.
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM entries').fetchone()[0],1)

if __name__ == '__main__':unittest.main()
