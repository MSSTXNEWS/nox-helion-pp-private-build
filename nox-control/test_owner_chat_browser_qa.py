"""Portable source/security tests; no browser or native NOX action is executed."""
import ast
import importlib.util
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('browser_qa',Path(__file__).with_name('owner_chat_browser_qa.py'))
QA=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QA)


class BrowserQaTests(unittest.TestCase):
    def test_browser_expected_build_matches_deployed_ui_renderer(self):
        tree = ast.parse(Path(QA.__file__).with_name('owner_chat_ui.py').read_text())
        builds = [ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'BUILD' for target in node.targets)]
        self.assertEqual(builds, [QA.BUILD])

    def test_resource_paths_never_include_query_credentials(self):
        self.assertEqual(QA.safe_route('http://127.0.0.1:8080/nox-web-v29/owner-chat-ui.js?token=secret'),
                         '/nox-web-v29/owner-chat-ui.js')
        self.assertEqual(QA.safe_route('http://127.0.0.1:8080/api/ui/memory/dialogs/history?dialog_id=private'),
                         '/api/ui/memory/dialogs/history')

    def test_unknown_paths_are_not_exported(self):
        for url in ('http://host/private_customer_name/file','http://host/api/user/alice',
                    'http://host/nox-web-v29/credential.txt','file:///root/nox/secrets/chat_password'):
            self.assertEqual(QA.safe_route(url),'[OTHER_ROUTE]')

    def test_only_bounded_public_numbers_can_be_exported(self):
        self.assertEqual(QA.public_numeric_answer('1, 2, 3, 4, 5, 6, 7, 8, 9, 10'),QA.EXPECTED)
        for value in ('owner Alice', 'token=abc', '<img src=x>', '1\nprivate context', '1'*101, None):
            self.assertIsNone(QA.public_numeric_answer(value))

    def test_exception_text_cannot_leak_credentials(self):
        self.assertEqual(QA.safe_error(RuntimeError('password=opaque credential')), 'RuntimeError')
        self.assertEqual(QA.safe_error(RuntimeError('HOLD_OWNER_STOP')), 'HOLD_OWNER_STOP')

    def test_click_diagnostic_exports_only_fixed_boolean_flags(self):
        value=QA.click_error_projection(RuntimeError('owner private title: element is not stable; another node intercepts pointer events'))
        self.assertEqual(set(value),{'not_stable','not_visible','outside_viewport','pointer_intercepted','detached'})
        self.assertTrue(value['not_stable']);self.assertTrue(value['pointer_intercepted'])
        self.assertTrue(all(type(flag) is bool for flag in value.values()))

    def test_screenshot_private_creation_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'image.png'
            QA.write_private(path,b'public fixture')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            with self.assertRaises(FileExistsError):
                QA.write_private(path,b'overwrite')
            self.assertEqual(path.read_bytes(),b'public fixture')

    def test_screenshot_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            real=Path(folder)/'other'
            real.write_bytes(b'preserve')
            link=Path(folder)/'image.png'
            link.symlink_to(real)
            with self.assertRaisesRegex(RuntimeError,'HOLD_BROWSER_ARTIFACT_SYMLINK'):
                QA.write_private(link,b'replace')
            self.assertEqual(real.read_bytes(),b'preserve')

    def test_instrumentation_forwards_real_calls_and_masks_private_regions(self):
        self.assertIn('Reflect.apply(original,this,args)',QA.OBSERVER_JS)
        self.assertIn('const response=await fetch0(input,init)',QA.OBSERVER_JS)
        self.assertIn('observe(response.clone())',QA.OBSERVER_JS)
        self.assertIn('#nativeChats',QA.SENSITIVE_MASKS)
        source=Path(QA.__file__).read_text()
        self.assertNotIn('route.fulfill(',source)
        self.assertNotIn('storage_state(',source)
        self.assertNotIn('base64',source)
        self.assertNotIn('install-deps',source)

    @unittest.skipUnless(shutil.which('node'),'Node unavailable for JS syntax check')
    def test_browser_javascript_parses(self):
        source=QA.OBSERVER_JS.replace('__CONFIG__','{"did":"'+'a'*32+'"}')+'\nconst snapshot=('+QA.SNAPSHOT_JS+');\n'
        result=subprocess.run([shutil.which('node'),'--check'],input=source,text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':
    unittest.main()
