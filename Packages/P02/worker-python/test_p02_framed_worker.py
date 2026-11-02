"""Deterministic byte transport regression against the one existing ingress."""
import io
import subprocess
import sys
import json
import struct
import threading
import unittest
from p02_native_ingress import NativeIngress, ProtocolHold
from p02_framed_worker import serve_native_frames

R = "NOX-FRAME-GATE-C10"

def request(n, route="chat.model", payload=None, **extra):
    x={"protocol":"NOX-P02-NATIVE-v1","requestId":f"{n:032x}",
       "route":route,"payload":payload if payload is not None else {},"runId":R}
    x.update(extra)
    return json.dumps(x, separators=(",", ":")).encode("utf-8")

def frames(*payloads):
    return b"".join(struct.pack(">I",len(x))+x for x in payloads)

def read_frames(blob):
    result=[];cursor=io.BytesIO(blob)
    while True:
        header=cursor.read(4)
        if not header:break
        self_size=struct.unpack(">I",header)[0]
        body=cursor.read(self_size)
        assert len(body)==self_size
        result.append(json.loads(body))
    return result

class Dispatch:
    def __init__(self):
        self.seen=[];self.ready=threading.Event();self.allow=threading.Event()
    def execute(self,route,payload,session):
        assert session=="native-only"
        self.seen.append(route)
        if route=="helion.chat":
            self.ready.set()
            if not self.allow.wait(1):raise RuntimeError("chat transport was never stopped")
        elif route=="chat.stop":
            self.allow.set()
        return {"r":route}

class Tests(unittest.TestCase):
    def setUp(self):
        self.d=Dispatch()
        self.ingress=NativeIngress(self.d, lambda:"native-only",expected_run_id=R)
    def serve(self,*data):
        output=io.BytesIO()
        n=serve_native_frames(self.ingress,io.BytesIO(frames(*data)),output)
        return n,read_frames(output.getvalue())
    def test_stop_overtakes_chat_and_reply_frames_keep_ids(self):
        n,rows=self.serve(request(1,"helion.chat"),request(2,"chat.stop"))
        self.assertEqual(n,2)
        self.assertEqual({x["requestId"] for x in rows},{f"{1:032x}",f"{2:032x}"})
        self.assertTrue(all(x["status"]=="OK" for x in rows))
        self.assertEqual(set(self.d.seen),{"helion.chat","chat.stop"})
    def test_invalid_native_session_is_hold_not_success(self):
        ingress=NativeIngress(self.d,lambda:None,expected_run_id=R)
        out=io.BytesIO()
        serve_native_frames(ingress,io.BytesIO(frames(request(3))),out)
        self.assertEqual(read_frames(out.getvalue())[0]["errorCode"],"NATIVE_AUTHENTICATED_SESSION_REQUIRED")
    def test_webview_authority_payload_denied(self):
        n,rows=self.serve(request(4,payload={"admin":True}))
        self.assertEqual(rows[0]["status"],"HOLD")
        self.assertEqual(rows[0]["errorCode"],"PAGE_AUTHORITY_CLAIM_DENIED")
        self.assertFalse(self.d.seen)
    def test_duplicate_nonce_denied_without_second_dispatch(self):
        # Each request may be processed while previous worker still drains;
        # either BUSY or replay-denied is safe, never two owner calls.
        n,rows=self.serve(request(5),request(5))
        self.assertEqual(n,2)
        self.assertEqual(len(self.d.seen),1)
        self.assertEqual(sorted(x["status"] for x in rows),["HOLD","OK"])
    def test_oversize_and_truncated_frames_fail_closed(self):
        for blob in (struct.pack(">I",65537),struct.pack(">I",99)+b"abc",b"\x00"):
            with self.subTest(blob=blob[:8]):
                with self.assertRaises(ProtocolHold):
                    serve_native_frames(self.ingress,io.BytesIO(blob),io.BytesIO())
    def test_outer_duplicate_stop_route_rejected_before_priority_dispatch(self):
        # A last-wins route must NOT bypass the strict preflight as STOP.
        bad = (b'{"protocol":"NOX-P02-NATIVE-v1","requestId":"0000000000000000000000000000000a",'
               b'"route":"helion.chat","route":"chat.stop","payload":{},"runId":"NOX-FRAME-GATE-C10"}')
        calls = []
        original = self.ingress.handle
        def counted(raw):
            calls.append(raw)
            return original(raw)
        self.ingress.handle = counted
        n, rows = self.serve(bad, request(16, "chat.stop"))
        self.assertEqual(n, 2)
        self.assertEqual([row["status"] for row in rows], ["HOLD", "OK"])
        self.assertEqual(rows[0]["errorCode"], "NATIVE_FRAME_INVALID_JSON")
        self.assertIsNone(rows[0]["requestId"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.d.seen, ["chat.stop"])

    def test_outer_nonfinite_and_nested_duplicate_do_not_reach_owner(self):
        # Reject malformed data at the framed priority switch, not only
        # inside NativeIngress.handle. Next authentic STOP must still work.
        bad_float = request(17).replace(b'"payload":{}', b'"payload":{"x":1e9999}')
        bad_dup = request(18).replace(b'"payload":{}', b'"payload":{"a":1,"a":2}')
        bad_nan = request(19).replace(b'"payload":{}', b'"payload":{"a":NaN}')
        calls = []
        original = self.ingress.handle
        def counted(raw):
            calls.append(raw)
            return original(raw)
        self.ingress.handle = counted
        n, rows = self.serve(bad_float, bad_dup, bad_nan, request(20, "chat.stop"))
        self.assertEqual(n, 4)
        self.assertEqual([row["status"] for row in rows], ["HOLD", "HOLD", "HOLD", "OK"])
        self.assertTrue(all(row["errorCode"] == "NATIVE_FRAME_INVALID_JSON" for row in rows[:3]))
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.d.seen, ["chat.stop"])

    def test_foreign_run_stays_denied(self):
        _,rows=self.serve(request(6,runId="not-our-run"))
        self.assertEqual(rows[0]["status"],"HOLD")
        self.assertEqual(rows[0]["errorCode"],"NATIVE_PROTOCOL_OR_RUN_MISMATCH")
    def test_actual_os_subprocess_stdin_stdout_frames(self):
        # Actual Windows/Linux child process + OS pipes, not a second service.
        code = """import sys
from p02_native_ingress import NativeIngress
from p02_framed_worker import serve_native_frames
class ExistingOwner:
 def execute(self,route,payload,session):
  assert session == 'native-only'
  return {'route':route,'status':'real-process-boundary'}
ingress=NativeIngress(ExistingOwner(),lambda:'native-only',expected_run_id='NOX-FRAME-GATE-C10')
serve_native_frames(ingress,sys.stdin.buffer,sys.stdout.buffer)
"""
        result=subprocess.run([sys.executable,'-c',code],input=frames(request(10)),
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              cwd=str(__import__('pathlib').Path(__file__).parent),
                              timeout=10,check=True)
        answers=read_frames(result.stdout)
        self.assertEqual(len(answers),1)
        self.assertEqual(answers[0]['status'],'OK')
        self.assertEqual(answers[0]['result']['status'],'real-process-boundary')

    def test_frame_size_includes_utf8_bytes_not_codepoints(self):
        req=request(7,payload={"text":"Привет"})
        n,rows=self.serve(req)
        self.assertEqual(n,1)
        self.assertEqual(rows[0]["status"],"OK")

if __name__=="__main__": unittest.main()
