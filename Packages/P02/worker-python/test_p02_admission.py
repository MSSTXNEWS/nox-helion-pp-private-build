"""Fast synthetic safety fixtures. No providers, external network or production DB."""
import sqlite3
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from p02_runtime import P02Store, P02Error
from p02_capabilities import Identity
from p02_host_admission import NativeHostBinding, P02EventRelay, P02_TYPES

class SharedDatabaseAdmission(unittest.TestCase):
    def test_unknown_host_schema_holds_without_creating_parallel_history(self):
        con = sqlite3.connect(':memory:')
        con.execute('CREATE TABLE custom_history(ticket INTEGER)')
        with tempfile.TemporaryDirectory() as d:
            store = P02Store(con, d)
            before = store.host_schema_inventory()
            with self.assertRaisesRegex(P02Error,'HOST_SCHEMA_REVIEW_REQUIRED'):
                store.initialize()
            self.assertEqual(store.host_schema_inventory(), before)
        con.close()

    def test_approved_unrelated_host_table_can_share_same_connection(self):
        con = sqlite3.connect(':memory:')
        con.execute('CREATE TABLE app_settings(key TEXT)')
        with tempfile.TemporaryDirectory() as d:
            store = P02Store(con, d, approved_host_tables=frozenset({'app_settings'}))
            store.initialize()
            store.create_chat('tenant', 'owner', 'chat')
            self.assertIn('app_settings', store.host_schema_inventory())
            self.assertIn('p02_chats', store.host_schema_inventory())
        con.close()

    def test_host_transaction_never_silently_committed(self):
        con = sqlite3.connect(':memory:')
        with tempfile.TemporaryDirectory() as d:
            store = P02Store(con,d)
            store.initialize()
            con.execute("INSERT INTO p02_chats VALUES ('pending','a','b',1)")
            self.assertTrue(con.in_transaction)
            with self.assertRaisesRegex(P02Error,'HOST_SQLITE_TRANSACTION_ACTIVE'):
                store.create_chat('a','b','other')
            con.rollback()
            self.assertIsNone(con.execute('SELECT id FROM p02_chats WHERE id=?',('pending',)).fetchone())
        con.close()

    def test_unrecognized_schema_version_preserved_without_new_tables(self):
        con=sqlite3.connect(':memory:')
        con.execute('CREATE TABLE p02_meta(key TEXT PRIMARY KEY,value TEXT)')
        con.execute("INSERT INTO p02_meta VALUES('schema','999')")
        con.commit()
        with tempfile.TemporaryDirectory() as d:
            store=P02Store(con,d)
            with self.assertRaisesRegex(P02Error,'downgrade'):
                store.initialize()
            self.assertEqual(store.host_schema_inventory(),('p02_meta',))
            self.assertEqual(con.execute('SELECT value FROM p02_meta').fetchone(),('999',))
        con.close()

    def test_partial_p02_schema_refuses_repair_without_data_loss(self):
        con = sqlite3.connect(':memory:')
        con.execute('CREATE TABLE p02_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        con.execute("INSERT INTO p02_meta VALUES('schema','1')")
        con.commit()
        with tempfile.TemporaryDirectory() as d:
            store = P02Store(con,d)
            before = store.host_schema_inventory()
            with self.assertRaisesRegex(P02Error,'INCOMPLETE_P02_SCHEMA'):
                store.initialize()
            self.assertEqual(before,store.host_schema_inventory())
            self.assertEqual(con.execute('SELECT value FROM p02_meta').fetchone(),('1',))
        con.close()

    def test_existing_schema_columns_mismatch_fails_without_rewriting(self):
        con=sqlite3.connect(':memory:')
        with tempfile.TemporaryDirectory() as d:
            store=P02Store(con,d)
            store.initialize()
            con.execute('ALTER TABLE p02_messages ADD COLUMN unexpected TEXT')
            con.commit()
            before=store.host_schema_inventory()
            with self.assertRaisesRegex(P02Error,'P02_SCHEMA_COLUMNS_MISMATCH'):
                store.initialize()
            self.assertEqual(before,store.host_schema_inventory())
        con.close()

class ExistingEventBusOnly(unittest.TestCase):
    def binding(self, publish=None, types=None, verified=True):
        route={p: 'host.p02.'+p for p in P02_TYPES}
        allowed=frozenset(route.values()) if types is None else types
        return NativeHostBinding(Identity('t','u','core','persona','session'),verified,allowed,route,
                                 publish or (lambda kind,payload: None))

    def test_missing_existing_host_registry_fails_closed(self):
        with self.assertRaisesRegex(P02Error,'EVENT_TYPE_NOT_IN_EXISTING_V3_REGISTRY'):
            P02EventRelay(self.binding(types=frozenset()))
        with self.assertRaises(PermissionError):
            P02EventRelay(self.binding(verified=False))

    def test_bounded_host_delivery_with_single_run(self):
        seen=[]
        relay=P02EventRelay(self.binding(publish=lambda name, payload: seen.append((name,payload))))
        rid=uuid.uuid4().hex
        relay.relay({'type':'chat.start','run_id':rid,'model':'installed:verified'})
        relay.relay({'type':'chat.delta','run_id':rid,'text':'Hello'})
        relay.relay({'type':'chat.complete','run_id':rid,'chars':5})
        self.assertEqual(len(seen),3)
        with self.assertRaisesRegex(P02Error,'CHAT_ALREADY_TERMINATED'):
            relay.relay({'type':'chat.delta','run_id':rid,'text':'extra'})

    def test_cross_run_or_privileged_fields_rejected(self):
        rid=uuid.uuid4().hex
        relay=P02EventRelay(self.binding())
        with self.assertRaisesRegex(P02Error,'CHAT_START_REQUIRED'):
            relay.relay({'type':'chat.delta','run_id':rid,'text':'wrong order'})
        relay.relay({'type':'chat.start','run_id':rid,'model':'installed:1'})
        with self.assertRaisesRegex(P02Error,'EVENT_RUN_MISMATCH'):
            relay.relay({'type':'chat.delta','run_id':uuid.uuid4().hex,'text':'other chat'})
        with self.assertRaises(PermissionError):
            relay.relay({'type':'chat.delta','run_id':rid,'text':'unsafe','principal':'other'})
        with self.assertRaisesRegex(P02Error,'P02_EVENT_PAYLOAD_OVER_QUOTA'):
            relay.relay({'type':'chat.delta','run_id':rid,'text':'x'*70000})


    def test_sources_reject_ambiguous_https_links_without_publishing(self):
        seen = []
        relay = P02EventRelay(self.binding(publish=lambda name, payload: seen.append((name, payload))))
        rid = uuid.uuid4().hex
        relay.relay({'type': 'chat.start', 'run_id': rid, 'model': 'installed:verified'})
        suspicious = (
            'https://example.org/%0a',
            'https://@example.org/',
            'https://example.org\\\\@evil.test/',
            'https://example.org/%7f',
            'https://example.org/%E2%80%AEevil',
            'https://example.org:99999/path',
            ' https://example.org/',
            'https://example.org/\\u202ehidden',
        )
        for url in suspicious:
            with self.subTest(url=url):
                with self.assertRaisesRegex(P02Error, 'CHAT_SOURCE_URL_FORBIDDEN'):
                    relay.relay({'type': 'chat.sources', 'run_id': rid, 'sources': [
                        {'source_id': 'doc', 'title': 'Verified', 'url': url}]})
        self.assertEqual(len(seen), 1, 'No invalid citation may reach the host bus')

    def test_sources_accept_valid_https_after_rejections(self):
        seen = []
        relay = P02EventRelay(self.binding(publish=lambda name, payload: seen.append((name, payload))))
        rid = uuid.uuid4().hex
        relay.relay({'type': 'chat.start', 'run_id': rid, 'model': 'installed:verified'})
        relay.relay({'type': 'chat.sources', 'run_id': rid, 'sources': [
            {'source_id': 'ref-1', 'title': 'Verified source',
             'url': 'https://example.org:8443/article?lang=es'}]})
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[-1][1]['sources'][0]['source_id'], 'ref-1')

if __name__=='__main__': unittest.main()
