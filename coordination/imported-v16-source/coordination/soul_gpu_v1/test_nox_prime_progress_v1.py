"""Actual pipeline progress is an event journal, never fictitious percent."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase,main
from nox_prime_progress_v1 import log_event,read_progress

class ProgressTests(TestCase):
    def test_counted_events_and_no_fictitious_steps(self):
        with TemporaryDirectory() as d:
            log_event(d,"DOWNLOAD","START","Model missing",actual=0,total=3)
            log_event(d,"DOWNLOAD","RUNNING","One source-hashed weight saved",actual=1,total=3)
            p=read_progress(d)
            self.assertEqual(len(p["events"]),2)
            self.assertEqual(p["current"]["actual"],1)
            self.assertEqual(p["current"]["total"],3)
            self.assertEqual(p["actual_gpu_steps"],[])
            self.assertFalse(p["s03_written"])
    def test_real_gpu_log_step_and_loss(self):
        with TemporaryDirectory() as d:
            path=Path(d)/"brain"/"intelligence"/"adapters"/"NOX_RESUME_test"/"training.log"
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('{"step":3560,"loss":1.02,"device":"DirectML"}\n'
                            '{"step":3561,"loss":0.91,"device":"DirectML"}\n'
                            '{"step":3562,"loss":"fake","device":"DirectML"}\n',
                            encoding="utf-8")
            p=read_progress(d)
            self.assertEqual([x["step"] for x in p["actual_gpu_steps"]],[3560,3561])
            self.assertEqual(p["last_gpu_step"]["loss"],0.91)
    def test_no_imaginary_percent_or_overflow(self):
        with TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                log_event(d,"GPU_TRAIN","RUNNING","fake",actual=99,total=10)
            with self.assertRaises(ValueError):
                log_event(d,"READY","FRAUD","must reject")
if __name__=="__main__":main()
