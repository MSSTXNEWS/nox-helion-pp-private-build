import io
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import redirect_stdout
from creative_worker import serve_line
from nox_fastpack.engine import Studio

class WorkerProtocolTests(unittest.TestCase):
    def test_status_dispatch_line(self):
        with TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()) as buf:
                serve_line(Studio(Path(d)),json.dumps({'request_id':'b963b505-f360-440a-94d4-8a65ef45d637','payload':{'action':'catalog'}}))
            reply=json.loads(buf.getvalue().strip())
            self.assertTrue(reply['ok'])
            self.assertGreaterEqual(len(reply['data']['models']),5)

    def test_reject_invalid_path_and_unknown_action(self):
        with TemporaryDirectory() as d:
            studio=Studio(Path(d))
            for payload in ({'action':'project_files','project_id':'../sneak'},{'action':'run_shell','command':'whoami'}):
                with redirect_stdout(io.StringIO()) as buf:
                    serve_line(studio,json.dumps({'request_id':'b963b505-f360-440a-94d4-8a65ef45d637','payload':payload}))
                result=json.loads(buf.getvalue().strip())
                self.assertFalse(result['ok'])

if __name__=='__main__':unittest.main()
