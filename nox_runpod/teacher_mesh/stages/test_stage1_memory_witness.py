#!/usr/bin/env python3
"""Isolated SQLite fixture checks, NOT a live Windows/S03 acceptance.
Wiring on actual authenticated OneHost must repeat these tests with real S03.
"""
import sqlite3,sys,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from cognitive_overlay import CognitiveOverlay,MemoryEvidence
from stage1_memory_witness import capture_recall,compare_recall

NOW=datetime(2026,11,13,0,0,tzinfo=timezone.utc).timestamp()
STAMP="2026-11-12T21:00:00Z"
EVENT="m7-teacher-proof"
BOOT1="1"*64
BOOT2="2"*64
class FakeModel:
    def generate(self,prompt,context):return "NOX fixture"

class SqliteFixture:
    """Only the test owns this database. Production S03 remains untouched."""
    def __init__(self,db):self.db=db
    def search(self,*,query,scope,limit):
        if "дистилляция" not in query:return []
        with sqlite3.connect(self.db) as cx:
            rows=cx.execute("select id,scope,body,source from history where scope=? limit ?",
                (scope,limit)).fetchall()
        return [MemoryEvidence(id,body,"M7",source,STAMP,.92,True,False,row_scope)
                for id,row_scope,body,source in rows]
    def capabilities(self,*,scope):return []
    def append_approved(self,*,scope,event):raise AssertionError("source-only no S03 writes")

class TestMemoryWitness(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"test_s03_fixture.sqlite"
        with sqlite3.connect(self.path) as db:
            db.execute("create table history (id text, scope text, body text, source text)")
            db.executemany("insert into history values (?,?,?,?)",[
                (EVENT,"owner","Дистилляция использовала проверенный checkpoint NOX","s03://nox/history"),
                ("private-other","other","Чужое приватное событие","s03://other/private")
            ])
    def capture(self,boot=BOOT1,scope="owner",authorized=True):
        s03=SqliteFixture(self.path)
        overlay=CognitiveOverlay(s03,FakeModel(),clock=lambda:NOW)
        return capture_recall(overlay,scope=scope,expected_event_id=EVENT,
                              boot_id=boot,authenticated_onehost=authorized)
    def test_real_sqlite_fixture_reopen_same_digest(self):
        before=self.capture()
        after=self.capture(BOOT2)
        self.assertEqual(before["state"],"S03_VERIFIED_EVENT_READABLE_SOURCE_ONLY")
        self.assertEqual(before["event_fingerprint_sha256"],after["event_fingerprint_sha256"])
        self.assertFalse(before["live_s03_verified"])
        self.assertNotIn("Дистилляция",str(before))
        self.assertEqual(compare_recall(before,after)["state"],"HOLD")
    def test_signed_native_restart_receipt_still_not_independent_e07(self):
        before,after=self.capture(),self.capture(BOOT2)
        r=compare_recall(before,after,reboot={
            "verified_by_existing_onehost":True,
            "before_boot_id":BOOT1,"after_boot_id":BOOT2,
            "native_restart_readback":True,
        })
        self.assertEqual(r["state"],"NATIVE_REBOOT_RECEIPT_CLAIMS_STABLE_S03_RECALL")
        self.assertFalse(r["windows_reboot_verified"])
        self.assertTrue(r["independent_e07_required"])
    def test_non_owner_scope_cannot_leak(self):
        self.assertEqual(self.capture(scope="other")["state"],"HOLD")
    def test_unverified_native_host_cannot_create_witness(self):
        self.assertEqual(self.capture(authorized=False)["reason"],"AUTHENTICATED_ONEHOST_REQUIRED")
    def test_event_modified_after_reopen_fails(self):
        before=self.capture()
        with sqlite3.connect(self.path) as db:
            db.execute("update history set body=? where id=?",
                       ("изменённая история, не соответствует",EVENT))
        after=self.capture(BOOT2)
        self.assertEqual(compare_recall(before,after)["reason"],"RECALL_FACT_CHANGED_OR_MISSING")
    def test_identical_boot_id_not_restart(self):
        before,after=self.capture(BOOT1),self.capture(BOOT1)
        self.assertEqual(compare_recall(before,after)["reason"],"NO_BOOT_BOUNDARY_EVIDENCE")
    def test_no_missing_event_cannot_claim_memory(self):
        with sqlite3.connect(self.path) as db:db.execute("delete from history where id=?",(EVENT,))
        self.assertEqual(self.capture()["reason"],"VERIFIED_GENESIS_EVENT_NOT_RETRIEVED")
if __name__=="__main__":unittest.main()
