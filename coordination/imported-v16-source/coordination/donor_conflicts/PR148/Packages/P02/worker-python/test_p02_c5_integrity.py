"""C5 additive synthetic security regressions; no real user data or external calls."""
import io
import os
import pathlib
import sqlite3
import tempfile
import unittest
import uuid
from unittest import mock
from p02_runtime import P02Store, P02Error
from p02_host_admission import NativeHostBinding, P02EventRelay, P02_TYPES
from p02_capabilities import Identity


class C5Safety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.db = sqlite3.connect(':memory:')
        self.store = P02Store(self.db, self.base/'app')
        self.store.initialize()
        self.store.create_chat('tenant', 'alice', 'chat')

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_01_ddl_atomic_rollback_if_schema_create_fails(self):
        class Broken(sqlite3.Connection):
            def execute(self, sql, *args, **kwargs):
                if str(sql).lstrip().startswith('CREATE INDEX IF NOT EXISTS p02_messages'):
                    raise RuntimeError('simulated power loss at DDL')
                return super().execute(sql, *args, **kwargs)
        db = sqlite3.connect(':memory:', factory=Broken)
        with self.assertRaisesRegex(RuntimeError, 'simulated power loss'):
            with tempfile.TemporaryDirectory() as path:
                P02Store(db, path).initialize()
        self.assertEqual(db.execute('SELECT name FROM sqlite_master WHERE name LIKE "p02_%"').fetchall(), [])
        db.close()

    def test_02_existing_schema_missing_primary_key_stays_untouched(self):
        self.db.execute('PRAGMA foreign_keys=OFF')
        self.db.execute('DROP TABLE p02_messages')
        self.db.execute('CREATE TABLE p02_messages (id TEXT, chat_id TEXT NOT NULL REFERENCES p02_chats(id) ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, created_at INTEGER NOT NULL)')
        self.db.commit()
        with self.assertRaisesRegex(P02Error, 'P02_SCHEMA_PRIMARY_KEY_DRIFT'):
            self.store.initialize()
        self.assertEqual(self.db.execute('PRAGMA table_info(p02_messages)').fetchall()[0][-1],0)

    def test_03_storage_uniqueness_drift_stops_admission(self):
        self.db.execute('PRAGMA foreign_keys=OFF')
        self.db.execute('DROP TABLE p02_attachments')
        self.db.execute('CREATE TABLE p02_attachments(id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES p02_chats(id) ON DELETE CASCADE, storage TEXT NOT NULL, sha256 TEXT NOT NULL, mime TEXT NOT NULL, bytes INTEGER NOT NULL, created_at INTEGER NOT NULL)')
        self.db.commit()
        with self.assertRaisesRegex(P02Error, 'P02_STORAGE_UNIQUENESS_DRIFT'):
            self.store.initialize()

    def test_04_root_symlink_refused_before_any_upload(self):
        other = self.base/'other';other.mkdir()
        link = self.base/'linked'
        try:
            link.symlink_to(other, target_is_directory=True)
        except (OSError,NotImplementedError):
            self.skipTest('symlink privilege unavailable')
        with self.assertRaisesRegex(P02Error, 'ATTACHMENT_ROOT_SYMLINK_DENIED'):
            P02Store(self.db, link)

    def test_05_stream_none_is_error_not_successful_EOF(self):
        class Broken:
            def read(self, n): return None
        with self.assertRaisesRegex(P02Error, 'ATTACHMENT_STREAM_INVALID_CHUNK'):
            self.store.store_file('tenant','alice','chat','application/pdf',Broken())
        self.assertFalse(list(self.store.staging.iterdir()))

    def test_05b_unauthorized_stream_never_read_or_staged(self):
        class Stream:
            def __init__(self): self.calls = 0
            def read(self, n):
                self.calls += 1
                return b'%PDF-1.7\n'
        stream = Stream()
        with self.assertRaises(PermissionError):
            self.store.store_file('tenant', 'mallory', 'chat', 'application/pdf', stream)
        self.assertEqual(stream.calls, 0)
        self.assertFalse(list(self.store.staging.iterdir()))

    def test_06_stream_over_read_quota_disallowed(self):
        class Broken:
            def read(self,n): return b'x'*(n+1)
        with self.assertRaisesRegex(P02Error, 'ATTACHMENT_STREAM_INVALID_CHUNK'):
            self.store.store_file('tenant','alice','chat','application/pdf',Broken())
        self.assertFalse(list(self.store.staging.iterdir()))

    def test_07_text_nul_after_first_header_rejected(self):
        with self.assertRaisesRegex(P02Error, 'ATTACHMENT_PLAINTEXT_NUL_DENIED'):
            self.store.store_file('tenant','alice','chat','text/plain', io.BytesIO(b'A'*70000+b'\0'))

    def test_08_text_truncated_multibyte_rejected(self):
        with self.assertRaisesRegex(P02Error, 'ATTACHMENT_PLAINTEXT_UTF8_REQUIRED'):
            self.store.store_file('tenant','alice','chat','text/plain',io.BytesIO(b'hello\xe2\x82'))
        ack=self.store.store_file('tenant','alice','chat','text/plain',io.BytesIO(b'hello'*13107+'\N{EURO SIGN}'.encode()))
        self.assertEqual(self.store.read_file('tenant','alice','chat',ack['stored_id'])[-3:],b'\xe2\x82\xac')

    def test_09_hardlink_alias_read_and_gc_fail_closed(self):
        ack = self.store.store_file('tenant','alice','chat','application/pdf',io.BytesIO(b'%PDF-1.7\nfixture'))
        (storage,) = self.db.execute('SELECT storage FROM p02_attachments').fetchone()
        blob=self.store.blobs/(storage+'.blob');link=self.base/'external_alias'
        try:
            os.link(blob,link)
        except (NotImplementedError,OSError):
            self.skipTest('Hardlinks not available')
        with self.assertRaisesRegex(P02Error,'ATTACHMENT_HARDLINK_ALIAS_DENIED'):
            self.store.read_file('tenant','alice','chat',ack['stored_id'])
        self.store.delete_attachment('tenant','alice','chat',ack['stored_id'])
        with self.assertRaisesRegex(P02Error,'ATTACHMENT_GC_UNSAFE_FILE_TYPE'):
            self.store.collect_garbage()
        self.assertTrue(blob.exists())
        link.unlink()
        self.assertEqual(self.store.collect_garbage(),1)

    def _relay(self):
        allowed = {typ:'native.'+typ for typ in P02_TYPES}
        calls=[]
        bind=NativeHostBinding(Identity('t','u','core','persona','session'), True,
          frozenset(allowed.values()),allowed,lambda typ,data: calls.append((typ,data)))
        relay=P02EventRelay(bind);run=uuid.uuid4().hex
        relay.relay({'type':'chat.start','run_id':run,'model':'installed'})
        return relay,run,calls

    def test_10_boolean_complete_and_untrusted_citation_url_denied(self):
        relay,run,calls=self._relay()
        with self.assertRaisesRegex(P02Error,'CHAT_COMPLETE_INVALID'):
            relay.relay({'type':'chat.complete','run_id':run,'chars':True})
        with self.assertRaisesRegex(P02Error,'CHAT_SOURCE_URL_FORBIDDEN'):
            relay.relay({'type':'chat.sources','run_id':run,'sources':[{'source_id':'1','title':'doc','url':'javascript:alert(1)'}]})
        self.assertEqual(len(calls),1)

if __name__ == '__main__':
    unittest.main(verbosity=2)
