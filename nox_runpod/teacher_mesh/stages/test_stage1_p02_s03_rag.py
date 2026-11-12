#!/usr/bin/env python3
"""Real SQLite fixture, native callback auth and STOP tests for P02 RAG seam."""
from __future__ import annotations
import sqlite3,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from stage1_p02_s03_rag import ExistingS03Rag

T="2026-11-12T18:10:00Z"
class Native:
    def __init__(self,path):
        self.path=path;self.stop=False;self.authorized=True;self.calls=[]
    def auth(self,t,p,c):return self.authorized and (t,p,c)==("nox","owner","chat1")
    def stopfn(self):return self.stop
    def search(self,t,p,c,query,limit):
        self.calls.append(query)
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            rows=db.execute("select * from fact where tenant=? and principal=? and chat=?",
                           (t,p,c)).fetchmany(limit)
        return [dict(x,scope_chat_id=x["chat"]) for x in rows]
    def rag(self):
        return ExistingS03Rag(native_authorize=self.auth,native_stop=self.stopfn,
                              search_authenticated=self.search)
class Tests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        path=Path(temp.name)/"fixture.sqlite"
        with sqlite3.connect(path) as db:
            db.execute("""create table fact(
                id text,tenant text,principal text,chat text,content text,
                source_uri text,segment text,timestamp_utc text,
                importance real,verified integer,superseded integer)""")
            db.executemany("insert into fact values(?,?,?,?,?,?,?,?,?,?,?)",[
                ("e1","nox","owner","chat1","NOX учитель Devstral в отчёте S1-L05: checked provenance",
                 "s03://owner/teacher_e1","M7",T,.95,1,0),
                ("e2","nox","owner","chat1","Сказка: всё чувствует, не подтверждено",
                 "s03://owner/unverified","M7",T,.99,0,0),
                ("e3","nox","someone_else","chat1","Чужая приватная история",
                 "s03://someone_else","M7",T,.99,1,0),
                ("e4","nox","owner","chat1","Устаревший факт",
                 "s03://old","M7",T,.99,1,1)
            ])
        self.host=Native(path)
    def test_memory_recall_provenance_with_alias_and_privacy(self):
        r=self.host.rag()("nox","owner","chat1","Ты кого съел?")
        self.assertEqual(r["memory_state"],"S03_VERIFIED_SCOPE_READ_ONLY")
        self.assertEqual(r["evidence_count"],1)
        self.assertIn("Devstral",r["context"])
        self.assertNotIn("Чужая",r["context"])
        self.assertNotIn("Сказка",r["context"])
        self.assertNotIn("Устаревший",r["context"])
        self.assertEqual(len(self.host.calls),2)
        self.assertIn("teacher",self.host.calls[1])
    def test_reopened_store_still_yields_same_scoped_digest(self):
        a=self.host.rag()("nox","owner","chat1","Ты кого съел?")
        self.host=Native(self.host.path)
        b=self.host.rag()("nox","owner","chat1","Ты кого съел?")
        self.assertEqual(a["context_sha256"],b["context_sha256"])
    def test_stop_blocks_initial_and_after_read(self):
        self.host.stop=True
        self.assertEqual(self.host.rag()("nox","owner","chat1","Ты кого съел?")["memory_state"],"HOLD")
        self.host.stop=False
        cb=self.host.rag()
        original=self.host.search
        def stopping(*a,**k):
            result=original(*a,**k);self.host.stop=True;return result
        self.host.search=stopping
        cb=self.host.rag()
        self.assertEqual(cb("nox","owner","chat1","Ты кого съел?")["reason"],"STOP_OR_SCOPE_REVOKED_AFTER_S03")
    def test_refused_scope_holds(self):
        self.assertEqual(self.host.rag()("nox","other","chat1","Ты кого съел?")["memory_state"],"HOLD")
        self.assertEqual(self.host.rag()("nox","owner","chat-other","Ты кого съел?")["memory_state"],"HOLD")
    def test_disabled_owner_scope_blocks(self):
        self.host.authorized=False
        self.assertEqual(self.host.rag()("nox","owner","chat1","Ты кого съел?")["reason"],"STOP_OR_NATIVE_SCOPE_DENIED")
    def test_hallucinated_source_never_promoted(self):
        with sqlite3.connect(self.host.path) as db:db.execute(
            "update fact set verified=0 where id='e1'")
        self.assertEqual(self.host.rag()("nox","owner","chat1","Ты кого съел?")["evidence_count"] if False else
                         self.host.rag()("nox","owner","chat1","Ты кого съел?")["memory_state"],"HOLD")
if __name__=="__main__":unittest.main()
