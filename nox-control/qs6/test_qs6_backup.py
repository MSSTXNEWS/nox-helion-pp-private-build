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

    def test_backup_same_timestamp_never_overwrites_previous_copy(self):
        """Both repeated and concurrent-name collisions preserve the first copy."""
        now = 1_700_000_000.125
        first = B.backup(self.db, self.bdir, keep=5, now=now)
        first_bytes = open(first["path"], "rb").read()
        first_meta = open(first["path"] + ".json", "rb").read()
        s = Store(self.db)
        s.add_fact("Более новое содержимое")
        s.close()
        second = B.backup(self.db, self.bdir, keep=5, now=now)
        third = B.backup(self.db, self.bdir, keep=5, now=now)
        self.assertEqual(len({first["file"], second["file"], third["file"]}), 3)
        self.assertEqual(open(first["path"], "rb").read(), first_bytes)
        self.assertEqual(open(first["path"] + ".json", "rb").read(), first_meta)
        for r in (first, second, third):
            self.assertTrue(B.verify(r["path"])[0])
        self.assertEqual(B.counts(first["path"])["mem_facts"], 1)
        self.assertEqual(B.counts(second["path"])["mem_facts"], 2)

    def test_failed_backup_cleans_own_reservation_only(self):
        from unittest.mock import patch
        good = B.backup(self.db, self.bdir, now=1_700_000_000)
        with patch.object(B, "integrity", side_effect=RuntimeError("injected backup error")):
            with self.assertRaisesRegex(RuntimeError, "injected backup error"):
                B.backup(self.db, self.bdir, now=1_700_000_000)
        self.assertTrue(B.verify(good["path"])[0])
        self.assertEqual(len(B.list_backups(self.bdir)), 1)
        self.assertFalse(any(n.endswith(".tmp") for n in os.listdir(self.bdir)))

    def test_foreign_stale_temp_file_is_never_deleted_on_hold(self):
        now = 1_700_000_000
        good = B.backup(self.db, self.bdir, now=now)
        # Derive the exact expected next name using the actual timestamp.
        stamp = B.time.strftime("%Y%m%d-%H%M%S", B.time.gmtime(now))
        colliding = os.path.join(self.bdir, ".memory-" + stamp + "-1.sqlite3.tmp")
        with open(colliding, "wb") as f:
            f.write(b"previous process recovery marker")
        with self.assertRaisesRegex(RuntimeError, "HOLD"):
            B.backup(self.db, self.bdir, now=now)
        self.assertEqual(open(colliding, "rb").read(), b"previous process recovery marker")
        self.assertTrue(B.verify(good["path"])[0])

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

    def test_restore_refuses_same_second_backup_collision_without_overwrite(self):
        r = B.backup(self.db, self.bdir)
        s = Store(self.db)
        s.add_fact("Факт до запрещённого восстановления")
        s.close()
        old_contents = open(self.db, "rb").read()
        occupied = "%s.before-restore-%s" % (
            self.db, B.time.strftime("%Y%m%d-%H%M%S"))
        with open(occupied, "wb") as f:
            f.write(b"preserved previous checkpoint")
        with self.assertRaisesRegex(RuntimeError, "уже существует"):
            B.restore(r["path"], self.db)
        self.assertEqual(open(occupied, "rb").read(), b"preserved previous checkpoint")
        self.assertEqual(open(self.db, "rb").read(), old_contents)
        self.assertFalse(os.path.exists(self.db + ".restore.tmp"))

    def test_restore_failed_atomic_swap_rolls_back_original(self):
        from unittest.mock import patch

        r = B.backup(self.db, self.bdir)
        s = Store(self.db)
        s.add_fact("Факт, который нельзя терять при ошибке")
        s.close()
        real_replace = os.replace

        def fail_only_install(src, dst):
            if src == self.db + ".restore.tmp" and dst == self.db:
                raise OSError("injected disk rename failure")
            return real_replace(src, dst)

        with patch.object(B.os, "replace", side_effect=fail_only_install):
            with self.assertRaisesRegex(OSError, "injected"):
                B.restore(r["path"], self.db)
        self.assertFalse(os.path.exists(self.db + ".restore.tmp"))
        s = Store(self.db)
        self.assertEqual(s.stats()["facts"], 2)
        s.close()

    def test_restore_refuses_orphan_wal_before_install(self):
        r = B.backup(self.db, self.bdir)
        new = os.path.join(self.td.name, "orphan.db")
        with open(new + "-wal", "wb") as f:
            f.write(b"orphan WAL")
        with self.assertRaisesRegex(RuntimeError, "осиротевшие"):
            B.restore(r["path"], new)
        self.assertFalse(os.path.exists(new))
        self.assertEqual(open(new + "-wal", "rb").read(), b"orphan WAL")

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
