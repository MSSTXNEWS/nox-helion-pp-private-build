"""R12 regression: native read-only busy retry never replays side-effecting commands."""
import unittest
from unittest.mock import patch
from coordination.e06.native_onehost_smoke import NativeExe, SmokeFailed

class NativeBusyRetryTests(unittest.TestCase):
    def client(self, outcomes):
        instance=object.__new__(NativeExe)
        state={"sent":[],"queue":list(outcomes)}
        def send(route,payload):
            nonce=f"request-{len(state['sent'])+1}"
            state["sent"].append((route,payload,nonce))
            return nonce
        def receive(deadline):
            status,code=state["queue"].pop(0)
            nonce=state["sent"][-1][2]
            frame={"requestId":nonce,"status":status}
            if status=="HOLD":frame["errorCode"]=code
            elif status=="OK":frame["result"]={}
            return frame
        instance.send=send
        instance.receive=receive
        return instance,state

    @patch("coordination.e06.native_onehost_smoke.time.sleep",return_value=None)
    def test_transient_readonly_history_busy_recovers(self,_sleep):
        client,state=self.client([("HOLD","NATIVE_BUSY"),("HOLD","NATIVE_BUSY"),("OK",None)])
        result,_=client.request("chat.history",{"core_id":"core.core"},30)
        self.assertEqual(result["status"],"OK")
        self.assertEqual(len(state["sent"]),3)
        self.assertEqual(len({x[2] for x in state["sent"]}),3)

    @patch("coordination.e06.native_onehost_smoke.time.sleep",return_value=None)
    def test_readonly_inventory_busy_recovers(self,_sleep):
        client,state=self.client([("HOLD","NATIVE_BUSY"),("OK",None)])
        self.assertEqual(client.request("chat.model",{},30)[0]["status"],"OK")
        self.assertEqual(len(state["sent"]),2)

    @patch("coordination.e06.native_onehost_smoke.time.sleep",return_value=None)
    def test_persistent_busy_remains_hard_failure(self,_sleep):
        client,state=self.client([("HOLD","NATIVE_BUSY")]*4)
        with self.assertRaisesRegex(SmokeFailed,"NATIVE_READONLY_BUSY_PERSISTED_CHAT_MODEL"):
            client.request("chat.model",{},30)
        self.assertEqual(len(state["sent"]),4)

    def test_no_retry_of_chat(self):
        client,state=self.client([("HOLD","NATIVE_BUSY")])
        result,_=client.request("helion.chat",{"text":"test"},30)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(len(state["sent"]),1)

    def test_no_retry_of_stop(self):
        client,state=self.client([("HOLD","NATIVE_BUSY")])
        result,_=client.request("chat.stop",{},30)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(len(state["sent"]),1)

    def test_no_retry_of_model_selection(self):
        client,state=self.client([("HOLD","NATIVE_BUSY")])
        result,_=client.request("chat.model",{"model":"approved"},30)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(len(state["sent"]),1)

    def test_other_hold_not_masked(self):
        client,state=self.client([("HOLD","NATIVE_PROVIDER_HOLD")])
        result,_=client.request("chat.history",{},30)
        self.assertEqual(result["errorCode"],"NATIVE_PROVIDER_HOLD")
        self.assertEqual(len(state["sent"]),1)

if __name__=="__main__": unittest.main()
