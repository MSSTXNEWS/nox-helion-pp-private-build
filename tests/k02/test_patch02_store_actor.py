import sqlite3, tempfile, threading, unittest
from pathlib import Path
from nox_selfbuilder.onehost_store import OneHostStoreActor, StoreActorHold

class OriginalStore:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
    def close(self): self.conn.close()

class ActorTests(unittest.TestCase):
    def test_same_original_db_cross_thread(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'helion.sqlite3'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE memory (x INTEGER)')
                db.execute('INSERT INTO memory VALUES (17)')
            original=OriginalStore(path)
            errors=[]
            def wrong_thread():
                try: original.conn.execute('SELECT x FROM memory').fetchone()
                except sqlite3.ProgrammingError: errors.append(True)
            t=threading.Thread(target=wrong_thread);t.start();t.join()
            self.assertEqual(errors,[True])
            original.close()
            with OneHostStoreActor(lambda: OriginalStore(path)) as actor:
                values=[]
                def worker(): values.append(actor.call(lambda s:s.conn.execute('SELECT x FROM memory').fetchone()))
                workers=[threading.Thread(target=worker) for _ in range(8)]
                for t in workers:t.start()
                for t in workers:t.join()
                self.assertEqual(values,[(17,)]*8)
                with self.assertRaises(StoreActorHold):
                    actor.call(lambda s:s.conn)
                actor.call(lambda s:s.conn.execute('INSERT INTO memory VALUES (18)').rowcount)
                actor.call(lambda s:s.conn.commit())
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT x FROM memory ORDER BY x').fetchall(),[(17,),(18,)])
    def test_error_not_swallowed(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'existing.sqlite3'
            with sqlite3.connect(path):pass
            with OneHostStoreActor(lambda: OriginalStore(path)) as actor:
                with self.assertRaises(sqlite3.OperationalError):
                    actor.call(lambda s:s.conn.execute('SELECT * FROM missing').fetchall())
