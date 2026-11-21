import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qs6.s03_store import Store
from qs6 import backup_memory as B


class BackupT(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(); self.addCleanup(self.td.cleanup)
        self.db = os.path.join(self.td.name, "mem.db")
        self.bdir = os.path.join(self.td.name, "bk")
        s = Store(self.db)
        s.add_fact("Факт для бэкапа"); s.add_episode("Эпизод"); s.set_profile("k", "v")
        s.close()

    def test_backup_verify_rotate(self):
        names = []
        for i in range(5):
            r = B.backup(self.db, self.bdir, keep=3, now=1_700_000_000 + i * 3600)
            names.append(r["file"])
        left = [m["file"] for m in B.list_backups(self.bdir)]
        self.assertEqual(left, names[-3:])
        self.assertEqual(len([n for n in os.listdir(self.bdir) if n.endswith(".json")]), 3)
        ok, msg = B.verify(os.path.join(self.bdir, names[-1]))
        self.assertTrue(ok, msg)
        self.assertEqual(r["counts"]["mem_facts"], 1)

    def test_backup_while_open_for_write(self):
        s = Store(self.db)
        s.add_fact("Ещё факт")
        r = B.backup(self.db, self.bdir)
        s.close()
        self.assertEqual(r["counts"]["mem_facts"], 2)

    def test_corruption_detected_and_restore_refused(self):
        r = B.backup(self.db, self.bdir)
        with open(r["path"], "r+b") as f:
            f.seek(2000); f.write(b"\xff\xff\xff\xff")
        ok, msg = B.verify(r["path"])
        self.assertFalse(ok)
        before = open(self.db, "rb").read()
        with self.assertRaises(RuntimeError):
            B.restore(r["path"], self.db)
        self.assertEqual(open(self.db, "rb").read(), before)       # база не тронута

    def test_restore_keeps_previous(self):
        r = B.backup(self.db, self.bdir)
        s = Store(self.db); s.add_fact("Новее чем копия"); s.close()
        out = B.restore(r["path"], self.db)
        self.assertTrue(os.path.exists(out["previous_kept_as"]))
        s = Store(self.db)
        self.assertEqual(s.stats()["facts"], 1)
        s.close()
        old = Store(out["previous_kept_as"])
        self.assertEqual(old.stats()["facts"], 2)
        old.close()

    def test_restore_into_new_path(self):
        r = B.backup(self.db, self.bdir)
        new = os.path.join(self.td.name, "sub", "new.db")
        out = B.restore(r["path"], new)
        self.assertIsNone(out["previous_kept_as"])
        self.assertEqual(sqlite3.connect(new).execute("SELECT COUNT(*) FROM mem_facts").fetchone()[0], 1)

    def test_missing_meta_and_cli(self):
        r = B.backup(self.db, self.bdir)
        os.remove(r["path"] + ".json")
        self.assertFalse(B.verify(r["path"])[0])
        self.assertEqual(B.main(["backup", "--db", self.db, "--dir", self.bdir, "--keep", "2"]), 0)
        self.assertEqual(B.main(["backup", "--db", "/nonexistent.db", "--dir", self.bdir]), 1)
        self.assertEqual(B.main(["cron", "--db", self.db, "--dir", self.bdir]), 0)
        self.assertIn("7 * * * *", B.cron_line(self.db, self.bdir, 24))
        newest = B.list_backups(self.bdir)[-1]["path"]
        self.assertEqual(B.main(["verify", newest]), 0)


if __name__ == "__main__":
    unittest.main()
