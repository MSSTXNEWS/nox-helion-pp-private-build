"""V126 source-only safety gate for read-only S03 writer inventory."""
import ast
import unittest
from nox_runpod.teacher_mesh.v126.native_s03_writer_contract import REMOTE

class S03ContractReadOnly(unittest.TestCase):
    def test_native_code_compiles_with_ro_sqlite(self):
        script=REMOTE.split("<<'PYREMOTE'\n",1)[1].rsplit('\nPYREMOTE',1)[0]
        ast.parse(script)
        compile(script,'<v126-s03-readonly>','exec')
        self.assertIn("mode=ro",script)
        self.assertIn("PRAGMA query_only=ON",script)
        self.assertIn("PRAGMA table_info(s03_items)",script)
        self.assertIn("NATIVE_V126_SOURCE=",script)
        self.assertIn("NATIVE_V126_S03=",script)
        for bad in ('INSERT INTO','UPDATE s03_items','DELETE FROM','DROP TABLE',
                    'torch.save(','optimizer.step(','supervisorctl'):
            self.assertNotIn(bad,script)
        self.assertNotIn('SELECT text FROM s03_items',script)
        self.assertNotIn("print(s03_memory.DB)",script)

if __name__=='__main__':
    unittest.main()
