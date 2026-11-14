"""One offline model-response test for editable NOX film storyboard writes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from integrations.creative.nox_fastpack.engine import Studio,StudioError


class StoryboardShape(unittest.TestCase):
    def test_missing_or_unstructured_scenes_cannot_publish_partial_storyboard(self):
        with TemporaryDirectory() as folder:
            studio=Studio(folder)
            project="filmr31"
            variants=(
                ({"scenes":[None]},False),
                ({"scenes":[]},False),
                ({"scenes":[{"duration_s":4,"dialogue":"Hola"}]},True),
            )
            for content,valid in variants:
                with self.subTest(valid=valid,response=content):
                    studio._text=lambda prompt,format_json:json.dumps(content)
                    if valid:
                        outcome=studio.storyboard("A cinematic story",scenes=1,project_id=project)
                        self.assertEqual(outcome["status"],"STORYBOARD_READY")
                        self.assertIn("Hola",(Path(folder)/"projects"/project/"subtitles.srt").read_text("utf-8"))
                    else:
                        with self.assertRaises(StudioError):
                            studio.storyboard("A cinematic story",scenes=1,project_id=project)
                        self.assertFalse((Path(folder)/"projects"/project/"storyboard.json").is_file())


if __name__=="__main__":
    unittest.main()
