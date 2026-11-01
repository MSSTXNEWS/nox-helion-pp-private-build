"""C03 original S03/P02 adapter: explicit native denial must never write history.
Run in the EXISTING NOX EXPRESS source checkout:
  PYTHONPATH=src python -m unittest discover -s tests/k02 -p test_c03_native_auth_result.py -v
No new store, service, model, network, or Windows-release claim.
"""
from pathlib import Path
import tempfile
import unittest
from helion.storage import Store
from nox_selfbuilder.onehost_store import OneHostStoreActor
from nox_selfbuilder.original_store_adapter import OriginalStoreChatAdapter


class NativeAuthorizationResultContract(unittest.TestCase):
    def check_denial(self, denied_call):
        with tempfile.TemporaryDirectory() as root:
            with OneHostStoreActor(lambda: Store(Path(root) / 'helion.sqlite3')) as actor:
                chat = OriginalStoreChatAdapter(actor)
                with chat.model_context('reviewed-local-model:test'):
                    self.assertEqual(chat.history('local', 'owner', 'default'), [])
                    calls = []
                    def native_authorize():
                        calls.append(1)
                        return False if len(calls) == denied_call else True
                    with self.assertRaisesRegex(PermissionError, 'ORIGINAL_CHAT_NATIVE_AUTH_REVOKED'):
                        chat.add_exchange('local', 'owner', 'default',
                                          'question', 'answer', authorize=native_authorize)
                self.assertEqual(chat.history('local', 'owner', 'default'), [])

    def test_denied_before_transaction(self):
        self.check_denial(1)

    def test_denied_after_begin_rolls_back(self):
        self.check_denial(2)

    def test_denied_after_insert_rolls_back(self):
        self.check_denial(3)

    def test_legacy_raise_on_revoke_none_on_success_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            with OneHostStoreActor(lambda: Store(Path(root) / 'helion.sqlite3')) as actor:
                chat = OriginalStoreChatAdapter(actor)
                with chat.model_context('reviewed-local-model:test'):
                    chat.history('local', 'owner', 'default')
                    chat.add_exchange('local', 'owner', 'default',
                                      'question', 'answer', authorize=lambda: None)
                self.assertEqual(len(chat.history('local', 'owner', 'default')), 2)


if __name__ == '__main__':
    unittest.main()