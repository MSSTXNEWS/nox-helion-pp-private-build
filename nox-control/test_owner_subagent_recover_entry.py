import base64
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import owner_subagent_recover_entry as recovery


class RecoveryTests(unittest.TestCase):
    def test_real_transport_replacement_preserves_nested_helper_bundle(self):
        folder = Path(__file__).resolve().parent
        assets = {'owner_subagent_install_entry.py': base64.b64encode(
            (folder/'owner_subagent_install_entry.py').read_bytes()).decode(),
            'owner_subagent_dispatcher.py': 'reviewed-module-sentinel'}
        payload = (folder/'owner_subagent_recover_entry.py').read_text().replace(
            '__NOX_BUNDLE_JSON__', json.dumps(assets))
        namespace = {'__name__': 'recovery_transport_test'}
        with patch.dict(sys.modules):
            exec(compile(payload, '<materialized-native-transport>', 'exec'), namespace)
            self.assertEqual(namespace['helper']().BUNDLE, assets)

    def test_exact_observed_preimage_has_only_reviewed_hash_delta(self):
        root = Path(__file__).resolve().parents[1]
        before = subprocess.check_output(['git', 'show',
            '41fbe63b5e57b1172956f8264c403aefa338aa6d:nox-control/owner_subagent_dispatcher.py'], cwd=root)
        after = recovery.corrected_source(before)
        self.assertEqual(after, (root/'nox-control/owner_subagent_dispatcher.py').read_bytes())
        with self.assertRaisesRegex(RuntimeError, 'SOURCE_CHANGED'):
            recovery.corrected_source(after)

    def test_original_admissions_are_read_only_and_reuse_same_s03_ids(self):
        tasks = {}
        for role in recovery.ADMISSIONS:
            task_id = 'owner.native.v06.'+role+'.84780aaf911a'
            tasks[task_id] = {'native_admission': {'task_id': task_id, 'source_sha256': recovery.OLD_MODULE}}
        module = Mock()
        def readback(receipt):
            role = receipt['task_id'].split('.')[3]
            return {'s03_item_id': recovery.ADMISSIONS[role], 'task_id': receipt['task_id']}
        module.s03_readback.side_effect = readback
        result = recovery.admissions({'tasks': tasks}, module)
        self.assertEqual(len(result), 3)
        module.remember.assert_not_called()
        tasks[next(iter(tasks))]['native_admission']['source_sha256'] = '0'*64
        with self.assertRaisesRegex(RuntimeError, 'ADMISSION_IDENTITY'):
            recovery.admissions({'tasks': tasks}, module)

    def test_group_allows_only_director_descendants_not_other_roles(self):
        rows = {1: {'pid': 1, 'ppid': 0, 'pgrp': 1, 'state': 'S'},
                2: {'pid': 2, 'ppid': 1, 'pgrp': 1, 'state': 'S'},
                3: {'pid': 3, 'ppid': 2, 'pgrp': 1, 'state': 'S'}}
        with patch.object(recovery, 'metadata', side_effect=lambda pid: rows.get(int(pid))), \
             patch.object(Path, 'iterdir', return_value=iter([Path(str(pid)) for pid in rows])):
            self.assertEqual(len(recovery.owned_group(1)), 3)
        rows[3]['ppid'] = 99
        with patch.object(recovery, 'metadata', side_effect=lambda pid: rows.get(int(pid))), \
             patch.object(Path, 'iterdir', return_value=iter([Path(str(pid)) for pid in rows])):
            with self.assertRaisesRegex(RuntimeError, 'UNRELATED_PROCESS_GROUP'):
                recovery.owned_group(1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
