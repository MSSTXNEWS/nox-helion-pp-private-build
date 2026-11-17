"""One local journal boundary regression; no native process, HTTP or provider."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'final_inputs'))
import model_reference_changed_path_qa as qa


class DurableIntentAckLoss(unittest.TestCase):
    def test_committed_intent_ack_loss_never_sends_and_later_request_cannot_replay(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(qa.native, 'STATE', Path(directory)), patch(
                'socket.socket.connect', side_effect=AssertionError('NO_NETWORK')):
            client = qa.Client()
            with patch.object(client.opener, 'open', side_effect=AssertionError('NO_HTTP')) as opened:
                with qa.Journal('246802', 'a' * 40, 'b' * 32) as journal:
                    real_write = journal.write
                    def committed_then_ack_loss(name, value):
                        real_write(name, value)
                        if name == 'model_post_intent.json':
                            raise OSError('CONTROLLED_ACK_LOSS_AFTER_DURABLE_INTENT')
                    with patch.object(journal, 'write', side_effect=committed_then_ack_loss):
                        with self.assertRaises(OSError):
                            journal.send(client)
                    self.assertEqual(client.counts['model_post'], 0)
                    self.assertFalse(journal.sent)
                    intent = qa.document((journal.path / 'model_post_intent.json').read_bytes())
                    self.assertTrue(intent['single_send_attempt'])
                    self.assertEqual(intent['body_sha256'], qa.digest(qa.canonical(qa.body('b' * 32))))
                    # An acknowledgement failure does not erase the intent.
                    with self.assertRaises(FileExistsError):
                        journal.send(client)
                with self.assertRaisesRegex(qa.Hold, 'HOLD_QA_ALREADY_RESERVED_NO_RETRY'):
                    with qa.Journal('246803', 'c' * 40, 'd' * 32):
                        self.fail('A different request cannot replay this reserved QA purpose')
                opened.assert_not_called()
                self.assertEqual(client.counts['login_post'], 0)
                self.assertEqual(client.counts['model_post'], 0)
                self.assertEqual(client.counts['dialog_create_post'], 0)


if __name__ == '__main__':
    unittest.main()
