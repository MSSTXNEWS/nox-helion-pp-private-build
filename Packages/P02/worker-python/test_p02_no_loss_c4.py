"""P02 C4 targeted NO-LOSS security regression. Synthetic fixtures only."""
import io
import os
import pathlib
import sqlite3
import tempfile
import unittest
import uuid
from p02_runtime import P02Store, P02Error
from p02_host_admission import NativeHostBinding, P02EventRelay, P02_TYPES
from p02_capabilities import Identity

class StorageNoLoss(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.temp.name)
        self.db=sqlite3.connect(':memory:')
        self.s=P02Store(self.db,self.root/'app')
        self.s.initialize()
        self.s.create_chat('tenant','alice','chat')
    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_01_foreign_keys_stay_enabled_after_host_changes_connection(self):
        self.db.execute('PRAGMA foreign_keys=OFF')
        self.assertEqual(self.db.execute('PRAGMA foreign_keys').fetchone(),(0,))
        self.s.add_message('tenant','alice','chat','user','hello')
        self.assertEqual(self.db.execute('PRAGMA foreign_keys').fetchone(),(1,))
        self.s.delete_chat('tenant','alice','chat')
        self.assertEqual(self.db.execute('SELECT count(*) FROM p02_messages').fetchone(),(0,))

    def test_02_schema_foreign_key_drift_fails_closed(self):
        self.db.execute('PRAGMA foreign_keys=OFF')
        self.db.execute('DROP TABLE p02_messages')
        self.db.execute('CREATE TABLE p02_messages(id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at INTEGER NOT NULL)')
        self.db.commit()
        with self.assertRaisesRegex(P02Error,'P02_SCHEMA_FOREIGN_KEY_DRIFT'):
            self.s.initialize()
        self.assertTrue('p02_messages' in self.s.host_schema_inventory())

    def test_03_partial_schema_drift_no_automatic_repair(self):
        self.db.execute('DROP TABLE p02_meta')
        self.db.commit()
        tables_before=self.s.host_schema_inventory()
        with self.assertRaisesRegex(P02Error,'INCOMPLETE_P02_SCHEMA'):
            self.s.initialize()
        self.assertEqual(tables_before,self.s.host_schema_inventory())

    def test_04_blob_is_never_overwritten_on_storage_id_collision(self):
        """Patch UUID in runtime, force same destination, verify prior bytes survive."""
        from unittest.mock import patch
        fixed='a'*32
        original=b'important-user-data'
        path=self.s.blobs/(fixed+'.blob')
        path.write_bytes(original)
        class ConstantUUID:
            hex=fixed
        # First UUID=storage, after successful link would be record ID.
        with patch('p02_runtime.uuid.uuid4',return_value=ConstantUUID()):
            with self.assertRaises(FileExistsError):
                self.s.store_file('tenant','alice','chat','application/pdf',io.BytesIO(b'%PDF-1.4\nfixture'))
        self.assertEqual(path.read_bytes(),original)
        self.assertFalse(list(self.s.staging.iterdir()))

    def test_05_storage_symlink_after_initialization_denied(self):
        # Simulate a local attacker replacing an app-owned directory with link.
        outside=self.root/'other';outside.mkdir()
        self.s.staging.rmdir()
        try:
            self.s.staging.symlink_to(outside,target_is_directory=True)
        except (NotImplementedError,OSError):
            self.skipTest('OS symlinks are unavailable')
        with self.assertRaisesRegex(P02Error,'ATTACHMENT_STORAGE_OUTSIDE_APPROVED_ROOT'):
            self.s.store_file('tenant','alice','chat','application/pdf',io.BytesIO(b'%PDF-1.4\nfixture'))
        self.assertFalse(list(outside.iterdir()))

    def test_06_existing_symlinked_blob_root_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            root=self.root/'second';root.mkdir()
            try:
                (root/'stored').symlink_to(other,target_is_directory=True)
            except (NotImplementedError,OSError):
                self.skipTest('OS symlinks are unavailable')
            with self.assertRaisesRegex(P02Error,'ATTACHMENT_STORAGE_SYMLINK_DENIED'):
                P02Store(self.db,root)

class EventNoLoss(unittest.TestCase):
    def make_relay(self):
        mapped={x:'host.'+x for x in P02_TYPES}
        seen=[]
        binding=NativeHostBinding(Identity('t','u','core','persona','sess'),True,
             frozenset(mapped.values()),mapped,lambda kind,payload: seen.append((kind,payload)))
        return P02EventRelay(binding),seen

    def test_07_event_extra_fields_rejected_instead_of_native_forward(self):
        relay,seen=self.make_relay();rid=uuid.uuid4().hex
        with self.assertRaises(PermissionError):
            relay.relay({'type':'chat.start','run_id':rid,'model':'installed','host_command':'delete'})
        self.assertEqual(seen,[])
        relay.relay({'type':'chat.start','run_id':rid,'model':'installed'})
        with self.assertRaises(PermissionError):
            relay.relay({'type':'chat.delta','run_id':rid,'text':'OK','principal':{'id':'other'}})
        self.assertEqual(len(seen),1)

    def test_08_event_sources_nested_privileges_fail_closed(self):
        relay,seen=self.make_relay();rid=uuid.uuid4().hex
        relay.relay({'type':'chat.start','run_id':rid,'model':'installed'})
        with self.assertRaisesRegex(P02Error,'CHAT_SOURCES_SCHEMA_INVALID'):
            relay.relay({'type':'chat.sources','run_id':rid,'sources':[
                {'source_id':'x','title':'doc','api_key':'secret'}]})
        self.assertEqual(len(seen),1)

    def test_09_non_json_extra_object_never_reaches_host_publisher(self):
        relay,seen=self.make_relay();rid=uuid.uuid4().hex
        relay.relay({'type':'chat.start','run_id':rid,'model':'installed'})
        with self.assertRaisesRegex(PermissionError,'EVENT_PRIVILEGE_FIELDS_FORBIDDEN'):
            relay.relay({'type':'chat.delta','run_id':rid,'text':'ok','untrusted':object()})
        self.assertEqual(len(seen),1)

    def test_10_missing_error_code_is_rejected_without_fake_ack(self):
        relay,seen=self.make_relay();rid=uuid.uuid4().hex
        relay.relay({'type':'chat.start','run_id':rid,'model':'installed'})
        with self.assertRaisesRegex(P02Error,'CHAT_ERROR_SCHEMA_INVALID'):
            relay.relay({'type':'chat.error','run_id':rid,'detail':'error'})
        self.assertEqual(len(seen),1)

if __name__=='__main__':unittest.main(verbosity=2)
