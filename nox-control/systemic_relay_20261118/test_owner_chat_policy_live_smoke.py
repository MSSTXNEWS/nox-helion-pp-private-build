"""Source-only tests; never opens network connections or changes native files."""
import importlib.util
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

path=Path(__file__).with_name("owner_chat_policy_live_smoke.py")
spec=importlib.util.spec_from_file_location("nox_synthetic_smoke",path)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class SmokeSourceTests(TestCase):
    def test_hard_stop_precedes_network_and_source_reads(self):
        with patch.object(m.os.path,"lexists",return_value=True), patch.object(
            m,"source_status",side_effect=AssertionError("Should not read source on STOP")
        ):
            with self.assertRaisesRegex(RuntimeError,"HOLD_LIVE_SMOKE_STOP"):
                m.guards()

    def test_process_identity_uses_start_ticks(self):
        fields=[b"S",b"114",b"242298"]+[b"0"]*16+[b"183262723"]
        raw=b"242298 (python3) "+b" ".join(fields)
        with patch.object(Path,"read_bytes",return_value=raw):
            self.assertTrue(m.process_same(242298,183262723))
            self.assertFalse(m.process_same(242298,183262724))

    def test_legacy_model_port_falls_back_to_existing_8098_without_network(self):
        import subprocess
        from urllib.error import URLError
        class Response:
            status=200
            def __init__(self,body):self.body=body
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,maximum=None):return self.body
        class Opener:
            def open(self,url,timeout=None):
                if url.endswith(":8080/health"):return Response(b"OK")
                if url.endswith(":8081/slots"):raise URLError("offline")
                if url.endswith(":8098/slots"):return Response(b'[{"is_processing": false}]')
                raise AssertionError("unexpected target")
        proc=subprocess.CompletedProcess([],0,stdout="nox-proxy RUNNING\nnox-ds41-8098 RUNNING\nnox-dispatcher-t855u RUNNING\n",stderr="")
        with patch.object(m.os.path,"lexists",return_value=False), patch.object(
            m,"source_status",return_value=True
        ), patch.object(m,"process_same",return_value=True), patch.object(
            m.subprocess,"run",return_value=proc
        ), patch.object(m.urllib.request,"build_opener",return_value=Opener()):
            outcome=m.guards()
        self.assertEqual(outcome["slot_port"],8098)
        self.assertEqual(outcome["slots"],1)

    def test_sse_and_ndjson_frame_parsing(self):
        self.assertEqual(m.parse_frame_line(b'data: {"type":"delta","text":"test"}\n'),
                         {"type":"delta","text":"test"})
        self.assertEqual(m.parse_frame_line(b'{"type":"done","status":"done"}\n'),
                         {"type":"done","status":"done"})
        self.assertEqual(m.parse_frame_line(b'data: [DONE]\n'), {"type":"sentinel"})
        self.assertIsNone(m.parse_frame_line(b'event: message\n'))
        self.assertIsNone(m.parse_frame_line(b'\n'))
        with self.assertRaisesRegex(RuntimeError,"HOLD_LIVE_SMOKE_SSE_JSON"):
            m.parse_frame_line(b'data: unfinished JSON\n')

    def test_qa_is_bounded_and_not_exposing_output(self):
        source=path.read_text()
        self.assertIn("result+=token",source)
        self.assertIn('answer_sha256',source)
        self.assertIn('"raw_content_exported":False',source)
        self.assertIn('"credentials_exported":False',source)
        self.assertIn('"/api/nox/chat/stream"',source)
        self.assertIn('"saved_verified"',source)
        self.assertIn("if not substantive",source)
        self.assertIn("time.monotonic()-start>105",source)


if __name__=="__main__":main()
