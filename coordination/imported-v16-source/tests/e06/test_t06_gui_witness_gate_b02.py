"""B02: installed original WPF GUI proof must require stable live HWND and IPC."""
from __future__ import annotations
import ast
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[2]/"coordination/e06/t06_samevm_installed_smoke.py"

def load_gate():
    text=SOURCE.read_text(encoding="utf-8")
    tree=ast.parse(text, filename=str(SOURCE))
    helper=next((node for node in tree.body if isinstance(node,ast.FunctionDef)
                 and node.name=="proven_wpf_gui"),None)
    if helper is None: raise AssertionError("T06_INSTALLED_GUI_GATE_MISSING")
    context={}
    exec(compile(ast.Module(body=[helper],type_ignores=[]),str(SOURCE),"exec"),context)
    return context["proven_wpf_gui"],text

class OriginalGuiPhysicalWitness(unittest.TestCase):
    def test_no_false_gui_pass(self):
        gate, source=load_gate()
        good=dict(new_nav_ok=True,new_python_ipc_handshake=True,
                  stable_ready_window_pass=True,real_wpf_visible_pid_hwnd=True,
                  live_process_at_receipt=True,init_error=False,native_hold=False,
                  log_replaced=False)
        self.assertTrue(gate(good))
        for key in good:
            for value in (None,0 if good[key] else 1,
                          "true" if good[key] else "false"):
                altered=good.copy(); altered[key]=value
                with self.subTest(field=key,bad=value):
                    self.assertFalse(gate(altered))
            altered=good.copy(); altered.pop(key)
            with self.subTest(field=key,missing=True):
                self.assertFalse(gate(altered))
        self.assertFalse(gate(None))
        self.assertFalse(gate([]))
        main=source.split("def main()->int:",1)[1]
        self.assertIn('require(proven_wpf_gui(gui),',main)
        self.assertIn('report["installed_process_gui_webview2"]="PASS"',main)
        self.assertLess(main.index('require(proven_wpf_gui(gui),'),
                        main.index('report["installed_process_gui_webview2"]="PASS"'))

if __name__=="__main__":
    unittest.main()
