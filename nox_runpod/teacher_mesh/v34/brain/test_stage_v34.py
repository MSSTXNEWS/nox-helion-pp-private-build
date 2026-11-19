"""Independent filesystem stage check — no modification to active source."""
from __future__ import annotations
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

class StageChecks(unittest.TestCase):
    def test_isolated_stage_source_hashes_and_active_bytes_unchanged(self):
        spec = importlib.util.spec_from_file_location('nox_stage_v34', ROOT/'STAGE_V34_FOR_JAPAN.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        source = ROOT/'source_v29'/'inherited_native_pr162'/'Packages'/'P02'/'worker-python'
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); live=base/'LIVE_NOX';worker=live/'Packages'/'P02'/'worker-python';worker.mkdir(parents=True)
            names=('p02_chat_bridge.py','p02_onehost.py')
            for name in names:(worker/name).write_bytes((source/name).read_bytes())
            before={n:hashlib.sha256((worker/n).read_bytes()).hexdigest() for n in names}
            receipt=module.stage(nox_root=live,stage_root=base/'STAGED_V34')
            self.assertEqual(receipt['state'],'SOURCE_STAGED_NOT_DEPLOYED')
            self.assertFalse(receipt['p02_baseline_drift'])
            self.assertTrue(receipt['native_integration_allowed'])
            self.assertTrue((base/'STAGED_V34'/'brain'/'neural_s03_live_v34.py').is_file())
            for name in names:
                self.assertEqual(before[name],hashlib.sha256((worker/name).read_bytes()).hexdigest())
            with self.assertRaises(RuntimeError):module.stage(nox_root=live,stage_root=base/'STAGED_V34')

if __name__=='__main__':unittest.main()
