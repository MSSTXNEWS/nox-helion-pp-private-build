import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from nox_selfbuilder.onehost_store import OneHostStoreActor, StoreActorHold

class OriginalStore:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
    def close(self):
        self.conn.close()

class ActorLifecycle(unittest.TestCase):
    def test_timed_out_queued_mutation_is_cancelled(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'helion.sqlite3'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE original_memory (value TEXT)')
            entered=threading.Event(); release=threading.Event()
            with OneHostStoreActor(lambda: OriginalStore(path)) as actor:
                with ThreadPoolExecutor(1) as worker:
                    pending=worker.submit(actor.call,lambda s:(entered.set(),release.wait(2),None)[-1])
                    self.assertTrue(entered.wait(2))
                    with self.assertRaisesRegex(StoreActorHold,'TIMEOUT_CANCELLED'):
                        actor.call(lambda s:s.conn.execute("INSERT INTO original_memory VALUES ('late')").rowcount,timeout=.02)
                    release.set(); pending.result()
                self.assertEqual(actor.call(lambda s:s.conn.execute('SELECT * FROM original_memory').fetchall()),())
            with self.assertRaisesRegex(StoreActorHold,'CLOSED'):
                actor.call(lambda s: None)

    def test_sqlite_factory_and_close_remain_on_owner_thread(self):
        threads=[]
        class TrackedStore(OriginalStore):
            def __init__(self,path):
                threads.append(threading.get_ident());super().__init__(path)
            def close(self):
                threads.append(threading.get_ident());super().close()
        with tempfile.TemporaryDirectory() as d:
            with OneHostStoreActor(lambda:TrackedStore(Path(d)/'helion.sqlite3')) as actor:
                owner=actor.call(lambda s:threading.get_ident())
            self.assertEqual(threads,[owner,owner]);self.assertNotEqual(owner,threading.get_ident())

if __name__=='__main__':unittest.main()
