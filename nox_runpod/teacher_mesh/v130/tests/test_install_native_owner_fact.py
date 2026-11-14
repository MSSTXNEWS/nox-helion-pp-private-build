"""V130 native deployment safety tests; no Vast/SSH connection from unit runner."""
import ast,unittest
from pathlib import Path
from nox_runpod.teacher_mesh.v130 import install_native_owner_fact as install

class InstallSourceTests(unittest.TestCase):
    def setUp(self):
        self.script=install.REMOTE_TEMPLATE.partition("<<'PYREMOTE'")[2].rpartition('PYREMOTE')[0]

    def test_remote_native_compiles(self):
        self.assertTrue(self.script)
        compile(self.script,'<V130 NATIVE INSTALL>', 'exec')
        self.assertIn("HOLD_V130_CONCURRENT_SHA_DRIFT",self.script)
        self.assertIn("HOLD_V130_POST_NOTE_S03",self.script)

    def test_gates_and_atomic_rollback_required(self):
        for part in ('HOLD_STOP','HOLD_V130_IDLE_HEALTH','HOLD_V130_BACKUP_SHA',
                     'HOLD_V130_BEFORE_WRITE_CHANGED','HOLD_V130_MODULE_STAGE',
                     'HOLD_V130_OWNER_ONLY','HOLD_V130_IDEMPOTENT_REPLAY',
                     'HOLD_ROLLBACK_UNVERIFIED','TEMP_SSH_CLEANUP='):
            candidate=(self.script+Path(install.__file__).read_text())
            self.assertIn(part,candidate)

    def test_exact_existing_onehost_auth_guard(self):
        self.assertEqual(install.PROXY_OLD_GUARD.count("'/api/nox/training/status'"),1)
        self.assertNotIn("'/api/nox/memory/facts'",install.PROXY_OLD_GUARD)
        self.assertEqual(install.PROXY_NEW_GUARD.count("'/api/nox/memory/facts'"),1)
        self.assertIn("and _session_ok(request):",install.PROXY_NEW_GUARD)
        self.assertEqual(install.ANCHOR.count("directory=Path(site_dir)"),1)

    def test_immutable_native_model_and_s03_sha_pins(self):
        for field in (install.BRIDGE_SHA,install.PROXY_SHA,install.S03_SOURCE_SHA):
            self.assertEqual(len(field),64)
            self.assertTrue(all(x in '0123456789abcdef' for x in field))
        self.assertIn('nox_v29_chat_bridge.py',self.script)
        self.assertIn('chat_proxy.py',self.script)
        self.assertIn('s03_memory.py',self.script)
        self.assertNotIn("terminate_pod",self.script)
        self.assertNotIn("DELETE FROM s03_items",self.script)

    def test_existing_s03_native_writer_used_not_new_database(self):
        source=Path('nox_runpod/teacher_mesh/v130/owner_s03_fact_write.py').read_text()
        self.assertIn('s03_memory.remember(',source)
        self.assertIn("mode=ro",source)
        self.assertIn("PRAGMA quick_check",source)
        self.assertNotIn('CREATE TABLE',source)
        self.assertIn('readback_verified',source)

if __name__=='__main__':unittest.main()
