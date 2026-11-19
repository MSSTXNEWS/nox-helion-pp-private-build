"""Exact source closure and rejection before executable issuer definitions."""
import base64
import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest import mock


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


E = load('owner_qwen_successor_entry_v2')
I = load('owner_qwen_successor_install_v2')


class EntryTests(unittest.TestCase):
    def test_actual_thirteen_source_assets_bind_native_aliases_without_main(self):
        names = [E.ISSUER, *I.CANDIDATES, *I.UTILITIES]
        bundle = {name: base64.b64encode(Path(__file__).with_name(name).read_bytes()).decode('ascii') for name in names}
        with mock.patch.object(E, 'BUNDLE', bundle):
            value = E.prepared()
        assets = value.assets()
        self.assertEqual(len(names), 13)
        self.assertEqual(len(value.BUNDLE), 13)
        self.assertEqual(set(assets), {*I.CANDIDATES.values(), *I.UTILITIES, I.SELF})
        self.assertEqual(hashlib.sha256(assets[I.SELF]).hexdigest(), E.ISSUER_SHA)
        self.assertEqual(value.__file__, '/root/nox/scripts/' + I.SELF)
        for name, native in I.CANDIDATES.items():
            self.assertEqual(hashlib.sha256(assets[native]).hexdigest(), I.PINS[name])
        self.assertNotIn(E.ISSUER, value.BUNDLE)
        self.assertEqual(Path(E.__file__).read_text().count('__NOX_BUNDLE_JSON__'), 1)

    def test_bad_issuer_rejected_before_module_creation_or_execution(self):
        bundle = {E.ISSUER: base64.b64encode(b'raise RuntimeError("must not execute")').decode('ascii')}
        with mock.patch.object(E, 'BUNDLE', bundle), mock.patch.object(E.types, 'ModuleType') as constructor:
            with self.assertRaisesRegex(RuntimeError, 'ISSUER_PIN'):
                E.prepared()
            constructor.assert_not_called()

    def test_missing_or_changed_dependency_never_reaches_main(self):
        names = [E.ISSUER, *I.CANDIDATES, *I.UTILITIES]
        original = {name: base64.b64encode(Path(__file__).with_name(name).read_bytes()).decode('ascii') for name in names}
        for replacement in (None, base64.b64encode(b'# changed watcher').decode('ascii')):
            bundle = dict(original)
            if replacement is None:
                del bundle[I.WATCHER]
                reason = 'DEPENDENCY_CLOSURE'
            else:
                bundle[I.WATCHER] = replacement
                reason = 'BUNDLE_PIN'
            with mock.patch.object(E, 'BUNDLE', bundle):
                with self.assertRaisesRegex(RuntimeError, reason):
                    E.prepared()


if __name__ == '__main__':
    unittest.main()
