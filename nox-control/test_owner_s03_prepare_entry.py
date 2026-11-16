import base64
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
SPEC=importlib.util.spec_from_file_location('owner_s03_prepare_entry',HERE/'owner_s03_prepare_entry.py')
e=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(e)


class PreparationTests(unittest.TestCase):
    def test_helper_pin_matches_frozen_file(self):
        self.assertEqual(hashlib.sha256((HERE/'owner_s03_gateway.py').read_bytes()).hexdigest(),e.HELPER_SHA)

    def test_source_prediction_does_not_activate_or_modify_native_preimage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'scripts').mkdir()
            source='def recall(): pass\ndef remember(): pass\ndef format_for_prompt(): pass\ndef persist_turn(): pass\n'
            native=root/'scripts/s03_memory.py';native.write_text(source)
            bundle={'owner_s03_gateway.py':base64.b64encode((HERE/'owner_s03_gateway.py').read_bytes()).decode()}
            with patch.object(e,'ROOT',root),patch.object(e,'BUNDLE',bundle),patch.object(e,'BASE_S03_SHA',hashlib.sha256(source.encode()).hexdigest()):
                helper,raw,after=e.load_helper()
                self.assertEqual(native.read_text(),source)
                self.assertNotEqual(after,hashlib.sha256(source.encode()).hexdigest())
                e.install_helper(helper,raw)
                self.assertEqual(hashlib.sha256((root/'scripts/owner_s03_gateway.py').read_bytes()).hexdigest(),e.HELPER_SHA)
                e.install_helper(helper,raw)
                self.assertEqual(native.read_text(),source)

    def test_wrong_bundle_or_existing_helper_never_overwrites_source(self):
        with patch.object(e,'BUNDLE',{'owner_s03_gateway.py':base64.b64encode(b'print("untrusted")').decode()}):
            with self.assertRaisesRegex(RuntimeError,'SOURCE_PIN'):e.load_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'scripts').mkdir();path=root/'scripts/owner_s03_gateway.py'
            path.write_text('existing different source')
            class Helper:
                plain=staticmethod(Path)
                file_sha=staticmethod(lambda target:hashlib.sha256(Path(target).read_bytes()).hexdigest())
            with patch.object(e,'ROOT',root):
                with self.assertRaisesRegex(RuntimeError,'HELPER_CHANGED'):e.install_helper(Helper,b'new source')
            self.assertEqual(path.read_text(),'existing different source')


if __name__=='__main__':unittest.main()
