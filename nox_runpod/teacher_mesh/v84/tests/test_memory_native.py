import sqlite3,tempfile,unittest
from pathlib import Path
from nox_runpod.teacher_mesh.v84.memory_native import NativeMemoryAccess,retrieve,distillation_reference_plan

class TestMemory(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.seed=str(root/'seed.sqlite3');self.inf=str(root/'infinite.sqlite3')
        c=sqlite3.connect(self.seed)
        c.execute("CREATE TABLE s03_segments(id TEXT,level TEXT,content TEXT,provenance TEXT,ref TEXT,sha256 TEXT,session TEXT,significance REAL)")
        c.executemany("INSERT INTO s03_segments VALUES (?,?,?,?,?,?,?,?)",[
            ("one","M3","NOX memory tested","source://one",None,None,"scope1",0.9),
            ("two","M3","NOX hidden memory",None,None,None,"scope1",0.8),
            ("three","M3","NOX wrong scope","source://other",None,None,"other",0.7)])
        c.commit();c.close()
        c=sqlite3.connect(self.inf)
        c.execute("CREATE TABLE facts(fact_id TEXT,key TEXT,value TEXT,source TEXT,active INTEGER,is_test INTEGER,superseded_by TEXT,ts_utc TEXT,dialog_id TEXT)")
        c.execute("CREATE TABLE brain_nodes(node_id TEXT,text TEXT,source TEXT,is_test INTEGER,hidden INTEGER,kind TEXT,ts_utc TEXT,meta TEXT)")
        c.executemany("INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?)",[
            ("fact1","NOX","knowledge","source://fact",1,0,None,"2026-01-01","scope1"),
            ("fact2","NOX","obsolete","source://fact",0,0,None,"2026-01-02","scope1"),
            ("fact3","NOX","test","source://fact",1,1,None,"2026-01-03","scope1")])
        c.executemany("INSERT INTO brain_nodes VALUES (?,?,?,?,?,?,?,?)",[
            ("n1","NOX synapse","source://graph",0,0,"concept","2026-01-01","{}"),
            ("n2","NOX secret","source://graph",0,1,"concept","2026-01-01","{}")])
        c.commit();c.close()
        self.paths={"seed":self.seed,"infinite":self.inf}
        self.native=NativeMemoryAccess(lambda s,a:s=="owner",lambda s,k,r:r["id"]!="three",lambda:False)
    def test_retrieval_filters(self):
        r=retrieve("NOX",scope="owner",paths=self.paths,native=self.native)
        self.assertEqual(r["state"],"NATIVE_LOCAL_MEMORY_RETRIEVED")
        self.assertEqual({x["id"] for x in r["results"]},{"one","fact1","n1"})
    def test_s03_record_session_acl(self):
        acl=NativeMemoryAccess(lambda s,a:True,lambda s,k,r: k!="s03_M3" or r.get("record_session")=="scope1",lambda:False)
        r=retrieve("NOX",scope="owner",paths=self.paths,native=acl)
        self.assertIn("one",{x["id"] for x in r["results"]})
        self.assertNotIn("three",{x["id"] for x in r["results"]})
    def test_no_scope(self):
        self.assertEqual(retrieve("NOX",scope="intruder",paths=self.paths,native=self.native)["state"],"HOLD_STOP_OR_ACCESS")
    def test_no_training_by_default(self):
        self.assertEqual(distillation_reference_plan(scope="owner",query="NOX",paths=self.paths,native=self.native)["state"],"HOLD_TRAINING_CONSENT")
    def test_plan_is_not_training(self):
        r=distillation_reference_plan(scope="owner",query="NOX",paths=self.paths,native=self.native,owner_training_opt_in=True)
        self.assertEqual(r["state"],"LOCAL_REFERENCE_CANDIDATES_ONLY")
        self.assertFalse(r["trainset_created"])
        self.assertEqual(r["optimizer_steps"],0)
    def test_missing_provenance_excluded(self):
        self.assertNotIn("two",[x["id"] for x in retrieve("NOX",scope="owner",paths=self.paths,native=self.native)["results"]])

if __name__=="__main__":unittest.main()
