import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('browser_diagnostic',Path(__file__).with_name('owner_browser_diagnostic.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class DiagnosticTests(unittest.TestCase):
    def test_raw_launch_error_projects_only_library_names_and_codes(self):
        raw=b'/private/owner/path: error while loading shared libraries: libnss3.so: cannot open shared object file: No such file\nlibatk-1.0.so.0 => not found\npassword=never-export\n'
        self.assertEqual(m.missing_libraries(raw),['libatk-1.0.so.0','libnss3.so'])
        self.assertEqual(m.failure_tags(raw),['MISSING_SHARED_LIBRARY'])
        self.assertNotIn('private',json.dumps(m.missing_libraries(raw)))

    def test_owned_subprocess_has_output_and_time_bounds(self):
        result=m.bounded_command([sys.executable,'-c','print("x"*100000)'],dict(os.environ),2,1000)
        self.assertEqual(result['bounded_stop'],'OUTPUT_LIMIT')
        self.assertLessEqual(len(result['stdout'])+len(result['stderr']),1000)
        start=time.monotonic()
        result=m.bounded_command([sys.executable,'-c','import time;time.sleep(5)'],dict(os.environ),0.1)
        self.assertEqual(result['bounded_stop'],'TIMEOUT')
        self.assertLess(time.monotonic()-start,1)

    def test_private_reader_rejects_fifo_without_blocking(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fifo';os.mkfifo(path)
            start=time.monotonic()
            with self.assertRaisesRegex(RuntimeError,'FILE_TYPE'):m.read(path)
            self.assertLess(time.monotonic()-start,0.1)

    def test_media_projection_does_not_export_log_text_or_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state=root/'state/owner_media';state.mkdir(parents=True)
            request='6903919663'
            (state/'prepare_job.json').write_text(json.dumps({'request':request,'source_sha':'a'*40,'pid':0,
                                                            'installer_sha256':'b'*64,'log':'/private/unrelated'}))
            logs=root/'logs';logs.mkdir()
            rows=[{'phase':'download','file':'sdxl_lightning_4step.safetensors','bytes':1024,'total':6938040682},
                  {'phase':'isolated_dependency_closure','ok':False,'issues':[{'package':'requests','reason':'MISSING'}]},
                  {'phase':'private','secret':'never-export'}]
            (logs/('owner_media_prepare_'+request+'.log')).write_text('password=never-export\n'+
                '\n'.join('NOX_MEDIA_INSTALL='+json.dumps(row) for row in rows))
            with patch.object(m,'ROOT',root):value=m.media_progress()
            self.assertEqual(value['request'],request)
            self.assertFalse(value['restarted'])
            self.assertEqual(len(value['events']),2)
            self.assertEqual(value['events'][1]['issues'],[{'package':'requests','reason':'MISSING'}])
            self.assertNotIn('never-export',json.dumps(value))
            self.assertNotIn('/private',json.dumps(value))

    def test_launch_probe_has_no_auth_or_backend_access(self):
        compile(m.CHILD,'<isolated-launch-probe>','exec')
        self.assertIn("page.goto('about:blank'",m.CHILD)
        self.assertNotIn('chat_proxy',m.CHILD)
        self.assertNotIn('/chat/login',m.CHILD)
        self.assertNotIn('8080',m.CHILD)
        self.assertIn("child_env['CUDA_VISIBLE_DEVICES']=''",m.CHILD)


if __name__=='__main__':unittest.main()
