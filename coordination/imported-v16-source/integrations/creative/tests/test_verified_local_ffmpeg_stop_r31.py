"""One local source test: FFmpeg STOP is not successful before exit is proven."""
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from integrations.creative.nox_fastpack import engine


class FakeProcess:
    def __init__(self,exits=True):
        self.exits=exits
        self.exited=False
        self.killed=0
    def poll(self):return 0 if self.exited else None
    def kill(self):
        self.killed+=1
        if not self.exits:raise OSError("fixture kill denied")
    def wait(self,timeout):
        if self.exits:self.exited=True
        return 0


class VerifiedLocalStop(unittest.TestCase):
    def test_explicit_consent_and_verifiable_worker_exit(self):
        with TemporaryDirectory() as root:
            studio=engine.Studio(root)
            with patch.object(engine,"_get") as provider:
                with self.assertRaises(engine.StudioError):
                    studio.stop("false")
                provider.assert_not_called()
            good=FakeProcess()
            studio._active_process=good
            result=studio.stop(False)
            self.assertEqual(result["status"],"STOPPED")
            self.assertTrue(result["ffmpeg_cancelled"])
            self.assertEqual(good.killed,1)
            bad=FakeProcess(exits=False)
            studio._active_process=bad
            result=studio.stop(False)
            self.assertEqual(result["status"],"STOP_UNCONFIRMED")
            self.assertFalse(result["ffmpeg_cancelled"])
            studio._active_process=None
            self.assertEqual(studio.stop(False)["status"],"NO_ACTIVE_LOCAL_RENDER")


if __name__=="__main__":
    unittest.main()
