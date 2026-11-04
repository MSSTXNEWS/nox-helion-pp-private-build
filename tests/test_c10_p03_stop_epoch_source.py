"""C10 source contract only: STOP epoch must reach native P03 renderer actions.
This does NOT certify WPF compilation or installed E07.
Run in checkout: python -m unittest discover -s tests -p 'test_c10_p03_stop_epoch_source.py' -v
"""
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "coordination/e06/MainWindow.NativeP02.cs"


class StopEpochSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = SRC.read_text(encoding="utf-8")
        lo = cls.src.index("private async void OnP03WebMessageReceived(")
        hi = cls.src.index("private void ShutdownNativeP02()", lo)
        cls.handler = cls.src[lo:hi]

    def test_stop_rotates_source_generation(self):
        self.assertIn("_nativeModelsStop.Cancel();_nativeModelsStop.Dispose();", self.src)
        self.assertIn("_nativeModelsStop=new CancellationTokenSource();", self.src)

    def test_epoch_capture_before_p03_await(self):
        h = self.handler
        self.assertIn("var stopGeneration = _nativeModelsStop.Token;", h)
        self.assertLess(h.index("var stopGeneration = _nativeModelsStop.Token;"),
                        h.index("await _nativeModels.ReadJobsAsync("))

    def test_cancel_route_does_not_block_on_stopped_generation(self):
        self.assertIn('command.Action == "stop" ? CancellationToken.None : stopGeneration', self.handler)

    def test_consent_and_queue_share_captured_epoch(self):
        h = self.handler
        self.assertIn("await ConfirmP02NativeAsync(route, root, activeStopToken)", h)
        self.assertIn("activeStopToken.ThrowIfCancellationRequested();", h)
        self.assertIn('command.Action is not ("stop" or "diagnose"), activeStopToken)', h)
        self.assertNotIn('command.Action is not ("stop" or "diagnose"), CancellationToken.None)', h)

    def test_cancelled_epoch_has_no_native_ack(self):
        h = self.handler
        self.assertIn("if (activeStopToken.IsCancellationRequested ||", h)
        self.assertIn("if (!activeStopToken.IsCancellationRequested &&", h)


if __name__ == "__main__":
    unittest.main()
