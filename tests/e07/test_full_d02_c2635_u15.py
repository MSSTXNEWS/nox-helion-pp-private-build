"""U15 source invariants; physical acceptance only from actual Windows receipt."""
import ast,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[2]
class U09(unittest.TestCase):
    def test_probe_syntax_and_pins(self):
        s=(R/"coordination/e07/probe_full_d02_c2635_u15.py").read_text()
        ast.parse(s)
        for v in ("30cbd21782eacd452363d6c65899fd5e57a24d1c",
                  "c2635c56b4d742973df50ff07f1647d1c0c4ff4689b8a94b02b79b7fbf0d8b99",
                  "NOX-V16-4808dde05af9293a073db03f",
                  "source_receipts_729_parity_verified",
                  "samevm_lifecycle_verified",
                  "installed_file_sha_locked"):
            self.assertIn(v,s)
    def test_real_clicks_without_fake_release(self):
        s=(R/"coordination/e07/probe_full_d02_c2635_u15.py").read_text()
        self.assertIn("e07.lifecycle(setup,result,physical_nav=True)",s)
        self.assertIn('evaluate(result["checks"]["installed_gui"])',s)
        self.assertIn('"independent_e07_10_10":"HOLD"',s)
        self.assertIn('"release_accepted":False',s)
    def test_backward_compatible_existing_e07(self):
        s=(R/"coordination/e07/independent_setup_e07.py").read_text(encoding="utf-8")
        ast.parse(s)
        self.assertIn("physical_nav: bool = False",s)
        self.assertIn('safe_nav=physical_nav or frozen_source ==',s)
    def test_no_second_gui_backend_or_model_download(self):
        s=(R/"coordination/e07/probe_full_d02_c2635_u15.py").read_text()
        self.assertNotIn("ollama pull",s)
        self.assertNotIn("Popen(",s)
        self.assertNotIn("models.pull",s)
if __name__=="__main__":
    unittest.main()
