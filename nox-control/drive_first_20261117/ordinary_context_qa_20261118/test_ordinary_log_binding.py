"""One focused append-window/privacy/inode regression; no HTTP or app import."""
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import model_reference_changed_path_qa as qa


class OrdinaryLogBinding(unittest.TestCase):
    def test_only_current_inode_marker_supports_context_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'proxy.log'
            path.write_text('PRIVATE_OTHER_USER_BEFORE\n')
            suffix = ' user=' + repr(qa.QUESTION.replace('\n', ' ')[:80])
            line = '2026-11-18 02:04:05 +0100 chat_timing build_ms=734 cedr_ready=False seed=123 cache_prompt=True' + suffix
            with patch.object(qa, 'TIMING_LOG', path):
                window = qa.TimingLogWindow()
                try:
                    with path.open('a') as output:
                        output.write('PRIVATE_OTHER_USER_DURING\n' + line + '\nunfinished unrelated data')
                    evidence = window.observe()
                    self.assertEqual(evidence['status'], 'SOURCE_INFERRED_CONTEXT_HELPER_RETURNED')
                    self.assertEqual(evidence['build_ms'], 734)
                    self.assertEqual(evidence['marker_sha256'], qa.digest(line.encode()))
                    public = json.dumps(evidence, ensure_ascii=False)
                    self.assertNotIn('PRIVATE_OTHER_USER', public)
                    self.assertNotIn(qa.QUESTION[:80], public)
                    self.assertLessEqual(evidence['log_bytes_read'], qa.MAX_LOG_READ_BYTES)
                    self.assertIsNone(evidence['exact_tokenizer_rounds'])
                    self.assertFalse(evidence['actual_function_trace_observed'])
                finally:
                    window.close()
                with path.open('a') as output:
                    output.write('\n')
                rotated = qa.TimingLogWindow()
                try:
                    with path.open('a') as output:
                        output.write(line + '\n')
                    replacement = Path(directory) / 'replacement'
                    replacement.write_bytes(path.read_bytes())
                    os.replace(replacement, path)
                    with self.assertRaisesRegex(qa.Hold, '^HOLD_CONTEXT_LOG_INODE_CHANGED$'):
                        rotated.observe()
                finally:
                    rotated.close()


if __name__ == '__main__':
    unittest.main()
