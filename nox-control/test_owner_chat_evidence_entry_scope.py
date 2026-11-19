"""Guard the live owner evidence source against canonical-S03 mislabeling."""
import importlib.util
from pathlib import Path
import unittest

PATH=Path(__file__).with_name('owner_chat_evidence_entry.py')
SPEC=importlib.util.spec_from_file_location('owner_chat_evidence_scope_test',PATH)
ENTRY=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENTRY)


class OwnerChatEvidenceScopeTests(unittest.TestCase):
    def test_dialog_probe_requires_explicit_owner_table_receipt_and_history_scope(self):
        source=ENTRY.HTTP_PROBE
        self.assertIn("done.get('owner_dialog_saved') is not True",source)
        self.assertIn("done.get('s03_integrated') is not False",source)
        self.assertIn("done.get('canonical_s03_write_verified') is not False",source)
        self.assertIn("done.get('writer')!='V112_OWNER_DIALOG_WRITER'",source)
        self.assertIn("history.get('store_scope')!='OWNER_DIALOG_TABLES_ONLY'",source)
        self.assertIn("history.get('canonical_s03_readback_verified') is not False",source)
        self.assertNotIn("done.get('s03_integrated') is not True",source)
        self.assertIn("'synthetic_owner_dialog_history_readback':True",source)
        self.assertIn("'canonical_s03_readback_verified':False",source)
        self.assertIn("'onehost_1a01_acceptance_state':'HOLD_CANONICAL_S03_WRITER_AND_READBACK_NOT_BOUND'",source)


if __name__=='__main__':unittest.main()
