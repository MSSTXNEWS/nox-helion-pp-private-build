"""V131 source-only tests: fake owner API responses; no network or credentials."""
from __future__ import annotations
import io, json, os, unittest, urllib.error
from contextlib import redirect_stdout
from unittest.mock import patch
from nox_runpod.teacher_mesh.v131 import vast_no_billing_inventory as v


class VastInventorySource(unittest.TestCase):
    def test_v1_owner_scoped_list_not_deprecated_v0(self):
        script = v.main.__code__.co_consts.__repr__()
        self.assertIn("V1_CONSOLE_LIST", script)
        self.assertIn("V1_CLOUD_LIST", script)
        self.assertIn("owner=me", script)
        self.assertNotIn("V0_CONSOLE_LIST", script)
        self.assertNotIn("V0_CLOUD_LIST", script)

    def test_exact_owner_running_passes_metadata_only(self):
        with patch.object(v,"get",return_value=(200,{"instances":[
                {"id":60509551,"actual_status":"running"}]})):
            with patch.dict(os.environ,{"NOX2":"mocked-vast-key"}):
                output=io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(v.main(),0)
                self.assertIn("EXACT_EXISTING_RUNNING_INSTANCE=true",output.getvalue())
                self.assertIn("NATIVE_COMMAND_EXECUTED=false",output.getvalue())

    def test_wrong_instance_and_404_auth_hold(self):
        for code,payload in [(200,{"instances":[{"id":23,"actual_status":"running"}]}),
                             (404,{"error":"auth_error"})]:
            with patch.object(v,"get",return_value=(code,payload)):
                with patch.dict(os.environ,{"NOX2":"mocked-vast-key"}):
                    output=io.StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(v.main(),2)
                    self.assertIn("EXACT_EXISTING_RUNNING_INSTANCE=false",output.getvalue())
                    if code==404:self.assertIn('"provider_error":"auth_error"',output.getvalue())

    def test_storage_key_never_dispatched(self):
        with patch.object(v,"get",side_effect=AssertionError("unexpected network access")):
            with patch.dict(os.environ,{"NOX2":"tid_storage_credential"}):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(v.main(),2)

    def test_unpack_nested(self):
        self.assertEqual(v.unpack({"data":{"instances":[{"id":60509551}]}}),
                         [{"id":60509551}])

if __name__=="__main__":
    unittest.main()
