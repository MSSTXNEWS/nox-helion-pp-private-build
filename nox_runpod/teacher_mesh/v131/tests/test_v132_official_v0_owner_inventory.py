"""Contract: prefer documented Vast v0 owner list without mutating GPU instances."""
import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch
from nox_runpod.teacher_mesh.v131 import vast_no_billing_inventory as inv


class OwnerInventory(unittest.TestCase):
    def test_canonical_v0_owner_list_is_checked_first(self):
        with patch.object(inv,'get') as mocked,patch.dict(os.environ,{'NOX2':'test-not-a-real-key'}):
            mocked.side_effect=lambda url,key: (200,{'instances':[{'id':inv.INSTANCE,'actual_status':'running'}]}) if url=='https://cloud.vast.ai/api/v0/instances/' else (404,None)
            out=io.StringIO()
            with contextlib.redirect_stdout(out):
                code=inv.main()
            self.assertEqual(code,0)
            self.assertTrue(mocked.call_args_list[0].args[0].endswith('/api/v0/instances/'))
            proof=next(line.split('=',1)[1] for line in out.getvalue().splitlines() if line.startswith('NOX_V131_VAST_READ_ONLY='))
            result=json.loads(proof)
            self.assertTrue(result['checks'][0]['target_present'])
            self.assertEqual(result['checks'][0]['target_status'],'running')
            self.assertTrue(result['no_new_billing'])
            self.assertFalse(result['ssh_key_created'])

    def test_all_404_does_not_claim_server_deleted_or_available(self):
        with patch.object(inv,'get',return_value=(404,None)),patch.dict(os.environ,{'NOX2':'test-not-a-real-key'}):
            out=io.StringIO()
            with contextlib.redirect_stdout(out):
                code=inv.main()
            self.assertEqual(code,2)
            result=json.loads(next(l.split('=',1)[1] for l in out.getvalue().splitlines() if l.startswith('NOX_V131_VAST_READ_ONLY=')))
            self.assertTrue(all(row['http']==404 for row in result['checks']))
            self.assertTrue(all(row['target_status']=='UNKNOWN' for row in result['checks']))
            self.assertEqual(len(result['checks']),6)
            self.assertTrue(result['no_new_billing'])

    def test_no_key_does_not_call_provider(self):
        with patch.dict(os.environ,{'NOX2':''}),patch.object(inv,'get') as mocked:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(inv.main(),2)
            mocked.assert_not_called()


if __name__ == '__main__':
    unittest.main()
