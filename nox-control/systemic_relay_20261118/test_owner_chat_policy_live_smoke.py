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
