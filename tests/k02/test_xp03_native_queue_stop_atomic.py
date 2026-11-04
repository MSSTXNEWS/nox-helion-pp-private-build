"""XP03: original S03 work queue MUST rollback both task + audit on late STOP/ACL.
Run in EXISTING source checkout: PYTHONPATH=src python -m unittest tests.k02.test_xp03_native_queue_stop_atomic -v
Source SQLite fixture, not native Windows/EXE/E07 acceptance.
"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from nox_selfbuilder.onehost_store import OneHostStoreActor
from nox_selfbuilder.onehost_queue import NativeWorkQueue

class _OriginalSchemaFixture:
    def __init__(self, path, on_created):
        self.conn=sqlite3.connect(path)
        self.on_created=on_created
        self.conn.executescript("""CREATE TABLE tasks(id INTEGER PRIMARY KEY, title TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE audit(id INTEGER PRIMARY KEY, item_id INTEGER, action TEXT, metadata TEXT, at TEXT);""")
    def _audit(self, action, item_id, metadata):
        self.conn.execute("INSERT INTO audit(item_id,action,metadata,at) VALUES(?,?,?,?)",
                          (item_id,action,json.dumps(metadata),"2026-11-02T00:00:00Z"))
        if action=="NOX_NATIVE_WORK_CREATED": self.on_created()
    def close(self): self.conn.close()

class XP03NativeQueueAtomicStop(unittest.TestCase):
    def test_late_stop_acl_and_epoch_all_rollback(self):
        scope=SimpleNamespace(tenant="local",principal="owner",chat_id="default")
        for mode in ("STOP","ACL","EPOCH","OK"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                stop=Event()
                consent={"ok":True}
                epoch={"n":1}
                def on_created():
                    if mode=="STOP": stop.set()
                    if mode=="ACL": consent["ok"]=False
                    if mode=="EPOCH": epoch["n"]+=1
                with OneHostStoreActor(lambda:_OriginalSchemaFixture(Path(tmp)/"s03.sqlite3",on_created)) as actor:
                    queue=NativeWorkQueue(actor,authorize=lambda *_:consent["ok"],
                                          stop_requested=stop.is_set,stop_epoch=lambda:epoch["n"])
                    if mode=="OK":
                        tid=queue.enqueue(scope,kind="SELF_WRITE",payload={"task":"reviewed lesson"},
                                          permission="selfbuilder.propose")
                        self.assertGreater(tid,0)
                    else:
                        with self.assertRaisesRegex(PermissionError,"NATIVE_QUEUE_REVOKED"):
                            queue.enqueue(scope,kind="SELF_WRITE",payload={"task":"reviewed lesson"},
                                          permission="selfbuilder.propose")
                    counts=actor.call(lambda s:(s.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
                                                s.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]))
                    self.assertEqual(counts,(1,2) if mode=="OK" else (0,0))
if __name__=="__main__": unittest.main()
