"""One local source integration test for ComfyUI workflow graph/queue ACK gates."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from integrations.creative.nox_fastpack import engine


class ComfyWorkflowAdmission(unittest.TestCase):
    def test_api_workflow_is_bounded_object_and_native_ack_is_exact_id(self):
        with TemporaryDirectory() as directory:
            studio=engine.Studio(directory)
            studio.workflows.mkdir(parents=True,exist_ok=True)
            path=studio.workflows/"source.json"
            valid={"6":{"inputs":{"text":"old"}}}
            path.write_text(json.dumps(valid),encoding="utf-8")
            with patch.object(engine,"_get",return_value={"prompt_id":"a"*32}):
                result=studio.workflow("source.json","6","film")
            self.assertEqual(result["status"],"QUEUED")
            self.assertEqual(json.loads(path.read_text())["6"]["inputs"]["text"],"old")
            with patch.object(engine,"_get",return_value={"prompt_id":{"unsafe":True}}):
                with self.assertRaises(engine.StudioError):
                    studio.workflow("source.json","6","film")
            path.write_text("[]",encoding="utf-8")
            with self.assertRaises(engine.StudioError):
                studio.workflow("source.json","6","film")
            path.write_text(" "*5000+json.dumps(valid),encoding="utf-8")
            with patch.object(engine,"MAX_CREATIVE_WORKFLOW_BYTES",1024):
                with self.assertRaises(engine.StudioError):
                    studio.workflow("source.json","6","film")


if __name__=="__main__":
    unittest.main()
