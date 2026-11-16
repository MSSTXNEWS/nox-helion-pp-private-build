import hashlib
import importlib.util
import os
from pathlib import Path
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('owner_training_disk_guard_entry',HERE/'owner_training_disk_guard_entry.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)


class InstallTests(unittest.TestCase):
    def test_exact_helper_pins(self):
        for name,pin in [('owner_native_repair.py',entry.HELPER_SHA),('owner_training_disk_guard.py',entry.GUARD_SHA)]:
            self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(),pin)

    def test_missing_real_initial_admission_cannot_touch_sources_or_services(self):
        with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'456','NOX_OWNER_SOURCE_SHA':'a'*40},clear=True), \
             patch.object(entry,'INITIAL_RECEIPT_SHA',''),patch.object(entry,'load') as load:
            with self.assertRaisesRegex(RuntimeError,'INSTALL_CONTEXT'):entry.main()
            load.assert_not_called()

    def test_priority_service_identity_excludes_foreign_process_groups(self):
        process={'pid':99,'service':entry.SERVICE,'pgrp':99,'state':'S','argv':['python',str(entry.SCHEDULER)]}
        helper=types.SimpleNamespace(program_config=lambda name:{'command':'python '+str(entry.SCHEDULER),
            'stopasgroup':'true'},service_state=lambda name:{'state':'RUNNING','pid':99},
            process=lambda pid:process,process_table=lambda:{99:process})
        self.assertEqual(entry.owned_scheduler(helper)['pid'],99)
        foreign={**process,'pid':100,'service':'nox-proxy'}
        helper.process_table=lambda:{99:process,100:foreign}
        with self.assertRaisesRegex(RuntimeError,'FOREIGN_PROCESS_GROUP'):entry.owned_scheduler(helper)


if __name__=='__main__':unittest.main()
