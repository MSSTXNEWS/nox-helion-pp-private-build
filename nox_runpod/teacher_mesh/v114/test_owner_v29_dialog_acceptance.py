"""Source-only guards for the V114 dialog acceptance gate."""
import importlib.util
from pathlib import Path
import re
import unittest

SOURCE = Path(__file__).with_name('owner_v29_dialog_acceptance.py')
SPEC = importlib.util.spec_from_file_location('v114_dialog_acceptance', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def validators():
    start = MODULE.REMOTE.index('def canonical_s03_receipt')
    end = MODULE.REMOTE.index('opener=None', start)
    namespace = {'re': re}
    exec(compile(MODULE.REMOTE[start:end], '<v114-canonical-s03-validators>', 'exec'), namespace)
    return namespace


class V114DialogAcceptanceTests(unittest.TestCase):
    def test_embedded_remote_source_compiles_without_execution(self):
        start = MODULE.REMOTE.index("<<'PYREMOTE'\n") + len("<<'PYREMOTE'\n")
        end = MODULE.REMOTE.index('\nPYREMOTE', start)
        compile(MODULE.REMOTE[start:end], '<v114-remote-source>', 'exec')

    def test_dialog_only_alias_cannot_pass_canonical_s03_gate(self):
        gate = validators()
        did = 'a' * 32
        alias_only = {'saved': True, 's03_integrated': True, 'dialog_id': did,
                      'exchange_id': 'public-exchange'}
        owner_dialog = {'saved': True, 's03_integrated': False,
                        'owner_dialog_saved': True,
                        'canonical_s03_write_verified': False,
                        'store_scope': 'OWNER_DIALOG_TABLES_ONLY',
                        'dialog_id': did, 'exchange_id': 'public-exchange'}
        self.assertFalse(gate['canonical_s03_receipt'](alias_only, did))
        self.assertFalse(gate['canonical_s03_receipt'](owner_dialog, did))

    def test_dialog_history_requires_explicit_canonical_readback_scope(self):
        gate = validators()
        did, prompt, answer, exchange = 'a' * 32, 'public prompt', 'public answer', 'public-exchange'
        owner_only = {'status': 'READY', 'dialog_id': did,
                      'store_scope': 'OWNER_DIALOG_TABLES_ONLY',
                      'canonical_s03_readback_verified': False,
                      'messages': [
                          {'role': 'user', 'content': prompt, 'exchange_id': exchange},
                          {'role': 'assistant', 'content': answer, 'exchange_id': exchange}]}
        unscoped = dict(owner_only, store_scope=None, canonical_s03_readback_verified=True)
        self.assertFalse(gate['canonical_s03_history'](owner_only, did, prompt, answer, exchange))
        self.assertFalse(gate['canonical_s03_history'](unscoped, did, prompt, answer, exchange))

    def test_acceptance_path_uses_both_proof_gates(self):
        source = MODULE.REMOTE
        self.assertIn('not canonical_s03_receipt(receipt,dialog_id)', source)
        self.assertIn('not canonical_s03_history(history,dialog_id,prompt,answer,receipt[\'exchange_id\'])', source)
        self.assertNotIn("receipt.get('s03_integrated') is not True or", source)


if __name__ == '__main__':
    unittest.main()
