"""Negative regressions for native local configuration, never UI authority."""
import importlib.util
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Packages/P02/worker-python'),str(ROOT/'Packages/P03/Source/python-host'),str(ROOT/'src')]
spec=importlib.util.spec_from_file_location('nox_native_bridge',ROOT/'proposals/NOX-PACK01-50/native_bridge.py')
bridge=importlib.util.module_from_spec(spec);sys.modules[spec.name]=bridge;spec.loader.exec_module(bridge)
spec=importlib.util.spec_from_file_location('k01_config_owner',ROOT/'coordination/e06/e06_native_stdio_owner.py')
owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)

class NativeConfigTest(unittest.TestCase):
    def test_absent_configuration_keeps_read_services_available(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(owner.load_native_config(Path(d)),{})
    def test_config_cannot_grant_consent_or_duplicate_fields(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'onehost-native-config.json'
            for text in ['{"version":1,"nativeConsent":true}', '{"version":1,"version":1}',
                         '{"version":1,"source_paths":["../outside.py"]}']:
                with self.subTest(text=text):
                    p.write_text(text)
                    with self.assertRaises(ValueError):owner.load_native_config(Path(d))
    def test_native_config_cannot_redirect_through_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target=root/'outside.json';target.write_text('{"version":1}')
            (root/'onehost-native-config.json').symlink_to(target)
            with self.assertRaises(ValueError):owner.load_native_config(root)
    def test_page_cannot_supply_unvalidated_actor(self):
        with self.assertRaisesRegex(RuntimeError,'ORIGINAL_STORE_ACTOR_REQUIRED'):
            owner.create_existing_ingress(object(),'test')
    def test_configured_interpreter_requires_exact_native_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);exe=root/'python.exe';exe.write_bytes(b'fixture-only-not-executed')
            cfg=root/'onehost-native-config.json'
            cfg.write_text(json.dumps({'version':1,'forge_python_exe':str(exe),
                                       'forge_python_sha256':'0'*64}))
            with self.assertRaisesRegex(ValueError,'INTERPRETER_SHA_HOLD'):
                owner.load_native_config(root)
            cfg.write_text(json.dumps({'version':1,'forge_python_exe':str(exe),
                'forge_python_sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}))
            self.assertEqual(owner.load_native_config(root)['forge_python_exe'],exe)

if __name__=='__main__':unittest.main()
