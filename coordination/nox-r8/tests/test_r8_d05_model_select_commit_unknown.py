"""D05 R8: native model selection's COMMIT-unknown owner receipt contract.

Source-contract regression only: does not run WPF, Ollama or Windows.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NATIVE = ROOT / "overrides" / "src" / "MainWindow.xaml.cs"
WEB = ROOT / "overrides" / "src" / "index.html"

class ModelSelectCommitUnknownContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native = NATIVE.read_text(encoding="utf-8")
        start = native.index("private async Task SelectModel(string model, string requestId)")
        end = native.index("private async Task PullExistingProviderModel(", start)
        cls.method = native[start:end]
        cls.web = WEB.read_text(encoding="utf-8")

    def test_commit_attempt_marked_before_commit(self):
        self.assertLess(self.method.index("commitAttempted = true;"), self.method.index("tx.Commit();"))
        self.assertLess(self.method.index("tx.Commit();"), self.method.index("using (var verifyDb"))
        self.assertLess(self.method.index("using (var verifyDb"), self.method.index('Send("model.select.receipt"'))

    def test_ambiguous_sqlite_and_transport_not_denied(self):
        m = self.method
        self.assertIn("if (commitAttempted)", m)
        self.assertIn('Send("model.select.uncertain"', m)
        self.assertIn("NOX_MODEL_SELECT_PERSISTENCE_UNKNOWN_HOLD", m)
        self.assertIn('Send("model.select.denied"', m)
        self.assertLess(m.index('catch (Exception ex)'), m.index('Send("model.select.receipt"'))
        self.assertLess(m.index('Send("model.select.receipt"'), m.index('await CheckProvider();'))

    def test_owner_ack_is_correlated_and_replay_is_held(self):
        w = self.web
        p = w.index("case 'model.select.uncertain':")
        end = w.index("case 'model.select.denied':", p)
        case = w[p:end]
        self.assertIn("v?.requestId===pendingModel.requestId", case)
        self.assertIn("v?.model===pendingModel.model", case)
        self.assertIn("pendingModel.uncertain=true", case)
        self.assertIn("$('saveModel').disabled=true", case)
        self.assertIn("$('modelPicker').disabled=true", case)
        denied = w[end:w.index("case 'download':", end)]
        self.assertIn("!pendingModel.uncertain", denied)
        self.assertIn("if(pendingModel&&(v.models||[]).includes(pendingModel.model))picker.value=pendingModel.model", w)

if __name__ == "__main__":
    unittest.main()
