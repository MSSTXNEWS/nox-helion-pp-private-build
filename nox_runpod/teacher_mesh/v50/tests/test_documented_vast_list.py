"""API request shape and native gate security regression tests — mocked only."""
import inspect
import unittest
from unittest.mock import patch
from nox_runpod.teacher_mesh.v50 import ephemeral_ssh_audit as m
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as v51

class DocumentedVastList(unittest.TestCase):
    def test_exact_instance_from_official_list(self):
        x=m.Vast("dummy-owner-key")
        with patch.object(x,"api",return_value={"instances":[
                {"id":7,"actual_status":"running"},
                {"id":60509551,"actual_status":"running"}]}) as mock_get:
            row=x.instance()
        self.assertEqual(row["id"],60509551)
        mock_get.assert_called_once_with("instances/")

    def test_wrong_owner_instance_never_accepted(self):
        x=m.Vast("dummy-owner-key")
        with patch.object(x,"api",return_value={"instances":[
                {"id":6,"actual_status":"running"}]}):
            with self.assertRaisesRegex(RuntimeError,"HOLD_VAST_INSTANCE_SCHEMA"):
                x.instance()

    def test_instance_list_delete_is_blocked_before_network(self):
        x=m.Vast("dummy-owner-key")
        with self.assertRaisesRegex(RuntimeError,"HOLD_API_METHOD"):
            x.api("instances/","DELETE")

    def test_v51_uses_list_not_unsupported_detail(self):
        source=inspect.getsource(v51.probe)
        self.assertIn('api("GET", "/instances/", key)',source)
        self.assertNotIn('api("GET", f"/instances/{INSTANCE}/", key)',source)

    def test_v51_v1_owner_list_and_pinned_host_before_attach(self):
        self.assertEqual(v51.LIST_API,
                         "https://console.vast.ai/api/v1/instances/?owner=me")
        self.assertIn("LIST_API if method", inspect.getsource(v51.api))
        source=inspect.getsource(v51.probe)
        self.assertLess(source.index("HOLD_UNVERIFIED_REMOTE_HOST_KEY"),
                        source.index('api("POST",'))
        self.assertIn("StrictHostKeyChecking=yes",source)

if __name__=="__main__":
    unittest.main()
