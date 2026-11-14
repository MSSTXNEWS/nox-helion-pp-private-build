"""Static safety gates for V126 RAM-only native S03 source probe."""
import ast
import unittest
from nox_runpod.teacher_mesh.v126.physical_writer_ramdb_probe import REMOTE

class NoProductionMutation(unittest.TestCase):
    def test_embedded_script_compiles(self):
        src=REMOTE.split("<<'PYREMOTE'\n",1)[1].rsplit('\nPYREMOTE',1)[0]
        compile(src,'<v126-ram-writer>', 'exec')
        self.assertIn("TemporaryDirectory(prefix='nox-v126-',dir=ram)",src)
        self.assertIn("db=str(path)",src)
        self.assertIn("mode=ro",src)
        self.assertIn("source_sha256",src)
        self.assertIn("meta_roundtrip",src)
        self.assertIn("NATIVE_READ_ONLY_COMPLETE=true",src)
        for b in ("os.replace(", "shutil.rmtree('/root", "supervisorctl",
                  "DELETE FROM", "DROP TABLE", "optimizer.step("):
            self.assertNotIn(b,src)

if __name__=="__main__":
    unittest.main()
