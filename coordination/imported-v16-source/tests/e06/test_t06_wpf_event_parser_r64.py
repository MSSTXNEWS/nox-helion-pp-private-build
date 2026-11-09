"""Exact GitHub-original WPF shell event log proof regression (BOOST03 R64)."""
import ast, pathlib, re, unittest
SRC=pathlib.Path(__file__).resolve().parents[2]/"coordination/e06/t06_samevm_installed_smoke.py"
RAW=SRC.read_text("utf-8")
TREE=ast.parse(RAW,filename=str(SRC))
FUN=[f for f in TREE.body if isinstance(f,ast.FunctionDef) and
     f.name in ("wpf_startup_marker_flags","summarize_fresh_webview_navigation")]
assert len(FUN)==2
NAMESPACE={"re":re}
exec(compile(ast.Module(body=FUN,type_ignores=[]),str(SRC),"exec"),NAMESPACE)
flags=NAMESPACE["wpf_startup_marker_flags"]
summarize=NAMESPACE["summarize_fresh_webview_navigation"]

class ExactEventTests(unittest.TestCase):
    def test_true_owner_nav_and_native_handshake(self):
        actual=flags("[2026-11-03] NAV_START\n[2026-11-03] NAV_OK\n"
                     "[2026-11-03] P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK\n")
        self.assertTrue(actual["NAV_OK"])
        self.assertTrue(actual["P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK"])
    def test_nav_fail_text_cannot_create_nav_ok(self):
        raw="[now] NAV_FAIL ConnectionFailed contains NAV_OK\n[now] INFO NAV_OK\n"
        self.assertFalse(flags(raw)["NAV_OK"])
        self.assertEqual(summarize(raw)["nav_failure_status"],"ConnectionFailed")
    def test_unbracketed_prose_and_nested_hold_cannot_spoof(self):
        raw="NAV_OK\nrandom ] NAV_OK\n[now] BLOCK_NAV with INIT_ERROR\n"
        actual=flags(raw)
        self.assertFalse(actual["NAV_OK"])
        self.assertFalse(actual["INIT_ERROR"])
        self.assertTrue(actual["BLOCK_NAV"])
    def test_diagnostics_not_other_event_prose(self):
        raw="[now] NAV_START includes NAV_FAIL\n[now] INFO WEBVIEW_PROCESS_FAILED\n"
        status=summarize(raw)
        self.assertTrue(status["nav_started"])
        self.assertFalse(status["nav_failed"])
        self.assertFalse(status["webview_process_failed"])
    def test_wiring_preserves_same_live_pid_hwnd_ipc(self):
        fn=next(f for f in TREE.body if isinstance(f,ast.FunctionDef)
                and f.name=="live_original_wpf_probe")
        body=ast.get_source_segment(RAW,fn)
        self.assertIn("wpf_startup_marker_flags(complete_lines)",body)
        self.assertNotIn("marker in window",body)
        self.assertIn("find_visible_wpf_hwnd(process.pid)",body)
        self.assertIn("alive_at_proof",body)
        self.assertIn("log_replaced",body)
if __name__=="__main__": unittest.main()
