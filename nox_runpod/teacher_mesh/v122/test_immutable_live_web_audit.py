"""V122 read-only source gate: no training, model changes, or native restart."""
import ast
import json
import unittest
from pathlib import Path
from nox_runpod.teacher_mesh.v122.immutable_live_web_audit import REMOTE_TEMPLATE

class ImmutableAuditTests(unittest.TestCase):
    def test_remote_python_compiles_and_has_no_mutating_actions(self):
        script=REMOTE_TEMPLATE.split("<<'PYREMOTE'\n",1)[1].rsplit('\nPYREMOTE',1)[0]
        compile(script,'<v122-audit>','exec')
        self.assertNotIn('os.replace(',script)
        self.assertNotIn('supervisorctl',script)
        self.assertNotIn('subprocess.Popen(',script)
        self.assertNotIn('mode=rw',script)
        self.assertIn('mode=ro',script)
        self.assertIn("NATIVE_READ_ONLY_COMPLETE=true",script)
        self.assertIn("credentials_exported':False",script)

    def test_all_frozen_routes_are_unique(self):
        obj=json.loads(Path('coordination/NOX_V98_WEB_FULL_REAL_API_MATRIX.json').read_text())
        routes=[x['route'] for x in obj['functions']]
        self.assertEqual(92,len(routes))
        self.assertEqual(92,len(set(routes)))
        self.assertTrue(all(p.startswith('/api/') for p in routes))

if __name__=='__main__':
    unittest.main()
