"""Source-only tests: no Vast API calls and no server access."""
import unittest
from unittest import mock
from nox_runpod.teacher_mesh.v50 import ephemeral_ssh_audit as e


class FakeVast:
    def __init__(self,*,bad_revoke=False,attach_denied=False):
        self.public=None
        self.bad_revoke=bad_revoke
        self.attach_denied=attach_denied
        self.revoke_calls=0
        self.read_calls=0

    def instance(self):
        return {"id":60509551,"actual_status":"running",
                "ssh_host":"ssh9.vast.ai","ssh_port":26623}

    def keys(self):
        self.read_calls+=1
        return ([{"id":4471,"public_key":self.public}] if self.public else [])

    def attach(self, public):
        if self.attach_denied:
            raise RuntimeError("HOLD_ATTACH_DENIED")
        self.public=public

    def detach(self, key_id):
        self.revoke_calls+=1
        if self.bad_revoke:
            raise RuntimeError("HOLD_REVOKE_DENIED")
        if key_id!=4471:
            raise AssertionError("must revoke only our own key")
        self.public=None


class TestKeyParsing(unittest.TestCase):
    def test_ssh_keys_json_list(self):
        records=e.parse_ssh_keys({"ssh_keys":'[{"id":34,"public_key":"ssh-ed25519 QUJD owner"}]'})
        self.assertEqual(records[0]["id"],34)

    def test_unexpected_list_schema_hold(self):
        with self.assertRaises(RuntimeError):
            e.parse_ssh_keys({"ssh_keys":"{}"})

    def test_public_key_comment_ignored(self):
        v="ssh-ed25519 QUJD owner"
        self.assertEqual(e.find_key_id([{"id":123,"public_key":"ssh-ed25519 QUJD other"}],v),123)

    def test_other_key_never_selected(self):
        v="ssh-ed25519 QUJD owner"
        self.assertIsNone(e.find_key_id([{"id":999,"public_key":"ssh-ed25519 REVG other"}],v))

    def test_public_key_malformed(self):
        self.assertIsNone(e.public_key_identity("private-key fake"))

    def test_route_rejects_unknown_host(self):
        with self.assertRaises(RuntimeError):
            e.validated_route({"id":60509551,"actual_status":"running",
                               "ssh_host":"evil.example","ssh_port":22})

    def test_route_rejects_stopped(self):
        with self.assertRaises(RuntimeError):
            e.validated_route({"id":60509551,"actual_status":"stopped",
                               "ssh_host":"ssh9.vast.ai","ssh_port":26623})

    def test_ssh_vast_route(self):
        self.assertEqual(e.validated_route({"id":60509551,"actual_status":"running",
                                             "ssh_host":"ssh9.vast.ai","ssh_port":26623}),
                         ("ssh9.vast.ai",26623))


class TestBoundedAudit(unittest.TestCase):
    @mock.patch.object(e,"ssh_audit")
    def test_success_revokes(self,remote):
        remote.return_value={"native_verified":True,"exit_code":0,"resource_readback":{"gpus":[]}}
        vast=FakeVast()
        out=e.audit(vast)
        self.assertTrue(out["api_verified"])
        self.assertTrue(out["native_verified"])
        self.assertTrue(out["ssh_key_detached_verified"])
        self.assertEqual(vast.revoke_calls,1)
        self.assertIsNone(vast.public)
        remote.assert_called_once()

    @mock.patch.object(e,"ssh_audit")
    def test_remote_failure_still_revokes(self,remote):
        remote.return_value={"native_verified":False,"exit_code":255}
        vast=FakeVast()
        out=e.audit(vast)
        self.assertFalse(out["native_verified"])
        self.assertTrue(out["ssh_key_detached_verified"])
        self.assertEqual(vast.revoke_calls,1)

    @mock.patch.object(e,"ssh_audit")
    def test_failed_revoke_never_pass(self,remote):
        remote.return_value={"native_verified":True,"exit_code":0}
        vast=FakeVast(bad_revoke=True)
        out=e.audit(vast)
        self.assertFalse(out["ssh_key_detached_verified"])
        self.assertEqual(out.get("cleanup_hold"),"HOLD_REVOKE_NOT_VERIFIED")
        self.assertEqual(vast.revoke_calls,1)

    @mock.patch.object(e,"ssh_audit")
    def test_attach_denied_no_remote_call(self,remote):
        out=e.audit(FakeVast(attach_denied=True))
        self.assertEqual(out["reason"],"HOLD_ATTACH_DENIED")
        remote.assert_not_called()

    @mock.patch.object(e,"ssh_audit")
    def test_no_vast_instance_remote_call(self,remote):
        class Bad(FakeVast):
            def instance(self):
                return {"id":123,"actual_status":"running"}
        out=e.audit(Bad())
        self.assertEqual(out["reason"],"HOLD_INSTANCE_NOT_RUNNING")
        remote.assert_not_called()

    def test_error_classification_removes_sensitive_stderr(self):
        self.assertEqual(e.classify_ssh_error("Permission denied (publickey)"),"AUTH_DENIED")
        self.assertEqual(e.classify_ssh_error("Host key verification failed."),"HOST_KEY_REJECTED")
        self.assertEqual(e.classify_ssh_error("ssh: connect to host secret 1234: Connection refused"),"CONNECT_REFUSED")
        self.assertEqual(e.classify_ssh_error("secret remote info without signature"),"UNKNOWN_SSH_ERROR")

    def test_api_whitelist(self):
        with self.assertRaises(RuntimeError):
            e.Vast("valid-test-key-123456").api("instances/60509551/","DELETE")


if __name__=="__main__":
    unittest.main()
