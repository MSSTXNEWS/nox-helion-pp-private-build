"""Focused output-privacy and exact two-read contract; no native access."""
import json
from types import SimpleNamespace
import unittest

import UI_CURRENT_SOURCE_PROJECTION as ui


class ExistingReaderFixture:
    def __init__(self, missing_html=False):
        self.calls = []
        self.guards = 0
        self.missing_html = missing_html

    def guard(self):
        self.guards += 1

    def check(self):
        pass

    def read(self, path, limit):
        self.calls.append((path, limit))
        if path.endswith('/chat.html'):
            if self.missing_html:
                raise FileNotFoundError('DO_NOT_EXPORT_EXCEPTION_TOKEN')
            raw = (b'<script src="/nox-web-v29/nox-ui.js?token=DO_NOT_EXPORT_QUERY#private"></script>'
                   b'<script src="./pc/v25/nox-shell-v25.js?key=PRIVATE_KEY"></script>'
                   b'<script src="https://user:PRIVATE_PASSWORD@example.test/private.js"></script>'
                   b'<script src="data:text/javascript,PRIVATE_INLINE"></script>'
                   b'<script src="/vendor/percent%3fPRIVATE_TOKEN.js"></script>'
                   b'<script>PRIVATE_BODY</script>')
        else:
            raw = b"function legacyNav() { d.className = 'n25-dock'; }"
        return raw, SimpleNamespace(st_dev=36, st_ino=901, st_uid=0, st_gid=0, st_mode=0o100644)


class CurrentUIProjectionTest(unittest.TestCase):
    def test_only_two_bounded_paths_and_sanitized_output(self):
        for missing in (False, True):
            with self.subTest(missing_html=missing):
                reader = ExistingReaderFixture(missing)
                value = ui.project(reader)
                self.assertEqual(reader.calls, list(ui.READSET))
                self.assertEqual(reader.guards, 2)
                self.assertLessEqual(value['content_bytes_read'], 262144)
                self.assertFalse(value['actual_visibility_proven'])
                output = json.dumps(value)
                for secret in ('DO_NOT_EXPORT', 'PRIVATE_', 'example.test', '?token=', 'key='):
                    self.assertNotIn(secret, output)
                if missing:
                    self.assertEqual(value['status'], 'PARTIAL_FILE_PROJECTION')
                else:
                    self.assertEqual(value['files'][0]['script_src_paths'],
                                     ['/nox-web-v29/nox-ui.js', './pc/v25/nox-shell-v25.js'])
                    self.assertTrue(value['files'][0]['direct_v25_shell_script_included'])
                    self.assertTrue(value['files'][1]['n25_dock_literal_present'])


if __name__ == '__main__':
    unittest.main()
