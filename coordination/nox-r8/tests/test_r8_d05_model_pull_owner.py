"""R8 D05 first-fail: OWNER-correlated Ollama pull/cancel and verified DONE (source contract only).

This does NOT assert successful Windows compilation, live Ollama download or owner-PC E2E.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1] / "overrides" / "src"
CS = (ROOT / "MainWindow.xaml.cs").read_text(encoding="utf-8")
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
PULL = CS.split("private async Task PullExistingProviderModel(", 1)[1].split(
    "private const string VuneoImportReceipt", 1)[0]


class ModelPullOwnerContract(unittest.TestCase):
    def test_native_pull_requires_request_and_owner_approval(self):
        self.assertIn('PullExistingProviderModel(Text("model"), Text("requestId"))', CS)
        self.assertIn("ValidWriteRequestId(requestId)", PULL)
        self.assertIn("MessageBox.Show(this,", PULL)
        self.assertIn("MessageBoxResult.Yes", PULL)
        self.assertIn('status = "DENIED"', PULL)

    def test_native_stop_is_request_and_model_scoped(self):
        self.assertIn("activeModelPullRequestId, pullId", CS)
        self.assertIn("activeModelPullName, pullModel", CS)
        self.assertIn('status = "CANCEL_DENIED"', CS)
        self.assertIn("activeModelPull.Cancel();", CS)
        self.assertNotIn('case "model.cancel": activeModelPull?.Cancel(); break;', CS)

    def test_done_requires_exact_provider_tag_readback(self):
        self.assertLess(PULL.index('Api + "/api/tags"'), PULL.index('status = "DONE"'))
        self.assertIn('string.Equals(x.GetProperty("name").GetString(), modelName, StringComparison.Ordinal)', PULL)
        self.assertNotIn("await CheckProvider()", PULL)
        self.assertIn("cts.Token.ThrowIfCancellationRequested();", PULL)

    def test_webview_owner_and_terminal_gate(self):
        self.assertIn("pendingModelPull={requestId,model}", HTML)
        self.assertIn("post('model.pull',{model,requestId})", HTML)
        self.assertIn("post('model.cancel',{requestId,model})", HTML)
        self.assertRegex(HTML, r"v\?\.requestId!==pendingModelPull.requestId")
        self.assertRegex(HTML, r"v\?\.model!==pendingModelPull.model")
        for state in ("DONE", "STOPPED", "ERROR", "DENIED"):
            self.assertIn("'"+state+"'", HTML)


if __name__ == "__main__":
    unittest.main()
