import ast
import json
from pathlib import Path
import unittest
import owner_subagent_observe_entry as observer


class ReadOnlyObserverTests(unittest.TestCase):
    def test_distinguishes_segment_hash_without_exporting_text_or_meta(self):
        receipt = {'task_id': 'owner.native.test', 'job_id': 'nox-native-example', 'phase': 'QUEUE_ADMITTED_NOT_EXECUTED'}
        text = 'NOX native job '+receipt['job_id']+' '+receipt['phase']+' receipt_sha256 '+observer.digest(observer.encoded(receipt))
        row = ('id', 'M2', text, 'owner_native_subagents', observer.digest(('M2|'+text).encode()), json.dumps({'receipt': receipt}))
        result = observer.record_diagnostic(receipt, row)
        self.assertTrue(result['segment_hash_matches'])
        self.assertFalse(result['plain_hash_matches'])
        self.assertTrue(result['meta_receipt_matches'])
        self.assertTrue(result['expected_text_matches'])
        self.assertNotIn(text, str(result))

    def test_wrong_metadata_is_not_an_accepted_receipt(self):
        receipt = {'task_id': 'owner.native.test', 'job_id': 'nox-native-example', 'phase': 'QUEUE_ADMITTED_NOT_EXECUTED'}
        result = observer.record_diagnostic(receipt, ('id', 'M2', 'unrelated private text', 'other', 'a'*64, '{}'))
        self.assertFalse(result['meta_receipt_matches'])
        self.assertFalse(result['expected_text_matches'])
        self.assertNotIn('unrelated private text', str(result))

    def test_observer_has_no_post_service_process_or_mutation_calls(self):
        tree = ast.parse(Path(observer.__file__).read_text())
        forbidden = {'remember', 'atomic', 'unlink', 'write_text', 'write_bytes', 'mkdir',
                     'Popen', 'run', 'start', 'terminate', 'kill', 'replace', 'chmod'}
        names = {node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
                 for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, (ast.Attribute, ast.Name))}
        self.assertFalse(names & forbidden)
        self.assertNotIn('POST', {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)})


if __name__ == '__main__':
    unittest.main(verbosity=2)
