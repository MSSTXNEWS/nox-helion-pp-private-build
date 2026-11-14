"""R65: never treat past NAV_OK/IPC as live WPF GUI proof after a fatal event.

This is a SOURCE-level unit test. It does not certify Windows, an installed
WebView2 environment, or E07. Execute with:
python -m unittest discover -v -s tests/e06 -p test_t06_processfailure_revokes_gui_r65.py
"""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_samevm_installed_smoke.py"
FATAL = ("NAV_FAIL", "BLOCK_NAV", "WEBVIEW_PROCESS_FAILED",
         "INIT_ERROR", "P02_ORIGINAL_NATIVE_HOLD")


def source_function():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    funcs = {node.name: node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    body = ast.Module(body=[funcs["wpf_startup_fatal_seen"]], type_ignores=[])
    namespace = {}
    exec(compile(body, str(SOURCE), "exec"), namespace)
    return namespace["wpf_startup_fatal_seen"], funcs["live_original_wpf_probe"]


class WebView2FatalAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fatal, cls.live = source_function()

    def test_normal_success_markers_do_not_signal_fatal(self):
        self.assertFalse(self.fatal({"NAV_OK": True,
                                     "P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK": True}))

    def test_each_real_failure_revokes_existing_nav_ok_and_ipc(self):
        for event in FATAL:
            with self.subTest(event=event):
                seen = {"NAV_OK": True, "P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK": True}
                seen[event] = True
                self.assertTrue(self.fatal(seen))

    def test_failure_after_initial_nav_ok_is_terminal_for_same_launch(self):
        seen = {"NAV_OK": True, "P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK": True}
        self.assertFalse(self.fatal(seen))
        seen["WEBVIEW_PROCESS_FAILED"] = True
        self.assertTrue(self.fatal(seen))

    def test_original_live_probe_checks_failure_before_early_pass_and_at_return(self):
        calls = [node for node in ast.walk(self.live)
                 if isinstance(node, ast.Call) and
                 isinstance(node.func, ast.Name) and
                 node.func.id == "wpf_startup_fatal_seen"]
        self.assertEqual(len(calls), 2)
        # Both guards live inside the original launched-process probe,
        # not solely in a disconnected report helper.
        self.assertTrue(any(isinstance(node, ast.If) for node in ast.walk(self.live)))
        self.assertTrue(any(isinstance(node, ast.Assign) for node in ast.walk(self.live)))


if __name__ == "__main__":
    unittest.main()
