"""memory_boot_s1.sh на временных каталогах: sha -> распаковка -> dry_run -> импорт -> cron (подменённый crontab). Без сети и без S1."""
import json, os, shutil, subprocess, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); CTRL = os.path.dirname(HERE); SCRIPT = os.path.join(HERE, "memory_boot_s1.sh")
NEED = all(shutil.which(x) for x in ("bash", "tar", "sha256sum", "gzip"))

@unittest.skipUnless(NEED, "нужны bash/tar/sha256sum/gzip")
class T(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(); self.src = os.path.join(self.t, "src"); os.makedirs(os.path.join(self.src, "m")); os.makedirs(os.path.join(self.t, "bin"))
        json.dump([{"text": "Мессир любит ночные прогоны сервера", "kind": "owner"}, {"text": "Порт старого шлюза был 8082", "kind": "fact"}, {"text": "пароль: abcdefgh12345"}],
                  open(os.path.join(self.src, "m", "memory.json"), "w", encoding="utf-8"), ensure_ascii=False)
        subprocess.check_call("tar -czf memory.tar.gzip m && cp memory.tar.gzip state.tar.gzip && rm -r m && sha256sum *.tar.gzip > SHA256SUMS", shell=True, cwd=self.src)
        self.cron = os.path.join(self.t, "cron.out"); cr = os.path.join(self.t, "bin", "crontab")
        open(cr, "w").write('#!/bin/bash\nif [ "$1" = "-l" ]; then cat %s 2>/dev/null; else cat > %s; fi\n' % (self.cron, self.cron)); os.chmod(cr, 0o755)
        self.env = dict(os.environ, PATH=os.path.join(self.t, "bin") + ":" + os.environ["PATH"], NOX_HOME=os.path.join(self.t, "home"), NOX_CONTROL=CTRL, NOX_BACKUP_SRC=self.src, PYTHONDONTWRITEBYTECODE="1")
        self.db = os.path.join(self.t, "home", "memory", "s03.db")
    def run_boot(self): return subprocess.run(["bash", SCRIPT], env=self.env, capture_output=True, text=True, timeout=120)
    def test_full_and_idempotent(self):
        r = self.run_boot(); self.assertIn("sha256 бэкапа сошёлся", r.stdout); self.assertIn("импорт выполнен", r.stdout, r.stdout + r.stderr)
        import sqlite3
        facts = [x[0] for x in sqlite3.connect(self.db).execute("SELECT text FROM mem_facts UNION SELECT value FROM mem_profile")]
        self.assertIn("Мессир любит ночные прогоны сервера", facts); self.assertFalse(any("abcdefgh" in f for f in facts))
        cron = open(self.cron, encoding="utf-8").read(); self.assertEqual(cron.count("@hourly"), 1); self.assertIn("backup_memory.py backup", cron); self.assertIn(self.db, cron)
        self.assertTrue(os.listdir(os.path.join(self.t, "home", "memory", "backups")))
        n = sqlite3.connect(self.db).execute("SELECT COUNT(*) FROM mem_facts").fetchone()[0]
        self.run_boot(); self.assertEqual(sqlite3.connect(self.db).execute("SELECT COUNT(*) FROM mem_facts").fetchone()[0], n)
        self.assertEqual(open(self.cron, encoding="utf-8").read().count("@hourly"), 1)
    def test_bad_sha_blocks_import(self):
        open(os.path.join(self.src, "memory.tar.gzip"), "ab").write(b"corrupt")
        r = self.run_boot(); self.assertIn("НЕ сошёлся", r.stdout); self.assertFalse(os.path.exists(self.db)); self.assertFalse(os.path.exists(self.cron))
    def test_no_sums_no_import(self):
        os.remove(os.path.join(self.src, "SHA256SUMS")); r = self.run_boot(); self.assertIn("нет", r.stdout); self.assertFalse(os.path.exists(self.db))
if __name__ == "__main__": unittest.main()
